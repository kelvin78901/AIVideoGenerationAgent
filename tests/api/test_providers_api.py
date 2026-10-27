from __future__ import annotations

import io
from collections.abc import Iterator

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from loguru import logger

from drama_series_agent.api.app import create_app

LOCAL = "http://127.0.0.1"
CLIENT_HEADERS = {"X-Drama-Studio": "1"}  # required on non-GET requests


SECRET = "sk-deepseek-REAL-looking-0123456789"


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(), base_url=LOCAL, headers=CLIENT_HEADERS) as c:
        yield c


def _deepseek(client: TestClient) -> dict[str, object]:
    data = client.get("/api/v1/providers").json()
    return next(p for p in data["providers"] if p["id"] == "deepseek")


def test_list_providers(client: TestClient) -> None:
    data = client.get("/api/v1/providers").json()
    ids = [p["id"] for p in data["providers"]]
    assert ids[:2] == ["deepseek", "moonshot"] and "local_llm" in ids
    assert data["llm_ui_order"][0] == "deepseek/v4-pro"
    ds = _deepseek(client)
    assert ds["has_key"] is False and ds["key_source"] == "none" and ds["needs_key"] is True
    local = next(p for p in data["providers"] if p["id"] == "local_llm")
    assert local["needs_key"] is False and local["where"] == "local"


def test_set_and_delete_key_never_echoes_it(client: TestClient) -> None:
    sink = io.StringIO()
    handler = logger.add(sink, format="{message}")
    try:
        resp = client.post("/api/v1/providers/deepseek/key", json={"api_key": SECRET})
        assert resp.status_code == 200
        assert resp.json()["has_key"] is True and resp.json()["key_source"] == "keyring"
        assert SECRET not in resp.text
        assert SECRET not in client.get("/api/v1/providers").text
        resp = client.delete("/api/v1/providers/deepseek/key")
        assert resp.status_code == 200 and resp.json()["has_key"] is False
    finally:
        logger.remove(handler)
    assert SECRET not in sink.getvalue()


def test_key_errors(client: TestClient) -> None:
    assert client.post("/api/v1/providers/nope/key", json={"api_key": "x"}).status_code == 404
    resp = client.post("/api/v1/providers/local_llm/key", json={"api_key": "x"})
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "provider_needs_no_key"
    assert client.post("/api/v1/providers/deepseek/key", json={"api_key": ""}).status_code == 422
    assert client.post("/api/v1/providers/deepseek/key", json={"api_key": "   "}).status_code == 422


@respx.mock(assert_all_called=False)
def test_test_connection_ok_and_bad(client: TestClient, respx_mock: respx.MockRouter) -> None:
    respx_mock.route(host="127.0.0.1").pass_through()
    route = respx_mock.get("https://api.deepseek.com/v1/models")
    client.post("/api/v1/providers/deepseek/key", json={"api_key": SECRET})
    route.mock(return_value=httpx.Response(200, json={"data": [{"id": "deepseek-v4-pro"}]}))
    resp = client.post("/api/v1/providers/deepseek/test")
    assert resp.json() == {"ok": True, "detail": None, "models": ["deepseek-v4-pro"], "media": []}
    assert route.calls.last.request.headers["authorization"] == f"Bearer {SECRET}"
    assert SECRET not in resp.text

    route.mock(return_value=httpx.Response(401))
    assert client.post("/api/v1/providers/deepseek/test").json()["detail"] == "auth_failed"

    client.delete("/api/v1/providers/deepseek/key")
    assert client.post("/api/v1/providers/deepseek/test").json()["detail"] == "missing_key"
    assert client.post("/api/v1/providers/custom/test").status_code == 400


GEMINI_KEY = "g-REAL-looking-0123456789"


@respx.mock(assert_all_called=False)
def test_test_connection_checks_the_media_models_on_the_key(
    client: TestClient, respx_mock: respx.MockRouter
) -> None:
    respx_mock.route(host="127.0.0.1").pass_through()
    google = next(
        p for p in client.get("/api/v1/providers").json()["providers"] if p["id"] == "google_llm"
    )
    assert google["media"] == [
        {"key": "google/nano-banana-pro", "display": "Nano Banana Pro"},
        {"key": "google/nano-banana-2.1", "display": "Nano Banana 2.1"},
    ]

    client.post("/api/v1/providers/google_llm/key", json={"api_key": GEMINI_KEY})
    respx_mock.get("https://generativelanguage.googleapis.com/v1beta/openai/models").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "gemini-3.6-flash"}]})
    )
    image = respx_mock.get(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-pro-image"
    ).mock(return_value=httpx.Response(404))
    respx_mock.get(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-nano-banana-2.1"
    ).mock(return_value=httpx.Response(200, json={"name": "models/gemini-nano-banana-2.1"}))
    resp = client.post("/api/v1/providers/google_llm/test")
    assert resp.json()["ok"] is True
    assert resp.json()["media"] == [
        {
            "key": "google/nano-banana-pro",
            "display": "Nano Banana Pro",
            "ok": False,
            "detail": "model_not_found",
        },
        {"key": "google/nano-banana-2.1", "display": "Nano Banana 2.1", "ok": True, "detail": None},
    ]
    assert image.calls.last.request.headers["x-goog-api-key"] == GEMINI_KEY
    assert GEMINI_KEY not in resp.text
    client.delete("/api/v1/providers/google_llm/key")


