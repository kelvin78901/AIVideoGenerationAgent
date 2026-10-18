"""After a scan, routes skip local models the machine cannot run (SPEC 7.3; M1 acceptance 3).

Uses the sample machines (FakeProbe / FakeRunner) through the API, then asks the router.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from drama_series_agent.api.app import create_app
from drama_series_agent.api.state import StudioState
from drama_series_agent.core.config import Resolved

LOCAL = "http://127.0.0.1"
CLIENT_HEADERS = {"X-Drama-Studio": "1"}
V1 = "/api/v1"
PROFILE = f"{V1}/setup/profile"
COMPAT = f"{V1}/series/demo/spec/compat"
PC_INSTALLABLE = [
    "torch", "ffmpeg", "comfy", "node_h3", "node_seedvr2", "node_flashvsr", "node_ctrl", "sage",
    "node_dramastudio", "w_h3", "w_te", "w_img", "w_sr", "w_tts", "w_llm", "llmsrv",
]  # fmt: skip


@pytest.fixture(autouse=True)
def _fast_demo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DRAMA_SETUP_FAKE_DELAY_MS", "0")
    monkeypatch.setenv("DRAMA_SETUP_FAKE_TICK_MS", "0")


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(), base_url=LOCAL, headers=CLIENT_HEADERS) as c:
        yield c


def _state(client: TestClient) -> StudioState:
    state: StudioState = client.app.state.studio  # type: ignore[attr-defined]
    return state


def _route(client: TestClient, component: str) -> Resolved:
    router = _state(client).router
    resolved: Resolved = client.portal.call(router.settings, component)  # type: ignore[union-attr]
    return resolved


def _modes(client: TestClient) -> dict[str, str]:
    return {c: _route(client, c).values["mode"] for c in ("vid", "kf", "up")}


def _wait(client: TestClient, phase: str, limit_s: float = 15) -> dict[str, Any]:
    deadline = time.monotonic() + limit_s
    while time.monotonic() < deadline:
        p: dict[str, Any] = client.get(PROFILE).json()
        if p["phase"] == phase:
            return p
        time.sleep(0.02)
    raise AssertionError(f"setup never reached {phase}")


def _scan(client: TestClient, machine: str = "pc") -> dict[str, Any]:
    if machine != "pc":
        client.post(f"{V1}/dev/setup/machine", json={"machine": machine})
    client.post(f"{V1}/setup/scan")
    return _wait(client, "scanned")


def _stages(client: TestClient) -> list[str]:
    return [row["stage"] for row in client.get(COMPAT).json()["rows"]]


def test_nothing_is_filtered_before_the_first_scan(client: TestClient) -> None:
    assert client.portal.call(_state(client).setup.capabilities) is None  # type: ignore[union-attr]
    assert _modes(client) == {"vid": "hybrid", "kf": "hybrid", "up": "local"}
    assert _route(client, "vid").unavailable == {}


def test_the_mac_makes_video_keyframes_and_upscaling_on_the_api(client: TestClient) -> None:
    unfiltered = _stages(client)
    _scan(client, "mac")
    caps = client.portal.call(_state(client).setup.capabilities)  # type: ignore[union-attr]
    assert caps is not None and not caps.cuda
    assert _modes(client) == {"vid": "api", "kf": "api", "up": "api"}
    assert _route(client, "vid").values["api_model"] == "minimax/h3-api"
    assert _route(client, "ctrl").values["mode"] == "off"
    assert _route(client, "vid").unavailable["comfy/h3"][0] == "cuda"

    # The compatibility table follows the route this machine will take: no local video draft.
    assert "video_draft" in unfiltered
    assert "video_draft" not in _stages(client)

    # Back to the PC sample: a new machine, unknown until it is scanned.
    client.post(f"{V1}/dev/setup/machine", json={"machine": "pc"})
    assert client.portal.call(_state(client).setup.capabilities) is None  # type: ignore[union-attr]
    assert _modes(client) == {"vid": "hybrid", "kf": "hybrid", "up": "local"}


def test_the_5090_keeps_hybrid_and_local_once_set_up(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _scan(client)
    # No H3 nodes or weights yet: the GPU alone is not enough.
    assert _modes(client) == {"vid": "api", "kf": "api", "up": "api"}
    assert _route(client, "vid").unavailable["comfy/h3"] == ["node_h3", "w_h3", "w_te"]

    body = {"items": PC_INSTALLABLE, "mirror": "auto", "dir": "D:\\DramaStudio"}
    client.post(f"{V1}/setup/install", json=body)
    client.post(f"{V1}/setup/install/confirm")  # the change list for D:\\ComfyUI
    _wait(client, "done")  # SageAttention fails; nothing routes through it
    assert _modes(client) == {"vid": "hybrid", "kf": "hybrid", "up": "local"}
    assert _route(client, "ctrl").values["mode"] == "local"
    assert _route(client, "vid").unavailable == {}

    # A rescan keeps the last findings until it finishes, then confirms them.
    monkeypatch.setenv("DRAMA_SETUP_FAKE_DELAY_MS", "30")
    client.post(f"{V1}/setup/scan")
    assert client.get(PROFILE).json()["phase"] == "scanning"
    assert _modes(client) == {"vid": "hybrid", "kf": "hybrid", "up": "local"}
    _wait(client, "scanned")
    assert _modes(client) == {"vid": "hybrid", "kf": "hybrid", "up": "local"}
