"""sync.so lip sync (``sync/lipsync-2-pro``, M6 step 7a; plan E2 口型修复).

Checked against the official docs (sync.so/docs: api-reference generate create / get / list,
developer-guides asset-uploads, models/lipsync, product/billing, pricing) on 2026-11-18
(DECISIONS 同日「M6 第 7a 步」):

- ``https://api.sync.so``, key in ``x-api-key``.
- Local files go up as assets: ``POST /v2/assets/upload`` ``{fileName, contentType, size}`` →
  a presigned ``uploadUrl`` (``PUT`` the bytes, same Content-Type, no key) and the file's
  ``url``; ``POST /v2/assets`` ``{url, type: VIDEO | AUDIO}`` registers it → ``id``.
- ``POST /v2/generate`` ``{model, input: [{type: video, assetId}, {type: audio, assetId}],
  options}`` → ``id``, ``status: PENDING``. ``options.sync_mode: cut_off`` (the shorter of
  the two is made and billed: our track is padded to the take's length); further options
  (``temperature``, ``occlusion_detection_enabled`` …) from ``caps.options``.
- ``GET /v2/generate/{id}``: ``PENDING / PROCESSING / COMPLETED / NO_OP / FAILED / REJECTED``;
  ``outputUrl``, ``outputDuration``, ``error`` / ``errorCode``. ``NO_OP`` = nothing lip-synced
  (no visible talking face): a failure here.
- Billed per output frame ($0.00333 a frame on Hobbyist / Creator, the per-second price
  quoted at 25 fps): ``Usage.output_seconds`` is frames / 25, so ``price`` (per second) in
  ``providers.yaml`` is the quoted one.
- The key check is ``GET /v2/generations?limit=1`` (free).
"""

from __future__ import annotations

import asyncio
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
from drama_series_agent.modelhub.adapters.http import KeyGetter, error_for, send
from drama_series_agent.modelhub.adapters.tasks import download, poll, video_file
from drama_series_agent.modelhub.adapters.upload import compact_audio, upload_timeout
from drama_series_agent.modelhub.pricing import cost_usd
from drama_series_agent.utils.llm_client import normalize_base_url

BILLED_FPS = 25.0  # the per-second price is quoted at 25 frames a second
DONE = "COMPLETED"
NO_OP = "NO_OP"


def billed_seconds(duration_s: float, fps: float) -> float:
    """The output's frames as seconds of the quoted price."""
    return round(duration_s * fps / BILLED_FPS, 3)


def _error(status: int, body: str) -> ModelError:
    if status == 402:
        return ModelError("insufficient_balance", body[:300], status=status)
    if status == 422 and "file_size_exceeds_plan_limit" in body:
        return ModelError("input_too_large", body[:300], status=status)
    return error_for(status, body)


