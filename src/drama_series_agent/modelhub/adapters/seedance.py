"""Seedance 2.5 on Volcengine Ark's content-generation tasks (the same account and key as
Seedream, ``volcengine.py``).

Checked against the Ark docs (docs.volcengine.com 82379/1520757 create, 1521309 query, 1521720
delete, 1330310 models, 1544106 prices, 1299023 errors) on 2026-10-26 (DECISIONS 同日
「M5 第 6 步」):

- ``POST /contents/generations/tasks`` with the fields in JSON (强校验; not the ``--rs`` text
  commands): ``content`` (the prompt; the first frame as a data URI with role ``first_frame``),
  ``resolution`` ``480p / 720p / 1080p``, ``ratio`` (``adaptive`` with a first frame: 2.5 takes
  the picture's aspect, so the keyframe sets it), ``duration`` whole seconds 4–30,
  ``generate_audio``, ``watermark: false``. 24 fps; no seed on 2.5. Answers ``id``.
- First frame, first + last frame and 全模态参考 are exclusive: we send the first frame only
  (no locked pictures, no audio). With 先配音 lines (``dialogue_audio``) Seedance makes no sound
  of its own: the lines are laid on in post.
- ``GET …/tasks/{id}``: ``queued / running / succeeded / failed / cancelled / expired``, the
  video at ``content.video_url`` (24 h, at most 100 downloads: fetched at once). The bill is
  ``usage.completion_tokens`` (w × h × 24 × seconds / 1024) at 70 / 77 元 per million for
  480p–720p / 1080p, reported as ``Usage.tokens["video_<res>"]``. Failed tasks are not billed.
  ``DELETE`` cancels a task still queued.
- Personal accounts run 3 tasks at once (enterprise 10).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from drama_series_agent.core.storage import BlobStore
from drama_series_agent.modelhub.adapters.base import (
    CallContext,
    Estimate,
    Health,
    ModelError,
    ModelRequest,
    ModelResult,
    ModelSpec,
    Usage,
)
from drama_series_agent.modelhub.adapters.http import KeyGetter, send
from drama_series_agent.modelhub.adapters.images import data_uri, load_refs
from drama_series_agent.modelhub.adapters.minimax_video import seconds_for
from drama_series_agent.modelhub.adapters.tasks import download, poll, video_file
from drama_series_agent.modelhub.adapters.volcengine import _code
from drama_series_agent.modelhub.adapters.volcengine import _error as _ark_error
from drama_series_agent.modelhub.pricing import cost_usd
from drama_series_agent.utils.llm_client import normalize_base_url

DURATION = (4, 30)
TASKS = "/contents/generations/tasks"
MAX_BODY = 64 * 1024 * 1024
TIERS = (("1080p", 1080), ("720p", 720), ("480p", 480))


def _error(status: int, body: str) -> ModelError:
    code = _code(body)
    if code == "AccountOverdueError":
        return ModelError("insufficient_balance", body[:300], status=status)
    if code == "QuotaExceeded":  # too many queued tasks (or the free trial is used up)
        return ModelError("rate_limited", body[:300], status=status, retryable=True)
    return _ark_error(status, body)


def resolution_for(w: int, h: int, offered: list[str]) -> str:
    """The highest tier the frame's short edge reaches (a 768 draft is 720p)."""
    short = min(w, h)
    for tier, edge in TIERS:
        if short >= edge and tier in offered:
            return tier
    return offered[-1] if offered else "720p"


def resolution_tier(spec: ModelSpec, params: dict[str, Any]) -> str:
    """The tier a request is made (and billed) at; the Mock adapter bills by it too."""
    offered = spec.caps.resolutions or [tier for tier, _ in TIERS]
    w, h = params.get("width"), params.get("height")
    if not (w and h):
        return "720p" if "720p" in offered else offered[0]
    return resolution_for(int(w), int(h), offered)


