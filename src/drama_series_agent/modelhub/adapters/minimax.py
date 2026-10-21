"""MiniMax speech: T2A v2 (``speech-2.8-hd``, ``speech-2.6-hd`` for whispers) and voice design.

Checked against platform.minimax.io / platform.minimax.cn on 2026-10-21 (DECISIONS 同日
「第 11 步」):

- Base URL from the ``minimax_llm`` account: ``https://api.minimax.io/v1`` (international) or
  ``https://api.minimax.cn/v1`` (China; a different account and key). Bearer key.
- ``kind="tts"``: ``POST /t2a_v2``, non-streaming, ``output_format: hex``; WAV at 44.1 kHz mono
  (``media/audio.py`` levels and resamples it). ``voice_setting`` takes the request's
  ``voice_id``, ``emotion`` and ``vol`` (``config/voice.yaml``); ``whisper`` exists on 2.6 only.
- ``kind="voice_design"``: ``POST /voice_design`` with the description as ``prompt`` and the
  lines as ``preview_text`` (≤ 500 characters); answers a ``voice_id`` and a hex trial clip.
- Errors come back as HTTP 200 with ``base_resp.status_code`` ≠ 0; rate limits and timeouts are
  retried.
- Billing: T2A by ``extra_info.usage_characters``; the $3 design fee when a designed voice is
  first used (``extra_info.usage_voice_count``), not when it is designed; the design's trial clip
  per character (``extras.design_preview_char``).
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from drama_series_agent.modelhub.adapters.base import (
    CallContext,
    Estimate,
    Health,
    ModelError,
    ModelRequest,
    ModelResult,
    ModelSpec,
    OutputFile,
    Usage,
)
from drama_series_agent.modelhub.adapters.http import KeyGetter, retry_delay, send
from drama_series_agent.modelhub.pricing import cost_usd
from drama_series_agent.utils.llm_client import normalize_base_url

SAMPLE_RATE = 44100
PREVIEW_MAX = 500
# base_resp.status_code → (our code, retry?)
ERRORS: dict[int, tuple[str, bool]] = {
    1000: ("provider_error", True),
    1001: ("timeout", True),
    1002: ("rate_limited", True),
    1004: ("auth_failed", False),
    1008: ("insufficient_balance", False),
    1013: ("provider_error", True),
    1026: ("content_blocked", False),
    1027: ("content_blocked", False),
    1039: ("rate_limited", True),
    1041: ("rate_limited", True),
    1042: ("bad_request", False),
    2013: ("bad_request", False),
    2042: ("voice_not_found", False),
    2045: ("rate_limited", True),
    2049: ("auth_failed", False),
    2054: ("voice_not_found", False),
    2056: ("rate_limited", False),  # the 5-hour usage window: waiting seconds will not help
}


def billed_chars(text: str) -> int:
    """What MiniMax is expected to bill, on the safe side: anything not ASCII (CJK characters,
    full-width punctuation) counts twice. An estimate: the answer's ``usage_characters`` is the
    bill, and a confirmed job may not spend more than its estimate."""
    return sum(1 if ord(ch) < 128 else 2 for ch in text)


def _mime(data: bytes) -> str:
    if data[:4] == b"RIFF":
        return "audio/wav"
    if data[:4] == b"fLaC":
        return "audio/flac"
    if data[:3] == b"ID3" or data[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return "audio/mpeg"
    return "application/octet-stream"


def _audio(hex_audio: Any) -> bytes:
    try:
        data = bytes.fromhex(str(hex_audio or ""))
    except ValueError as exc:
        raise ModelError("invalid_response", f"audio is not hex: {exc}") from exc
    if not data:
        raise ModelError("no_audio", "empty audio")
    return data


class MiniMaxSpeechAdapter:
    def __init__(
        self,
        spec: ModelSpec,
        *,
        get_key: KeyGetter,
        transport: httpx.AsyncBaseTransport | None = None,
        max_retries: int = 2,
        backoff_s: float = 2.0,
        request_timeout_s: float = 120.0,
        **_: Any,  # ``store``: speech needs no reference files
    ) -> None:
        self.spec = spec
        self._get_key = get_key
        self._base_url = normalize_base_url(spec.base_url or "")
        self._transport = transport
        self.max_retries = max_retries
        self.backoff_s = backoff_s
        self.request_timeout_s = request_timeout_s

    @property
    def key(self) -> str:
        return self.spec.key

    # ------------------------------------------------------------------ protocol

    def estimate(self, req: ModelRequest) -> Estimate:
        text = req.text()
        if req.kind == "voice_design":
            n = billed_chars(text[:PREVIEW_MAX])
            usage = Usage(calls={"design_preview_char": n})
        else:
            design = {"voice_design": 1} if req.params.get("charge_design") else None
            usage = Usage(chars=billed_chars(text), calls=design)
        return Estimate(
            cost_usd=cost_usd(self.spec.pricing, usage),
            seconds=5.0 + len(text) * 0.1,
            priced=self.spec.pricing.known,
        )

    async def run(self, req: ModelRequest, ctx: CallContext) -> ModelResult:
        if req.kind == "voice_design":
            return await self._design(req)
        return await self._speak(req)

    async def health(self) -> Health:
        """``POST /get_voice`` (a free listing): the key works. MiniMax has no free call that
        checks a speech model id."""
        try:
            await self._post("/get_voice", {"voice_type": "voice_generation"})
        except ModelError as exc:
            return Health(ok=False, detail=exc.code)
        return Health(ok=True, models=[self.spec.model_id] if self.spec.model_id else [])

    # ------------------------------------------------------------------ calls

    async def _speak(self, req: ModelRequest) -> ModelResult:
        voice_id = req.params.get("voice_id")
        if not voice_id:
            raise ModelError("voice_id_missing", "a MiniMax voice needs its voice_id")
        voice: dict[str, Any] = {"voice_id": str(voice_id), "speed": 1, "vol": 1, "pitch": 0}
        for name in ("emotion", "vol", "speed", "pitch"):
            if req.params.get(name) is not None:
                voice[name] = req.params[name]
        body = {
            **self._request_fields(),
            "model": self._model_id(),
            "text": req.prompt or "",
            "stream": False,
            "voice_setting": voice,
            "audio_setting": {"sample_rate": SAMPLE_RATE, "format": "wav", "channel": 1},
            "output_format": "hex",
        }
        data = await self._post("/t2a_v2", body)
        audio = _audio((data.get("data") or {}).get("audio"))
        extra = data.get("extra_info") or {}
        voices = int(extra.get("usage_voice_count") or 0)
        length_ms = extra.get("audio_length")
        duration = float(length_ms) / 1000 if length_ms else None
        return ModelResult(
            files=[OutputFile(role="audio", mime=_mime(audio), data=audio, duration_s=duration)],
            usage=Usage(
                chars=int(extra.get("usage_characters") or billed_chars(req.prompt or "")),
                output_seconds=duration,
                calls={"voice_design": voices} if voices else None,
            ),
            raw={"trace_id": data.get("trace_id")},
        )

    async def _design(self, req: ModelRequest) -> ModelResult:
        preview = (req.prompt or "")[:PREVIEW_MAX]
        body = {"prompt": str(req.params.get("design") or ""), "preview_text": preview}
        data = await self._post("/voice_design", body)
        voice_id = data.get("voice_id")
        if not voice_id:
            raise ModelError("voice_design_failed", "no voice_id in the answer")
        audio = _audio(data.get("trial_audio"))
        return ModelResult(
            json={"voice_id": str(voice_id)},
            files=[OutputFile(role="audio", mime=_mime(audio), data=audio)],
            usage=Usage(calls={"design_preview_char": billed_chars(preview)}),
            raw={"trace_id": data.get("trace_id")},
        )

    # ------------------------------------------------------------------ internals

    def _model_id(self) -> str:
        if not self.spec.model_id:
            raise ModelError("model_id_missing", f"{self.key}: fill model_id in providers.yaml")
        return self.spec.model_id

    def _request_fields(self) -> dict[str, Any]:
        """``caps.request``: fields every T2A request carries (``language_boost``)."""
        return dict((self.spec.caps.model_extra or {}).get("request") or {})

    def _headers(self) -> dict[str, str]:
        name = self.spec.key_name
        api_key = self._get_key(name) if name else None
        if not api_key:
            raise ModelError("missing_key", name or self.key)
        return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    async def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        """One call; a ``base_resp`` error that is worth retrying is retried like a 429."""
        if not self._base_url:
            raise ModelError("base_url_missing", self.key)
        headers = self._headers()
        attempt = 0
        async with httpx.AsyncClient(
            base_url=self._base_url, timeout=self.request_timeout_s, transport=self._transport
        ) as client:
            while True:
                resp = await send(
                    client,
                    "POST",
                    path,
                    json=body,
                    headers=headers,
                    max_retries=self.max_retries,
                    backoff_s=self.backoff_s,
                )
                try:
                    data: dict[str, Any] = resp.json()
                except ValueError:
                    raise ModelError("invalid_response", resp.text[:300]) from None
                base = data.get("base_resp") or {}
                status = int(base.get("status_code") or 0)
                if status == 0:
                    return data
                code, retry = ERRORS.get(status, ("provider_error", False))
                error = ModelError(code, f"{status}: {base.get('status_msg', '')}"[:300])
                attempt += 1
                if not retry or attempt > self.max_retries:
                    raise error
                await asyncio.sleep(retry_delay(attempt, None, self.backoff_s))