class SyncSoAdapter:
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
        duration = float(req.params.get("duration_s") or 5.0)
        fps = float(req.params.get("fps") or BILLED_FPS)
        return Estimate(
            cost_usd=cost_usd(
                self.spec.pricing, Usage(output_seconds=billed_seconds(duration, fps))
            ),
            seconds=60.0 + duration * 20.0,
            priced=self.spec.pricing.known,
        )

    async def run(self, req: ModelRequest, ctx: CallContext) -> ModelResult:
        p = req.params
        video = self._store.path_for(str(p["video_in"])).read_bytes()
        audio, audio_mime = await asyncio.to_thread(
            compact_audio, self._store.path_for(str(p["audio_in"])).read_bytes(), "audio/wav"
        )
        async with self._client() as client:
            video_id = await self._asset(client, video, "video/mp4", "VIDEO")
            audio_id = await self._asset(client, audio, audio_mime, "AUDIO")
            created = await self._send(
                client, "POST", "/v2/generate", json=self._body(video_id, audio_id), create=True
            )
            job_id = str(created.json().get("id") or "")
            if not job_id:
                raise ModelError("invalid_response", created.text[:300])
            job = await self._wait(client, job_id, ctx)
        url = job.get("outputUrl")
        if not url:
            raise ModelError("invalid_response", "no outputUrl", billed=True)
        data = await download(
            str(url),
            transport=self._transport,
            timeout_s=self.request_timeout_s,
            max_retries=self.max_retries,
            backoff_s=self.backoff_s,
        )
        asked = float(p.get("duration_s") or 0.0)
        out = await video_file(data, asked, self.key)
        made = float(job.get("outputDuration") or out.duration_s or asked)
        fps = float(p.get("fps") or BILLED_FPS)
        return ModelResult(
            files=[out],
            usage=Usage(output_seconds=billed_seconds(made, fps)),
            raw={"generation_id": job_id, "model": job.get("model")},
        )

    async def health(self) -> Health:
        """The generation list (free, one row): the key works."""
        try:
            async with self._client() as client:
                await self._send(client, "GET", "/v2/generations", params={"limit": 1})
        except ModelError as exc:
            return Health(ok=False, detail=exc.code)
        return Health(ok=True, models=[self.spec.model_id] if self.spec.model_id else [])

    # ------------------------------------------------------------------ request

    def _body(self, video_id: str, audio_id: str) -> dict[str, Any]:
        options = dict((self.spec.caps.model_extra or {}).get("options") or {})
        return {
            "model": self._model_id(),
            "input": [
                {"type": "video", "assetId": video_id},
                {"type": "audio", "assetId": audio_id},
            ],
            "options": {"sync_mode": "cut_off", **options},
        }

    async def _asset(self, client: httpx.AsyncClient, data: bytes, mime: str, kind: str) -> str:
        """One local file as a sync.so asset: presigned upload, then registered."""
        ext = {"video/mp4": "mp4", "audio/wav": "wav", "audio/mpeg": "mp3"}[mime]
        name = f"{kind.lower()}.{ext}"
        made = await self._send(
            client,
            "POST",
            "/v2/assets/upload",
            json={"fileName": name, "contentType": mime, "size": len(data)},
        )
        slot = made.json()
        upload_url, url = slot.get("uploadUrl"), slot.get("url")
        if not upload_url or not url:
            raise ModelError("invalid_response", made.text[:300])
        await send(  # presigned: no key goes with it
            client,
            "PUT",
            str(upload_url),
            content=data,
            headers={"Content-Type": mime},
            max_retries=self.max_retries,
            backoff_s=self.backoff_s,
            errors=_error,
            timeout=upload_timeout(len(data), self.request_timeout_s),
        )
        registered = await self._send(
            client, "POST", "/v2/assets", json={"url": url, "type": kind, "name": name}
        )
        asset_id = str(registered.json().get("id") or "")
        if not asset_id:
            raise ModelError("invalid_response", registered.text[:300])
        return asset_id

    # ------------------------------------------------------------------ task

    async def _wait(
        self, client: httpx.AsyncClient, job_id: str, ctx: CallContext
    ) -> dict[str, Any]:
        last: list[str] = []

        async def check() -> dict[str, Any] | None:
            resp = await self._send(client, "GET", f"/v2/generate/{job_id}")
            job: dict[str, Any] = resp.json()
            status = str(job.get("status") or "")
            if status == DONE:
                return job
            detail = f"{job.get('errorCode') or ''} {job.get('error') or ''}".strip()
            if status == NO_OP:
                raise ModelError("lipsync_no_face", detail or status)
            if status == "REJECTED":  # the inputs refused (format, length, plan limits)
                raise ModelError("bad_request", detail or status)
            if status == "FAILED":
                raise ModelError("provider_error", detail or status)
            if ctx.on_progress is not None and status and last[-1:] != [status]:
                await ctx.on_progress({"status": status, "task_id": job_id})
            last.append(status)
            return None

        return await poll(check, first_s=self.poll_s)

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
        return {"x-api-key": api_key}

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
