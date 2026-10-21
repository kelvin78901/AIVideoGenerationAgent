"""GPT Image 2 (``gpt-image-2``) through OpenAI's Image API.

Checked against developers.openai.com on 2026-10-21 (DECISIONS 同日「第 10 步」):

- No reference pictures: ``POST /images/generations`` (JSON). With references:
  ``POST /images/edits`` (multipart, one ``image[]`` part each). ``n`` pictures in one request.
- ``size`` is any ``WxH`` with both edges multiples of 16, the long edge ≤ 3840, at most 3:1 and
  655,360–8,294,400 pixels, so the frame is sent as is, rounded up to 16 (1080×1920 →
  1088×1920).
- Pictures always come back as ``b64_json``; ``input_fidelity`` must not be sent (gpt-image-2
  always reads references at high fidelity); ``quality`` comes from ``caps.request``.
- Billed by tokens (``usage``); the estimate prices the output tokens a picture of that size
  takes (``caps.est_tokens_per_mp``) and ``caps.est_ref_tokens`` per reference.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from drama_series_agent.modelhub.adapters.base import (
    CallContext,
    Estimate,
    Health,
    ModelError,
    ModelRequest,
    ModelResult,
    Usage,
)
from drama_series_agent.modelhub.adapters.http import error_for, send
from drama_series_agent.modelhub.adapters.images import ImageApiAdapter, fit_size, picture
from drama_series_agent.modelhub.adapters.mock import estimate_tokens
from drama_series_agent.modelhub.pricing import cost_usd

MIN_PIXELS = 655_360
MAX_PIXELS = 8_294_400
MAX_EDGE = 3840


def size_for(w: int, h: int) -> tuple[int, int]:
    return fit_size(
        w, h, multiple=16, min_pixels=MIN_PIXELS, max_pixels=MAX_PIXELS, max_edge=MAX_EDGE
    )


def _errors(status: int, body: str) -> ModelError:
    try:
        code = (json.loads(body).get("error") or {}).get("code")
    except (ValueError, AttributeError):
        code = None
    if code == "moderation_blocked":
        return ModelError("content_blocked", body[:300], status=status)
    return error_for(status, body)


def usage_of(usage: dict[str, Any], images: int) -> Usage:
    details = usage.get("input_tokens_details") or {}
    tokens_in = int(usage.get("input_tokens") or 0)
    tokens_out = int(usage.get("output_tokens") or 0)
    image_in = int(details.get("image_tokens") or 0)
    text_in = int(details.get("text_tokens") or tokens_in - image_in)
    tokens = {"text_in": text_in, "image_in": image_in, "image_out": tokens_out}
    return Usage(
        images=images,
        tokens_in=tokens_in or None,
        tokens_out=tokens_out or None,
        tokens={k: v for k, v in tokens.items() if v} if tokens_out else None,
    )


class OpenAIImageAdapter(ImageApiAdapter):
    def estimate(self, req: ModelRequest) -> Estimate:
        rates = self.spec.pricing.token_rates
        extra = self.spec.caps.model_extra or {}
        per_mp = extra.get("est_tokens_per_mp")
        if not rates or not per_mp:
            return super().estimate(req)
        n = int(req.params.get("n", 1))
        w, h = size_for(int(req.params["width"]), int(req.params["height"]))
        refs = len(req.params.get("refs") or [])
        tokens = {
            "text_in": estimate_tokens(req.text()),
            "image_in": refs * int(extra.get("est_ref_tokens") or 0),
            "image_out": n * round(w * h / 1e6 * float(per_mp)),
        }
        usage = Usage(images=n, tokens={k: v for k, v in tokens.items() if v})
        return Estimate(cost_usd=cost_usd(self.spec.pricing, usage), seconds=60.0)

    async def run(self, req: ModelRequest, ctx: CallContext) -> ModelResult:
        w, h = size_for(int(req.params["width"]), int(req.params["height"]))
        fields: dict[str, Any] = {
            **self._request_fields(),
            "model": self._model_id(),
            "prompt": req.prompt or "",
            "n": int(req.params.get("n", 1)),
            "size": f"{w}x{h}",
        }
        refs = self._refs(req)
        headers = {"Authorization": f"Bearer {self._api_key()}"}
        async with self._client() as client:
            if refs:
                files = [
                    ("image[]", (f"ref{i}.{mime.split('/')[-1]}", data, mime))
                    for i, (data, mime) in enumerate(refs)
                ]
                data = {k: str(v) for k, v in fields.items()}
                resp = await self._send(client, "/images/edits", headers, data=data, files=files)
            else:
                resp = await self._send(client, "/images/generations", headers, json=fields)
        body = resp.json()
        files_out = [picture(str(d.get("b64_json", ""))) for d in body.get("data") or []]
        if not files_out:
            raise ModelError("no_image", json.dumps(body)[:300])
        return ModelResult(
            files=files_out,
            usage=usage_of(body.get("usage") or {}, len(files_out)),
            raw={"created": body.get("created"), "size": f"{w}x{h}"},
        )

    async def health(self) -> Health:
        """``GET /models/{model}``: the key works and the model id exists (free)."""
        try:
            model = self._model_id()
            headers = {"Authorization": f"Bearer {self._api_key()}"}
            async with self._client() as client:
                resp = await client.get(f"/models/{model}", headers=headers)
        except ModelError as exc:
            return Health(ok=False, detail=exc.code)
        except httpx.HTTPError as exc:
            return Health(ok=False, detail=f"network_error: {type(exc).__name__}")
        if not resp.is_success:
            return Health(ok=False, detail=error_for(resp.status_code, resp.text).code)
        return Health(ok=True, models=[model])

    async def _send(
        self, client: httpx.AsyncClient, path: str, headers: dict[str, str], **kwargs: Any
    ) -> httpx.Response:
        return await send(
            client,
            "POST",
            path,
            headers=headers,
            max_retries=self.max_retries,
            backoff_s=self.backoff_s,
            errors=_errors,
            **kwargs,
        )
