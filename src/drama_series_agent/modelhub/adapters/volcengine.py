"""Seedream 5.0 through Volcengine Ark's ``POST /images/generations``.

Checked against the Ark docs (docs.volcengine.com 82379/1541523 and the Seedream 5.0 pro / flash
guide) on 2026-10-21 (DECISIONS 同日「第 10 步」):

- The tier is **5.0 flash** (``doubao-seedream-5-0-flash-260915``): the cheapest of pro / flash /
  lite, and its 1K–2K range (921,600–4,624,220 pixels) covers our draft and delivery frames;
  lite starts at 3.7 MP.
- ``size`` as ``WxH`` (the frame rounded to 16, scaled into the pixel range); no ``n`` (group
  pictures are lite-only), so n pictures are n requests at once. No
  ``sequential_image_generation`` either: flash refuses it outright (400 ``InvalidParameter``,
  the live smoke on 2026-10-21).
- Up to 10 reference pictures as data URIs in ``image``.
- Always ``watermark: false`` (the API reference defaults it to true, the guide to false) and
  ``response_format: b64_json`` (URLs would need a second download and expire in 24 h).
- ``usage.generated_images`` is the billed count; a failed picture comes back as ``error``.
"""

from __future__ import annotations

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
from drama_series_agent.modelhub.adapters.images import (
    ImageApiAdapter,
    data_uri,
    fit_size,
    one_per_request,
    picture,
)

MIN_PIXELS = 921_600
MAX_PIXELS = 4_624_220


def size_for(w: int, h: int) -> tuple[int, int]:
    return fit_size(w, h, multiple=16, min_pixels=MIN_PIXELS, max_pixels=MAX_PIXELS)


def _code(body: str) -> str:
    try:
        return str((json.loads(body).get("error") or {}).get("code") or "")
    except (ValueError, AttributeError):
        return ""


def _error(status: int, body: str) -> ModelError:
    code = _code(body)
    if "SensitiveContent" in code:  # Input / OutputImage / InputText SensitiveContentDetected
        return ModelError("content_blocked", body[:300], status=status)
    if code == "SetLimitExceeded":  # the console's usage limit (安全体验模式): the model is paused
        return ModelError("quota_exceeded", body[:300], status=status)
    if "NotFound" in code:  # InvalidEndpointOrModel.NotFound comes as a 400 / 404
        return ModelError("model_not_found", body[:300], status=status)
    return error_for(status, body)


class SeedreamAdapter(ImageApiAdapter):
    async def run(self, req: ModelRequest, ctx: CallContext) -> ModelResult:
        w, h = size_for(int(req.params["width"]), int(req.params["height"]))
        body: dict[str, Any] = {
            **self._request_fields(),
            "model": self._model_id(),
            "prompt": req.prompt or "",
            "size": f"{w}x{h}",
            "response_format": "b64_json",
            "watermark": False,
        }
        refs = [data_uri(data, mime) for data, mime in self._refs(req)]
        if refs:
            body["image"] = refs[0] if len(refs) == 1 else refs
        headers = {"Authorization": f"Bearer {self._api_key()}"}

        async def one(i: int) -> ModelResult:
            async with self._client() as client:
                resp = await send(
                    client,
                    "POST",
                    "/images/generations",
                    json=body,
                    headers=headers,
                    max_retries=self.max_retries,
                    backoff_s=self.backoff_s,
                    errors=_error,
                )
            return self._result(resp.json())

        return await one_per_request(int(req.params.get("n", 1)), one)

    async def health(self) -> Health:
        """A request Ark must refuse (empty prompt, 1×1): a 400 means the key and model are
        good and nothing is made; Ark has no documented free "list models" call."""
        try:
            model = self._model_id()
            headers = {"Authorization": f"Bearer {self._api_key()}"}
            probe = {"model": model, "prompt": "", "size": "1x1", "watermark": False}
            async with self._client() as client:
                resp = await client.post("/images/generations", json=probe, headers=headers)
        except ModelError as exc:
            return Health(ok=False, detail=exc.code)
        except httpx.HTTPError as exc:
            return Health(ok=False, detail=f"network_error: {type(exc).__name__}")
        error = _error(resp.status_code, resp.text)
        if resp.is_success or (resp.status_code == 400 and error.code == "bad_request"):
            return Health(ok=True, models=[model])
        return Health(ok=False, detail=error.code)

    @staticmethod
    def _result(data: dict[str, Any]) -> ModelResult:
        top = data.get("error")
        items = data.get("data") or []
        files = [picture(str(d["b64_json"])) for d in items if d.get("b64_json")]
        if not files:
            failed = top or next((d["error"] for d in items if d.get("error")), None)
            if failed:
                raise _error(400, json.dumps({"error": failed}, ensure_ascii=False))
            raise ModelError("no_image", json.dumps(data, ensure_ascii=False)[:300])
        usage = data.get("usage") or {}
        billed = int(usage.get("generated_images") or len(files))
        return ModelResult(
            files=files,
            usage=Usage(images=billed, tokens_out=usage.get("output_tokens")),
            raw={"model": data.get("model")},
        )
