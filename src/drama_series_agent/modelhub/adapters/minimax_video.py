"""MiniMax H3 through the video V2 API: generation, Context-IR and Regenerate-2K.

Checked against platform.minimaxi.com / platform.minimax.io on 2026-10-26 (DECISIONS 同日
「M5 第 6 步」):

- **Host** is the ``minimax_llm`` account's base URL without ``/v1`` (the V2 paths sit at the
  root): ``https://api.minimax.cn`` (China) or ``https://api.minimax.io``. Bearer key.
- **Three async tasks**, one query: ``POST /v2/video_generation`` (``kind="video"``),
  ``POST /v2/h3_context_ir`` (``kind="llm_aux"``: the official prompt rewriter, answers
  ``content.prompt`` and makes no video) and ``POST /v2/video_regeneration``
  (``kind="upscale"``: a 768P H3 take at 2K). Each answers ``task_id``; ``GET
  /v2/query/video_generation/{task_id}`` reports ``queued / running / succeeded / failed /
  cancelled``, the video at ``content.url`` (time-limited, downloaded at once), ``usage``.
  Polled with exponential backoff; a call that is cancelled (or times out) cancels a task still
  queued (``DELETE /v2/video_generation/{task_id}``; a running one cannot be stopped).
- **Inputs** go in ``content[]`` as data URIs (≤ 64 MB per request). First / last frames and
  ``reference_*`` items cannot be mixed, so: with audio (``dialogue_audio`` for 先配音,
  ``ref_audio`` voice samples for 原生同步) the request is reference-to-video, the first frame
  becomes ``<Picture 1>`` (``reference_image``), then the locked pictures (9 at most), then the
  audio; without audio it is image-to-video with the first frame (``first_frame``, a hard
  anchor) and the locked pictures are left out. ``ratio`` is the frame's (image-to-video ignores
  it). ``duration`` is whole seconds in ``caps.duration_s``; ``resolution`` ``768P`` or ``2K``
  by the frame's short edge. Output is 24 fps with sound (always; ``with_audio`` cannot turn it
  off). No seed.
- **Regenerate-2K** resends the draft's own inputs (the prompt that was actually sent, the same
  pictures and audio) plus the untrimmed 768P draft as ``base_video`` (``params["video_in"]``;
  it must have sound, 24 fps, 107–362 frames in steps of 17).
- **Errors** come back with real HTTP statuses and the MiniMax code in parentheses at the end
  of ``error.message`` (``… (1026)``); a failed task has ``task.error.code``.
- **Billing** (国内价, CNY): by ``usage.output_seconds`` at the resolution's price, plus
  ``usage.input_seconds`` (input video) and pictures past the first 5 (``extra_image``).
  Context-IR by tokens. Rate limit: 300 RPM, 30 tasks in flight.
"""

from __future__ import annotations

import asyncio
import json
import math
import re
from typing import Any

import httpx

from drama_series_agent.core.storage import BlobStore
from drama_series_agent.media.image import image_info
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
from drama_series_agent.modelhub.adapters.http import KeyGetter, error_for, send
from drama_series_agent.modelhub.adapters.images import data_uri
from drama_series_agent.modelhub.adapters.minimax import _mime as audio_mime
from drama_series_agent.modelhub.adapters.tasks import download, poll, video_file
from drama_series_agent.modelhub.pricing import cost_usd

MAX_BODY = 64 * 1024 * 1024
MAX_IMAGES = 9
MAX_AUDIOS = 3
FREE_IMAGES = 5
DURATION = (4, 15)
PATHS = {
    "video": "/v2/video_generation",
    "llm_aux": "/v2/h3_context_ir",
    "upscale": "/v2/video_regeneration",
}
QUERY = "/v2/query/video_generation/{}"
# MiniMax code → (our code, retry?)
CODES: dict[str, tuple[str, bool]] = {
    "1000": ("provider_error", True),
    "1002": ("rate_limited", True),
    "1004": ("auth_failed", False),
    "1008": ("insufficient_balance", False),
    "1026": ("content_blocked", False),
    "1027": ("content_blocked", False),
    "1045": ("rate_limited", True),  # too many tasks in flight
    "2013": ("bad_request", False),
    "2022": ("model_not_enabled", False),
    "2064": ("provider_error", True),  # cluster busy
    "2069": ("model_not_found", False),  # model retired
}
_CODE = re.compile(r"\((\d{4})\)\s*$")


def _error(status: int, body: str) -> ModelError:
    try:
        message = str((json.loads(body).get("error") or {}).get("message") or "")
    except (ValueError, AttributeError):
        message = ""
    match = _CODE.search(message)
    if match and match.group(1) in CODES:
        code, retry = CODES[match.group(1)]
        return ModelError(code, body[:300], status=status, retryable=retry)
    if status == 529:  # overloaded
        return ModelError("provider_error", body[:300], status=status, retryable=True)
    return error_for(status, body)