def test_real_mode_uses_openai_compat_for_llms(client: TestClient) -> None:
    from drama_series_agent.modelhub.adapters.openai_compat import OpenAICompatAdapter

    registry = client.app.state.studio.registry  # type: ignore[attr-defined]
    registry.mock = False
    registry._adapters.clear()
    assert isinstance(registry.get("deepseek/v4-pro"), OpenAICompatAdapter)
    assert isinstance(registry.get("local/qwen3.6-27b"), OpenAICompatAdapter)


def test_real_mode_uses_the_media_adapters(client: TestClient) -> None:
    from drama_series_agent.modelhub.adapters.comfyui import ComfyUIAdapter
    from drama_series_agent.modelhub.adapters.google import GeminiImageAdapter
    from drama_series_agent.modelhub.adapters.local_python import LocalPythonAdapter
    from drama_series_agent.modelhub.adapters.minimax import MiniMaxSpeechAdapter
    from drama_series_agent.modelhub.adapters.minimax_video import MiniMaxVideoAdapter
    from drama_series_agent.modelhub.adapters.openai_images import OpenAIImageAdapter
    from drama_series_agent.modelhub.adapters.seedance import SeedanceAdapter
    from drama_series_agent.modelhub.adapters.volcengine import SeedreamAdapter
    from drama_series_agent.modelhub.registry import UnavailableAdapter

    registry = client.app.state.studio.registry  # type: ignore[attr-defined]
    registry.mock = False
    registry._adapters.clear()
    assert isinstance(registry.get("google/nano-banana-pro"), GeminiImageAdapter)
    assert isinstance(registry.get("openai/gpt-image-2"), OpenAIImageAdapter)
    assert isinstance(registry.get("volc/seedream-5.0"), SeedreamAdapter)
    assert isinstance(registry.get("minimax/speech-2.8-hd"), MiniMaxSpeechAdapter)
    assert isinstance(registry.get("minimax/speech-2.6-hd"), MiniMaxSpeechAdapter)
    minimax = next(
        p for p in client.get("/api/v1/providers").json()["providers"] if p["id"] == "minimax_llm"
    )
    assert [m["key"] for m in minimax["media"]] == [
        "minimax/h3-api",
        "minimax/h3-regenerate-2k",
        "minimax/context-ir",
        "minimax/speech-2.8-hd",
        "minimax/speech-2.6-hd",
    ]
    for key in ("minimax/h3-api", "minimax/h3-regenerate-2k", "minimax/context-ir"):
        assert isinstance(registry.get(key), MiniMaxVideoAdapter)
    assert isinstance(registry.get("volc/seedance-2.5"), SeedanceAdapter)
    assert isinstance(registry.get("kling/kling-3.0"), UnavailableAdapter)  # not yet
    for key in ("local/qwen3-tts", "local/indextts2", "local/rapidocr"):
        assert isinstance(registry.get(key), LocalPythonAdapter)
    for key in ("comfy/qwen-image", "comfy/qwen-image-edit", "comfy/qwen-image-edit-hq"):
        assert isinstance(registry.get(key), ComfyUIAdapter)
    assert isinstance(registry.get("comfy/h3"), ComfyUIAdapter)
    assert isinstance(registry.get("comfy/h3-fun-controlnet"), UnavailableAdapter)  # no folder yet


def test_real_local_runs_local_models_for_real_and_keeps_the_rest_mock(
    client: TestClient,
) -> None:
    """``DRAMA_REAL_LOCAL=1`` (the local smoke test): ComfyUI workflows and Python workers are
    real, API and writing models (local LLM servers included) stay Mock."""
    from drama_series_agent.modelhub.adapters.comfyui import ComfyUIAdapter
    from drama_series_agent.modelhub.adapters.local_python import LocalPythonAdapter
    from drama_series_agent.modelhub.adapters.mock import MockAdapter

    registry = client.app.state.studio.registry  # type: ignore[attr-defined]
    assert registry.mock and not registry.real_local
    registry.real_local = True
    registry._adapters.clear()
    assert isinstance(registry.get("comfy/qwen-image"), ComfyUIAdapter)
    assert isinstance(registry.get("local/rapidocr"), LocalPythonAdapter)
    for key in ("google/nano-banana-pro", "minimax/speech-2.8-hd", "local/qwen3.6-27b"):
        assert isinstance(registry.get(key), MockAdapter), key