class SeedanceAdapter:
    def __init__(
        self,
        spec: ModelSpec,
        *,
        get_key: KeyGetter,
        store: BlobStore,
        transport: httpx.AsyncBaseTransport | None = None,
        max_retries: int = 2,
        backoff_s: float = 2.0,
        poll_s: float = 5.0,
        request_timeout_s: float = 120.0,
    ) -> None:
        self.spec = spec
        self._get_key = get_key
        self._store = store
        self._base_url = normalize_base_url(spec.base_url or "")
        self._transport = transport
        self.max_retries = max_retries
        self.backoff_s = backoff_s
        self.poll_s = poll_s
        self.request_timeout_s = request_timeout_s

    @property
    def key(self) -> str:
        return self.spec.key

    # ------------------------------------------------------------------ protocol

    def estimate(self, req: ModelRequest) -> Estimate:
        seconds = self._seconds(req)
        return Estimate(
            cost_usd=cost_usd(
                self.spec.pricing, Usage(output_seconds=seconds), resolution=self._resolution(req)
            ),
            seconds=90.0 + seconds * 15.0,
            priced=self.spec.pricing.known,
        )

    async def run(self, req: ModelRequest, ctx: CallContext) -> ModelResult:
        body = self._body(req)
        async with self._client() as client:
            created = await self._send(client, "POST", TASKS, json=body)
            task_id = str(created.json().get("id") or "")
            if not task_id:
                raise ModelError("invalid_response", created.text[:300])
            try:
                task = await self._wait(client, task_id, ctx)
            except asyncio.CancelledError:
                await asyncio.shield(self._cancel(task_id))
                raise
        url = (task.get("content") or {}).get("video_url")
        if not url:
            raise ModelError("invalid_response", "no video_url", billed=True)
        data = await download(
            str(url),
            transport=self._transport,
            timeout_s=self.request_timeout_s,
            max_retries=self.max_retries,
            backoff_s=self.backoff_s,
        )
        asked = float(task.get("duration") or body["duration"])
        video = await video_file(data, asked, self.key)
        resolution = str(task.get("resolution") or body["resolution"])
        tokens = int((task.get("usage") or {}).get("completion_tokens") or 0)
        return ModelResult(
            files=[video],
            usage=Usage(
                output_seconds=asked,
                tokens={f"video_{resolution}": tokens} if tokens else None,
                resolution=resolution,
            ),
            raw={"task_id": task_id, "model": task.get("model")},
        )

    async def health(self) -> Health:
        """The task list (free, one row): the key works."""
        try:
            async with self._client() as client:
                await self._send(client, "GET", TASKS, params={"page_size": 1})
        except ModelError as exc:
            return Health(ok=False, detail=exc.code)
        return Health(ok=True, models=[self.spec.model_id] if self.spec.model_id else [])

    # ------------------------------------------------------------------ request

    def _body(self, req: ModelRequest) -> dict[str, Any]:
        p = req.params
        text = (req.prompt or "").strip()
        if not text:
            raise ModelError("bad_request", "empty prompt")
        content: list[dict[str, Any]] = [{"type": "text", "text": text}]
        first = p.get("first_frame")
        if first:
            data, mime = load_refs(self._store, [str(first)], 1)[0]
            url = data_uri(data, mime)
            content.append({"type": "image_url", "image_url": {"url": url}, "role": "first_frame"})
        body: dict[str, Any] = {
            **dict((self.spec.caps.model_extra or {}).get("request") or {}),
            "model": self._model_id(),
            "content": content,
            "resolution": self._resolution(req),
            "ratio": "adaptive" if first else str(p.get("aspect") or "adaptive"),
            "duration": self._seconds(req),
            "generate_audio": bool(p.get("with_audio", True)) and not p.get("dialogue_audio"),
            "watermark": False,
        }
        if len(json.dumps(body)) > MAX_BODY:
            raise ModelError("input_too_large", f"{self.key}: request over 64 MB")
        return body

    def _seconds(self, req: ModelRequest) -> int:
        span = (self.spec.caps.model_extra or {}).get("duration_s")
        lo, hi = (int(span[0]), int(span[1])) if span else DURATION
        return seconds_for(float(req.params.get("duration_s") or lo), (lo, hi))

    def _resolution(self, req: ModelRequest) -> str:
        return resolution_tier(self.spec, req.params)

    # ------------------------------------------------------------------ task

    async def _wait(
        self, client: httpx.AsyncClient, task_id: str, ctx: CallContext
    ) -> dict[str, Any]:
        last: list[str] = []

        async def check() -> dict[str, Any] | None:
            resp = await self._send(client, "GET", f"{TASKS}/{task_id}")
            task: dict[str, Any] = resp.json()
            status = str(task.get("status") or "")
            if status == "succeeded":
                return task
            if status == "failed":
                raise _error(400, json.dumps({"error": task.get("error") or {}}))
            if status in ("cancelled", "expired"):
                raise ModelError("canceled", status)
            if ctx.on_progress is not None and status and last[-1:] != [status]:
                await ctx.on_progress({"status": status, "task_id": task_id})
            last.append(status)
            return None

        return await poll(check, first_s=self.poll_s)

    async def _cancel(self, task_id: str) -> None:
        """Best effort: a queued task is cancelled; a running one cannot be."""
        try:
            async with self._client() as client:
                await client.delete(f"{TASKS}/{task_id}", headers=self._headers())
        except (httpx.HTTPError, ModelError):
            pass

    # ------------------------------------------------------------------ internals

    def _model_id(self) -> str:
        if not self.spec.model_id:
            raise ModelError("model_id_missing", f"{self.key}: fill model_id in providers.yaml")
        return self.spec.model_id

    def _headers(self) -> dict[str, str]:
        name = self.spec.key_name
        api_key = self._get_key(name) if name else None
        if not api_key:
            raise ModelError("missing_key", name or self.key)
        return {"Authorization": f"Bearer {api_key}"}

    def _client(self) -> httpx.AsyncClient:
        if not self._base_url:
            raise ModelError("base_url_missing", self.key)
        return httpx.AsyncClient(
            base_url=self._base_url, timeout=self.request_timeout_s, transport=self._transport
        )

    async def _send(
        self, client: httpx.AsyncClient, method: str, path: str, **kwargs: Any
    ) -> httpx.Response:
        return await send(
            client,
            method,
            path,
            headers=self._headers(),
            max_retries=self.max_retries,
            backoff_s=self.backoff_s,
            errors=_error,
            **kwargs,
        )
