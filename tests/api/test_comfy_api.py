"""``GET /comfy/env``: what the scan read about the installed ComfyUI (SPEC 6.4.1)."""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import select

from drama_series_agent.api.app import create_app
from drama_series_agent.api.state import StudioState
from drama_series_agent.core.models_db import ComfyEnvRow

LOCAL = "http://127.0.0.1"
CLIENT_HEADERS = {"X-Drama-Studio": "1"}
V1 = "/api/v1"
PROFILE = f"{V1}/setup/profile"
ENV = f"{V1}/comfy/env"


@pytest.fixture(autouse=True)
def _fast_demo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DRAMA_SETUP_FAKE_DELAY_MS", "0")


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(), base_url=LOCAL, headers=CLIENT_HEADERS) as c:
        yield c


def _scan(client: TestClient, machine: str = "pc") -> None:
    if machine != "pc":
        client.post(f"{V1}/dev/setup/machine", json={"machine": machine})
    client.post(f"{V1}/setup/scan")
    deadline = time.monotonic() + 15
    while client.get(PROFILE).json()["phase"] != "scanned":
        assert time.monotonic() < deadline, "scan never finished"
        time.sleep(0.02)


def _env_rows(client: TestClient) -> list[ComfyEnvRow]:
    state: StudioState = client.app.state.studio  # type: ignore[attr-defined]

    async def rows() -> list[ComfyEnvRow]:
        async with state.db.session() as s:
            return list((await s.exec(select(ComfyEnvRow))).all())

    return client.portal.call(rows)  # type: ignore[union-attr,no-any-return]


def test_nothing_before_a_scan(client: TestClient) -> None:
    assert client.get(ENV).json() == {
        "scanned_at": None,
        "simulated": True,
        "comfy": None,
        "env": None,
    }


def test_the_pc_sample(client: TestClient) -> None:
    _scan(client)
    body: dict[str, Any] = client.get(ENV).json()
    assert body["scanned_at"] is not None and body["simulated"] is True
    comfy, env = body["comfy"], body["env"]
    assert (comfy["root"], comfy["kind"], comfy["port"]) == ("D:\\ComfyUI", "folder", 8188)
    assert {m["name"] for m in comfy["models"]} == {
        "sd_xl_base_1.0.safetensors",
        "rain/rain_style.safetensors",
        "ae.safetensors",
    }
    assert (env["comfyui_version"], env["python"], env["torch"]) == (
        "0.3.40",
        "3.12.9",
        "2.7.1+cu128",
    )
    assert [(p["name"], p["source"]) for p in env["node_packs"]] == [
        ("ComfyUI-KJNodes", "registry"),
        ("ComfyUI-VideoHelperSuite", "git"),
        ("websocket_image_save", "manual"),
    ]
    assert env["hash"] == comfy["env_hash"]

    # Same environment on the next scan: no second row.
    _scan(client)
    rows = _env_rows(client)
    assert [r.hash for r in rows] == [env["hash"]]
    assert rows[0].node_packs_json[1]["commit"] == "8a3f6c1e9b2d4f70a5c8e1b3d6f9a2c4e7b0d1f3"


def test_the_mac_sample_has_none(client: TestClient) -> None:
    _scan(client)
    _scan(client, "mac")
    body = client.get(ENV).json()
    assert body["scanned_at"] is not None
    assert (body["comfy"], body["env"]) == (None, None)