def _failed(task: dict[str, Any]) -> ModelError:
    error = task.get("error") or {}
    code, _ = CODES.get(str(error.get("code") or ""), ("provider_error", False))
    return ModelError(code, f"{error.get('code')}: {error.get('message', '')}"[:300])


def host_of(base_url: str) -> str:
    """The account's base URL (``…/v1``) without the version: V2 paths sit at the root."""
    return re.sub(r"/v1/?$", "", base_url.rstrip("/"))


def seconds_for(duration_s: float, span: tuple[int, int]) -> int:
    """Whole seconds, rounded up (the take is trimmed later), inside the model's span."""
    return max(span[0], min(span[1], math.ceil(float(duration_s) - 0.05)))


def resolution_tier(spec: ModelSpec, params: dict[str, Any]) -> str:
    """``2K`` when the frame is past 768P (an API run at the delivery tier) and the model
    has it; ``768P`` otherwise. The Mock adapter bills by it too."""
    if spec.kind == "upscale":
        return "2K"
    offered = spec.caps.resolutions or ["768P"]
    w, h = params.get("width"), params.get("height")
    short = min(int(w), int(h)) if w and h else 768
    return "2K" if short > 768 and "2K" in offered else "768P"


class MiniMaxVideoAdapter:
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
        self._host = host_of(spec.base_url or "")
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
        if self.spec.kind == "llm_aux":
            usage = Usage(tokens_in=6000 + len(req.prompt or "") // 2, tokens_out=4000)
            return Estimate(cost_usd(self.spec.pricing, usage), 30.0, self.spec.pricing.known)
        seconds = self._seconds(req)
        images = self._image_count(req)
        usage = Usage(
            output_seconds=seconds,
            # Regenerate-2K: the draft counts as input video (on the safe side; the docs'
            # example bills it 0).
            input_seconds=seconds if self.spec.kind == "upscale" else None,
            calls=self._extra_images(images),
        )
        resolution = self._resolution(req).lower()
        return Estimate(
            cost_usd=cost_usd(self.spec.pricing, usage, resolution=resolution),
            seconds=120.0 + seconds * 20.0,
            priced=self.spec.pricing.known,
        )

    async def run(self, req: ModelRequest, ctx: CallContext) -> ModelResult:
        if self.spec.kind not in PATHS:
            raise ModelError("bad_request", f"{self.key}: kind {self.spec.kind}")
        body = self._body(req)
        async with self._client() as client:
            created = await self._send(client, "POST", PATHS[self.spec.kind], json=body)
            task_id = str(created.json().get("task_id") or "")
            if not task_id:
                raise ModelError("invalid_response", created.text[:300])
            try:
                task = await self._wait(client, task_id, ctx)
            except asyncio.CancelledError:
                await asyncio.shield(self._cancel(task_id))
                raise
        if self.spec.kind == "llm_aux":
            return self._prompt(task)
        return await self._video(task, req)

    async def health(self) -> Health:
        """The task list (free): the key works. MiniMax has no call that checks a model."""
        try:
            async with self._client() as client:
                await self._send(
                    client,
                    "GET",
                    "/v2/query/video_generation",
                    params={"page_num": 1, "page_size": 1},
                )
        except ModelError as exc:
            return Health(ok=False, detail=exc.code)
        return Health(ok=True, models=[self.spec.model_id] if self.spec.model_id else [])

    # ------------------------------------------------------------------ request

    def _body(self, req: ModelRequest) -> dict[str, Any]:
        p = req.params
        content = self._content(req)
        body: dict[str, Any] = {"model": self._model_id(), "content": content}
        if self.spec.kind == "upscale":
            body["resolution"] = "2K"
        else:
            body["duration"] = self._seconds(req)
            if p.get("aspect"):
                body["ratio"] = str(p["aspect"])
        if self.spec.kind == "video":
            body["resolution"] = self._resolution(req)
        if len(json.dumps(body)) > MAX_BODY:
            raise ModelError("input_too_large", f"{self.key}: request over 64 MB")
        return body

    def _content(self, req: ModelRequest) -> list[dict[str, Any]]:
        p = req.params
        text = (req.prompt or "").strip()
        if not text:
            raise ModelError("bad_request", "empty prompt")
        items: list[dict[str, Any]] = [{"type": "text", "text": text}]
        audios = self._audios(req)
        first = p.get("first_frame")
        if audios:
            pictures = [first, *(p.get("refs") or [])] if first else list(p.get("refs") or [])
            for sha in pictures[:MAX_IMAGES]:
                items.append(self._picture(str(sha), "reference_image"))
            for data in audios:
                url = data_uri(data, audio_mime(data))
                items.append(
                    {"type": "audio_url", "audio_url": {"url": url}, "role": "reference_audio"}
                )
        elif first:
            items.append(self._picture(str(first), "first_frame"))
        if self.spec.kind == "upscale":
            base = p.get("video_in")
            if not base:
                raise ModelError("bad_request", "Regenerate-2K needs the draft (video_in)")
            url = data_uri(self._blob(str(base)), "video/mp4")
            items.append({"type": "video_url", "video_url": {"url": url}, "role": "base_video"})
        return items

    def _audios(self, req: ModelRequest) -> list[bytes]:
        p = req.params
        if p.get("dialogue_audio"):  # 先配音: the lines, copied as the sound
            shas = [p["dialogue_audio"]]
        else:  # 原生同步: the speakers' voice samples
            shas = list(p.get("ref_audio") or [])
        return [self._blob(str(sha)) for sha in shas[:MAX_AUDIOS]]

    def _picture(self, sha: str, role: str) -> dict[str, Any]:
        data = self._blob(sha)
        try:
            mime = image_info(data).mime
        except ValueError as exc:
            raise ModelError("ref_unreadable", f"{sha[:12]}: {exc}") from exc
        return {"type": "image_url", "image_url": {"url": data_uri(data, mime)}, "role": role}

    def _blob(self, sha: str) -> bytes:
        try:
            return self._store.path_for(sha).read_bytes()
        except (OSError, ValueError) as exc:
            raise ModelError("ref_unreadable", f"{sha[:12]}: {exc}") from exc

    def _image_count(self, req: ModelRequest) -> int:
        p = req.params
        first = 1 if p.get("first_frame") else 0
        has_audio = bool(p.get("dialogue_audio") or p.get("ref_audio"))
        refs = len(p.get("refs") or []) if has_audio else 0
        return min(MAX_IMAGES, first + refs)

    @staticmethod
    def _extra_images(count: int) -> dict[str, int] | None:
        extra = max(0, count - FREE_IMAGES)
        return {"extra_image": extra} if extra else None

    def _seconds(self, req: ModelRequest) -> int:
        span = self.spec.caps.model_extra.get("duration_s") if self.spec.caps.model_extra else None
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
            resp = await self._send(client, "GET", QUERY.format(task_id))
            task: dict[str, Any] = resp.json().get("task") or {}
            status = str(task.get("status") or "")
            if status == "succeeded":
                return task
            if status in ("failed", "cancelled", "expired"):
                raise _failed(task) if status == "failed" else ModelError("canceled", status)
            if ctx.on_progress is not None and status and last[-1:] != [status]:
                await ctx.on_progress({"status": status, "task_id": task_id})
            last.append(status)
            return None

        return await poll(check, first_s=self.poll_s)

    async def _cancel(self, task_id: str) -> None:
        """Best effort: a queued task is cancelled; a running one cannot be."""
        try:
            async with self._client() as client:
                await client.delete(PATHS["video"] + f"/{task_id}", headers=self._headers())
        except (httpx.HTTPError, ModelError):
            pass

    def _prompt(self, task: dict[str, Any]) -> ModelResult:
        prompt = str((task.get("content") or {}).get("prompt") or "").strip()
        if not prompt:
            raise ModelError("invalid_response", "Context-IR answered no prompt")
        usage = task.get("usage") or {}
        return ModelResult(
            text=prompt,
            json={"prompt": prompt},
            usage=Usage(
                tokens_in=int(usage.get("prompt_tokens") or 0),
                tokens_out=int(usage.get("completion_tokens") or 0),
            ),
            raw={"task_id": task.get("id")},
        )

    async def _video(self, task: dict[str, Any], req: ModelRequest) -> ModelResult:
        url = (task.get("content") or {}).get("url")
        if not url:
            raise ModelError("invalid_response", "no video url", billed=True)
        data = await download(
            str(url),
            transport=self._transport,
            timeout_s=self.request_timeout_s,
            max_retries=self.max_retries,
            backoff_s=self.backoff_s,
        )
        asked = float(task.get("duration") or self._seconds(req))
        video = await video_file(data, asked, self.key)
        usage = task.get("usage") or {}
        resolution = str(task.get("resolution") or self._resolution(req)).lower()
        return ModelResult(
            files=[video],
            usage=Usage(
                output_seconds=float(usage.get("output_seconds") or asked),
                input_seconds=float(usage.get("input_seconds") or 0) or None,
                calls=self._extra_images(int(usage.get("input_image_count") or 0)),
                resolution=resolution,
            ),
            raw={"task_id": task.get("id"), "resolution": task.get("resolution")},
        )

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
        if not self._host:
            raise ModelError("base_url_missing", self.key)
        return httpx.AsyncClient(
            base_url=self._host, timeout=self.request_timeout_s, transport=self._transport
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
