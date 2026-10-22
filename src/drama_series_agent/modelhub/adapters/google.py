"""Nano Banana Pro (``gemini-3-pro-image``) through Gemini's native ``generateContent``.

Checked against ai.google.dev on 2026-10-21 (DECISIONS 同日「第 10 步」):

- ``POST {base}/models/{model}:generateContent`` with ``x-goog-api-key``; the base is the native
  ``v1beta`` root, not the account's OpenAI-compatible one.
- One picture per request: n pictures are n requests at once, seeds ``seed + i``.
- ``generationConfig.imageConfig``: the frame's aspect as is (every output-spec aspect is
  supported) and the smallest ``imageSize`` (1K / 2K / 4K) that covers the frame. The model
  returns its own pixels for that tier (9:16 at 2K is 1536×2752), recorded as they are.
- Up to 14 reference pictures go inline after the prompt.
- ``thought`` parts (interim pictures while it thinks) are skipped.
- Billed by tokens (``usageMetadata``, thinking included); 1K and 2K pictures are 1120 output
  tokens, the per-picture price used for estimates.
"""

from __future__ import annotations

import base64
import json
from typing import Any

import httpx

from drama_series_agent.modelhub.adapters.base import (
    CallContext,
    Health,
    ModelError,
    ModelRequest,
    ModelResult,
    Usage,
)
from drama_series_agent.modelhub.adapters.http import error_for, send
from drama_series_agent.modelhub.adapters.images import ImageApiAdapter, one_per_request, picture

# Nominal pixels per image size tier; a frame takes the smallest tier that covers it (2% slack:
# 9:16 at 1K is 768×1376, a hair over 1024²).
IMAGE_SIZES = (("1K", 1024 * 1024), ("2K", 2048 * 2048), ("4K", 4096 * 4096))
BLOCKED = {"SAFETY", "IMAGE_SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "RECITATION"}


def image_size(w: int, h: int) -> str:
    need = w * h * 0.98
    return next((name for name, px in IMAGE_SIZES if px >= need), IMAGE_SIZES[-1][0])


def _modalities(details: list[dict[str, Any]] | None) -> dict[str, int]:
    out: dict[str, int] = {}
    for d in details or []:
        modality = str(d.get("modality", "")).lower()
        if modality in ("text", "image") and d.get("tokenCount"):
            out[modality] = out.get(modality, 0) + int(d["tokenCount"])
    return out


def usage_of(meta: dict[str, Any], images: int) -> Usage:
    """``usageMetadata`` by kind; thinking is billed as text output."""
    prompt = _modalities(meta.get("promptTokensDetails"))
    cands = _modalities(meta.get("candidatesTokensDetails"))
    thoughts = int(meta.get("thoughtsTokenCount") or 0)
    tokens = {
        "text_in": prompt.get("text", 0),
        "image_in": prompt.get("image", 0),
        "text_out": cands.get("text", 0) + thoughts,
        "image_out": cands.get("image", 0),
    }
    tokens = {k: v for k, v in tokens.items() if v}
    return Usage(
        images=images,
        tokens_in=meta.get("promptTokenCount"),
        tokens_out=(meta.get("candidatesTokenCount") or 0) + thoughts or None,
        # Without the per-modality detail the tokens cannot be priced: bill per picture.
        tokens=tokens if cands.get("image") else None,
    )


class GeminiImageAdapter(ImageApiAdapter):
    async def run(self, req: ModelRequest, ctx: CallContext) -> ModelResult:
        model = self._model_id()
        w, h = int(req.params["width"]), int(req.params["height"])
        parts: list[dict[str, Any]] = [{"text": req.prompt or ""}]
        for data, mime in self._refs(req):
            parts.append(
                {"inlineData": {"mimeType": mime, "data": base64.b64encode(data).decode("ascii")}}
            )
        config: dict[str, Any] = {
            "responseModalities": ["TEXT", "IMAGE"],
            "imageConfig": {
                "aspectRatio": str(req.params["aspect"]),
                "imageSize": image_size(w, h),
            },
        }
        headers = {"x-goog-api-key": self._api_key(), "Content-Type": "application/json"}

        async def one(i: int) -> ModelResult:
            body = {
                "contents": [{"role": "user", "parts": parts}],
                "generationConfig": (
                    config if req.seed is None else {**config, "seed": (req.seed + i) % 2**31}
                ),
            }
            async with self._client() as client:
                resp = await send(
                    client,
                    "POST",
                    f"/models/{model}:generateContent",
                    json=body,
                    headers=headers,
                    max_retries=self.max_retries,
                    backoff_s=self.backoff_s,
                )
            return self._result(resp.json())

        return await one_per_request(int(req.params.get("n", 1)), one)

    async def health(self) -> Health:
        """``GET /models/{model}``: the key works and the model id exists (free)."""
        try:
            model = self._model_id()
            async with self._client() as client:
                resp = await client.get(
                    f"/models/{model}", headers={"x-goog-api-key": self._api_key()}
                )
        except ModelError as exc:
            return Health(ok=False, detail=exc.code)
        except httpx.HTTPError as exc:
            return Health(ok=False, detail=f"network_error: {type(exc).__name__}")
        if not resp.is_success:
            return Health(ok=False, detail=error_for(resp.status_code, resp.text).code)
        return Health(ok=True, models=[model])

    @staticmethod
    def _result(data: dict[str, Any]) -> ModelResult:
        candidates = data.get("candidates") or []
        content = (candidates[0].get("content") or {}) if candidates else {}
        files = [
            picture(str(inline.get("data", "")))
            for part in content.get("parts") or []
            if not part.get("thought")
            and (inline := part.get("inlineData") or part.get("inline_data"))
        ]
        if not files:
            blocked = (data.get("promptFeedback") or {}).get("blockReason")
            reason = blocked or (candidates[0].get("finishReason") if candidates else None)
            if blocked or reason in BLOCKED:
                raise ModelError("content_blocked", str(reason))
            raise ModelError("no_image", json.dumps(data, ensure_ascii=False)[:300])
        usage = usage_of(data.get("usageMetadata") or {}, len(files))
        return ModelResult(files=files, usage=usage, raw={"model": data.get("modelVersion")})
