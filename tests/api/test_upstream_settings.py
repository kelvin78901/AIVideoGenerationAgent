"""The upstream /api/series/settings endpoint must never hand stored keys to the browser."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from drama_series_agent.adapters.config import config_manager
from drama_series_agent.api.app import create_app

LLM_KEY = "sk-upstream-llm-SECRET-0001"
COMFY_KEY = "comfy-SECRET-0002"
RH_KEY = "rh-SECRET-0003"


@pytest.fixture
def client() -> Iterator[TestClient]:
    config_manager.reload()  # picks up the per-test DRAMA_SERIES_ROOT (empty config)
    config_manager.set_llm_config(LLM_KEY, "https://api.deepseek.com/v1", "deepseek-chat")
    config_manager.set_comfyui_config(comfyui_api_key=COMFY_KEY, runninghub_api_key=RH_KEY)
    config_manager.save()
    headers = {"X-Drama-Studio": "1"}
    with TestClient(create_app(), base_url="http://127.0.0.1", headers=headers) as c:
        yield c
    config_manager.reload()


def test_get_settings_reports_keys_without_values(client: TestClient) -> None:
    resp = client.get("/api/series/settings")
    assert resp.status_code == 200
    for secret in (LLM_KEY, COMFY_KEY, RH_KEY):
        assert secret not in resp.text
    data = resp.json()
    assert data["llm"]["api_key"] == "" and data["llm"]["api_key_set"] is True
    assert data["workflow"]["comfyui_api_key"] is None
    assert data["workflow"]["comfyui_api_key_set"] is True
    assert data["workflow"]["runninghub_api_key_set"] is True


def test_saving_with_empty_keys_keeps_the_stored_ones(client: TestClient) -> None:
    body = {
        "llm": {"api_key": "", "base_url": "https://api.deepseek.com/v1", "model": "deepseek-v4"},
        "workflow": {"comfyui_url": "http://127.0.0.1:8188", "comfyui_api_key": None},
    }
    resp = client.put("/api/series/settings", json=body)
    assert resp.status_code == 200
    assert LLM_KEY not in resp.text
    stored = json.loads(Path(config_manager.config_path).read_text(encoding="utf-8"))
    assert stored["llm"]["api_key"] == LLM_KEY
    assert stored["llm"]["model"] == "deepseek-v4"
    assert stored["comfyui"]["comfyui_api_key"] == COMFY_KEY
    assert stored["comfyui"]["runninghub_api_key"] == RH_KEY


def test_reset_response_has_no_keys(client: TestClient) -> None:
    resp = client.post("/api/series/settings/reset")
    assert resp.status_code == 200
    assert resp.json()["llm"]["api_key_set"] is False
