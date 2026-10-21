"""The three image API adapters against respx fakes: never the network, never money."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import httpx
import pytest
import respx

from drama_series_agent.core.config import get_config
from drama_series_agent.core.storage import BlobStore
from drama_series_agent.modelhub.adapters.base import CallContext, ModelError, ModelRequest
from drama_series_agent.modelhub.adapters.google import GeminiImageAdapter, image_size
from drama_series_agent.modelhub.adapters.images import fit_size
from drama_series_agent.modelhub.adapters.mock import solid_png
from drama_series_agent.modelhub.adapters.openai_images import OpenAIImageAdapter
from drama_series_agent.modelhub.adapters.openai_images import size_for as openai_size
from drama_series_agent.modelhub.adapters.volcengine import SeedreamAdapter
from drama_series_agent.modelhub.adapters.volcengine import size_for as seedream_size
from drama_series_agent.modelhub.media_adapters import media_adapter
from drama_series_agent.modelhub.pricing import cost_usd
from drama_series_agent.modelhub.registry import specs_from_config

KEYS = {"GEMINI_API_KEY": "g-SECRET", "OPENAI_API_KEY": "sk-SECRET", "ARK_API_KEY": "ark-SECRET"}
GEMINI = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-pro-image"
OPENAI = "https://api.openai.com/v1"
ARK = "https://ark.cn-beijing.volces.com/api/v3/images/generations"


def _png(w: int = 64, h: int = 112, rgb: tuple[int, int, int] = (200, 80, 40)) -> str:
    return base64.b64encode(solid_png(w, h, rgb)).decode("ascii")


@pytest.fixture
def store(tmp_path: Path) -> BlobStore:
    return BlobStore(tmp_path / "blobs")


def _adapter(key: str, store: BlobStore):  # type: ignore[no-untyped-def]
    spec = next(s for s in specs_from_config(get_config()) if s.key == key)
    adapter = media_adapter(spec, get_key=KEYS.get, store=store)
    adapter.backoff_s = 0  # type: ignore[attr-defined]
    return adapter


def _req(n: int = 1, refs: list[str] | None = None, seed: int | None = 7) -> ModelRequest:
    params: dict[str, object] = {"n": n, "width": 1080, "height": 1920, "aspect": "9:16"}
    if refs:
        params["refs"] = refs
    return ModelRequest(kind="image", prompt="雨夜的便利店门口", seed=seed, params=params)


# ---------------------------------------------------------------------------- sizes


def test_sizes_follow_the_frame_within_each_models_limits() -> None:
    assert openai_size(1080, 1920) == (1088, 1920)  # multiples of 16
    assert openai_size(1440, 2560) == (1440, 2560)
    assert openai_size(768, 768) == (816, 816)  # at least 655,360 pixels
    assert seedream_size(768, 768) == (960, 960)  # at least 921,600 pixels
    assert seedream_size(2976, 1248) == (2976, 1248)
    w, h = fit_size(4000, 4000, max_pixels=4_624_220)
    assert w * h <= 4_624_220 and w == h and w % 16 == 0
    assert fit_size(5000, 1000, max_edge=3840)[0] == 3840
    assert [image_size(*wh) for wh in ((768, 1366), (1080, 1920), (1080, 1080), (1440, 2560))] == [
        "1K",
        "2K",
        "2K",
        "2K",
    ]


def test_token_rates_price_what_was_used_and_fall_back_per_picture() -> None:
    spec = next(s for s in specs_from_config(get_config()) if s.key == "openai/gpt-image-2")
    from drama_series_agent.modelhub.adapters.base import Usage

    used = Usage(images=1, tokens={"text_in": 1000, "image_in": 2000, "image_out": 7000})
    assert cost_usd(spec.pricing, used) == pytest.approx(0.005 + 0.016 + 0.21)
    unknown = Usage(images=2, tokens={"audio_out": 5})
    assert cost_usd(spec.pricing, unknown) == pytest.approx(0.46)
    assert cost_usd(spec.pricing, Usage(images=2)) == pytest.approx(0.46)


# ---------------------------------------------------------------------------- Gemini


def _gemini_answer(b64: str) -> dict[str, object]:
    return {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": "构图想法", "thought": True},
                        {
                            "inlineData": {"mimeType": "image/png", "data": _png(8, 8)},
                            "thought": True,
                        },
                        {"text": "好的"},
                        {"inlineData": {"mimeType": "image/png", "data": b64}},
                    ]
                },
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 600,
            "candidatesTokenCount": 1130,
            "thoughtsTokenCount": 200,
            "promptTokensDetails": [
                {"modality": "TEXT", "tokenCount": 40},
                {"modality": "IMAGE", "tokenCount": 560},
            ],
            "candidatesTokensDetails": [
                {"modality": "IMAGE", "tokenCount": 1120},
                {"modality": "TEXT", "tokenCount": 10},
            ],
        },
        "modelVersion": "gemini-3-pro-image",
    }


@respx.mock
async def test_gemini_one_request_per_picture_with_refs_and_tokens(store: BlobStore) -> None:
    ref = store.put_bytes(solid_png(32, 32, (1, 2, 3)))
    route = respx.post(f"{GEMINI}:generateContent").mock(
        return_value=httpx.Response(200, json=_gemini_answer(_png(1536, 2752)))
    )
    adapter = _adapter("google/nano-banana-pro", store)
    result = await adapter.run(_req(n=2, refs=[ref]), CallContext())

    assert route.call_count == 2
    bodies = [json.loads(c.request.content) for c in route.calls]
    assert {b["generationConfig"]["seed"] for b in bodies} == {7, 8}
    config = bodies[0]["generationConfig"]
    assert config["imageConfig"] == {"aspectRatio": "9:16", "imageSize": "2K"}
    assert config["responseModalities"] == ["TEXT", "IMAGE"]
    parts = bodies[0]["contents"][0]["parts"]
    assert parts[0] == {"text": "雨夜的便利店门口"}
    assert parts[1]["inlineData"]["mimeType"] == "image/png"
    assert base64.b64decode(parts[1]["inlineData"]["data"]) == solid_png(32, 32, (1, 2, 3))
    assert route.calls.last.request.headers["x-goog-api-key"] == "g-SECRET"

    assert [(f.w, f.h, f.mime) for f in result.files] == [(1536, 2752, "image/png")] * 2
    assert result.usage.images == 2
    assert result.usage.tokens == {
        "text_in": 80,
        "image_in": 1120,
        "text_out": 420,
        "image_out": 2240,
    }
    cost = cost_usd(adapter.spec.pricing, result.usage)
    assert cost == pytest.approx((80 + 1120) * 2 / 1e6 + 420 * 12 / 1e6 + 2240 * 120 / 1e6)
    assert adapter.estimate(_req(n=2)).cost_usd == pytest.approx(0.268)


@respx.mock
async def test_gemini_partial_success_keeps_the_pictures_made(store: BlobStore) -> None:
    respx.post(f"{GEMINI}:generateContent").mock(
        side_effect=[
            httpx.Response(200, json=_gemini_answer(_png())),
            httpx.Response(400, json={"error": {"message": "bad"}}),
        ]
    )
    result = await _adapter("google/nano-banana-pro", store).run(_req(n=2), CallContext())
    assert len(result.files) == 1 and result.usage.images == 1
    assert result.raw == {"requests": 2, "failed": ["bad_request"]}


@respx.mock
async def test_gemini_blocked_and_empty_answers(store: BlobStore) -> None:
    route = respx.post(f"{GEMINI}:generateContent")
    adapter = _adapter("google/nano-banana-pro", store)
    route.mock(return_value=httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}}))
    with pytest.raises(ModelError) as exc:
        await adapter.run(_req(), CallContext())
    assert exc.value.code == "content_blocked"
    text_only = {"candidates": [{"content": {"parts": [{"text": "no"}]}, "finishReason": "STOP"}]}
    route.mock(return_value=httpx.Response(200, json=text_only))
    with pytest.raises(ModelError) as exc:
        await adapter.run(_req(), CallContext())
    assert exc.value.code == "no_image"


@respx.mock
async def test_gemini_retries_rate_limits(store: BlobStore) -> None:
    route = respx.post(f"{GEMINI}:generateContent").mock(
        side_effect=[httpx.Response(429), httpx.Response(200, json=_gemini_answer(_png()))]
    )
    result = await _adapter("google/nano-banana-pro", store).run(_req(seed=None), CallContext())
    assert route.call_count == 2 and len(result.files) == 1
    assert "seed" not in json.loads(route.calls.last.request.content)["generationConfig"]


# ---------------------------------------------------------------------------- GPT Image 2


def _openai_answer(n: int) -> dict[str, object]:
    return {
        "created": 1,
        "data": [{"b64_json": _png(1088, 1920)} for _ in range(n)],
        "usage": {
            "input_tokens": 1050,
            "output_tokens": 15000,
            "input_tokens_details": {"text_tokens": 50, "image_tokens": 1000},
        },
    }


@respx.mock
async def test_gpt_image_generations_without_refs(store: BlobStore) -> None:
    route = respx.post(f"{OPENAI}/images/generations").mock(
        return_value=httpx.Response(200, json=_openai_answer(2))
    )
    adapter = _adapter("openai/gpt-image-2", store)
    result = await adapter.run(_req(n=2), CallContext())
    sent = json.loads(route.calls.last.request.content)
    assert sent == {
        "quality": "high",
        "model": "gpt-image-2",
        "prompt": "雨夜的便利店门口",
        "n": 2,
        "size": "1088x1920",
    }
    assert route.calls.last.request.headers["authorization"] == "Bearer sk-SECRET"
    assert [(f.w, f.h) for f in result.files] == [(1088, 1920)] * 2
    assert result.usage.tokens == {"text_in": 50, "image_in": 1000, "image_out": 15000}
    assert cost_usd(adapter.spec.pricing, result.usage) == pytest.approx(
        50 * 5 / 1e6 + 1000 * 8 / 1e6 + 15000 * 30 / 1e6
    )
    # The estimate prices a 1088×1920 high picture: about 7.5k output tokens each.
    est = adapter.estimate(_req(n=2, refs=["a" * 64])).cost_usd
    assert est == pytest.approx(2 * 7521 * 30 / 1e6 + 2000 * 8 / 1e6, abs=0.001)


@respx.mock
async def test_gpt_image_edits_with_refs_as_multipart(store: BlobStore) -> None:
    refs = [store.put_bytes(solid_png(16, 16, (i, i, i))) for i in (10, 20)]
    route = respx.post(f"{OPENAI}/images/edits").mock(
        return_value=httpx.Response(200, json=_openai_answer(1))
    )
    await _adapter("openai/gpt-image-2", store).run(_req(refs=refs), CallContext())
    request = route.calls.last.request
    assert request.headers["content-type"].startswith("multipart/form-data")
    body = request.content
    assert body.count(b'name="image[]"') == 2
    assert b'name="size"\r\n\r\n1088x1920' in body and b'name="quality"\r\n\r\nhigh' in body
    assert b"input_fidelity" not in body


@respx.mock
async def test_gpt_image_moderation_is_content_blocked(store: BlobStore) -> None:
    blocked = {"error": {"code": "moderation_blocked", "message": "rejected"}}
    respx.post(f"{OPENAI}/images/generations").mock(return_value=httpx.Response(400, json=blocked))
    with pytest.raises(ModelError) as exc:
        await _adapter("openai/gpt-image-2", store).run(_req(), CallContext())
    assert exc.value.code == "content_blocked"


# ---------------------------------------------------------------------------- Seedream


def _ark_answer(b64: str | None = None, error: dict[str, str] | None = None) -> dict[str, object]:
    item: dict[str, object] = {"b64_json": b64, "size": "1088x1920"} if b64 else {"error": error}
    return {
        "model": "doubao-seedream-5-0-flash-260915",
        "data": [item],
        "usage": {"generated_images": 1 if b64 else 0, "output_tokens": 8000},
    }


@respx.mock
async def test_seedream_no_watermark_b64_and_one_request_per_picture(store: BlobStore) -> None:
    ref = store.put_bytes(solid_png(16, 16, (5, 5, 5)))
    route = respx.post(ARK).mock(return_value=httpx.Response(200, json=_ark_answer(_png())))
    adapter = _adapter("volc/seedream-5.0", store)
    result = await adapter.run(_req(n=2, refs=[ref]), CallContext())
    assert route.call_count == 2
    sent = json.loads(route.calls.last.request.content)
    assert sent["model"] == "doubao-seedream-5-0-flash-260915"
    assert sent["watermark"] is False and sent["response_format"] == "b64_json"
    assert sent["size"] == "1088x1920" and sent["sequential_image_generation"] == "disabled"
    assert sent["image"].startswith("data:image/png;base64,")
    assert route.calls.last.request.headers["authorization"] == "Bearer ark-SECRET"
    assert len(result.files) == 2 and result.usage.images == 2
    assert cost_usd(adapter.spec.pricing, result.usage) == pytest.approx(2 * 0.12 / 7.1)


@respx.mock
async def test_seedream_sensitive_content_and_failed_items(store: BlobStore) -> None:
    route = respx.post(ARK)
    adapter = _adapter("volc/seedream-5.0", store)
    sensitive = {"error": {"code": "OutputImageSensitiveContentDetected", "message": "x"}}
    route.mock(return_value=httpx.Response(400, json=sensitive))
    with pytest.raises(ModelError) as exc:
        await adapter.run(_req(), CallContext())
    assert exc.value.code == "content_blocked"
    item = _ark_answer(error={"code": "InputTextSensitiveContentDetected", "message": "x"})
    route.mock(return_value=httpx.Response(200, json=item))
    with pytest.raises(ModelError) as exc:
        await adapter.run(_req(), CallContext())
    assert exc.value.code == "content_blocked"


# ---------------------------------------------------------------------------- health


@respx.mock
async def test_health_checks_are_free(store: BlobStore) -> None:
    gemini = respx.get(GEMINI).mock(return_value=httpx.Response(200, json={"name": "x"}))
    health = await _adapter("google/nano-banana-pro", store).health()
    assert health.ok and health.models == ["gemini-3-pro-image"]
    assert gemini.calls.last.request.headers["x-goog-api-key"] == "g-SECRET"
    gemini.mock(return_value=httpx.Response(404))
    assert (await _adapter("google/nano-banana-pro", store).health()).detail == "model_not_found"

    respx.get(f"{OPENAI}/models/gpt-image-2").mock(return_value=httpx.Response(401))
    assert (await _adapter("openai/gpt-image-2", store).health()).detail == "auth_failed"

    ark = respx.post(ARK)
    invalid = {"error": {"code": "InvalidParameter", "message": "size"}}
    ark.mock(return_value=httpx.Response(400, json=invalid))
    assert (await _adapter("volc/seedream-5.0", store).health()).ok
    probe = json.loads(ark.calls.last.request.content)
    assert probe["prompt"] == "" and probe["size"] == "1x1"
    missing = {"error": {"code": "InvalidEndpointOrModel.NotFound", "message": "x"}}
    ark.mock(return_value=httpx.Response(404, json=missing))
    assert (await _adapter("volc/seedream-5.0", store).health()).detail == "model_not_found"

    spec = next(s for s in specs_from_config(get_config()) if s.key == "volc/seedream-5.0")
    no_key = SeedreamAdapter(spec, get_key=lambda _name: None, store=store)
    assert (await no_key.health()).detail == "missing_key"


def test_adapter_classes() -> None:
    store = BlobStore(Path("unused"))
    assert isinstance(_adapter("google/nano-banana-pro", store), GeminiImageAdapter)
    assert isinstance(_adapter("openai/gpt-image-2", store), OpenAIImageAdapter)
    assert isinstance(_adapter("volc/seedream-5.0", store), SeedreamAdapter)
