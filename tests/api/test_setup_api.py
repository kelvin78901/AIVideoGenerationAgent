"""``/setup/profile``, ``/setup/scan`` and ``/dev/setup/machine`` on Mock's sample machines."""

from __future__ import annotations

import sys
import time
from collections import Counter
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from drama_series_agent.api.app import create_app
from drama_series_agent.api.state import StudioState
from drama_series_agent.core.models_db import InstalledItem, MachineProfileRow
from drama_series_agent.setup.service import SCAN_JOB

LOCAL = "http://127.0.0.1"
CLIENT_HEADERS = {"X-Drama-Studio": "1"}
PROFILE = "/api/v1/setup/profile"
SCAN = "/api/v1/setup/scan"
MACHINE = "/api/v1/dev/setup/machine"
ITEM_KEYS = {"id", "group", "name", "status", "found", "fix", "required", "installable", "install"}


@pytest.fixture(autouse=True)
def _no_demo_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DRAMA_SETUP_FAKE_DELAY_MS", "0")


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(), base_url=LOCAL, headers=CLIENT_HEADERS) as c:
        yield c


def _state(client: TestClient) -> StudioState:
    state: StudioState = client.app.state.studio  # type: ignore[attr-defined]
    return state


def _call(client: TestClient, fn: Any) -> Any:
    return client.portal.call(fn)  # type: ignore[union-attr]


def _code(resp: Any) -> str:
    return resp.json()["detail"]["code"]  # type: ignore[no-any-return]


def _wait_scanned(client: TestClient, limit_s: float = 10) -> dict[str, Any]:
    deadline = time.monotonic() + limit_s
    while time.monotonic() < deadline:
        p: dict[str, Any] = client.get(PROFILE).json()
        if p["phase"] == "scanned":
            return p
        time.sleep(0.02)
    raise AssertionError("scan never finished")


def _counts(p: dict[str, Any]) -> Counter[str]:
    return Counter(x["status"] for x in p["items"])


async def _noop() -> None:
    return None


def test_profile_before_the_first_scan(client: TestClient) -> None:
    assert client.get(PROFILE).json() == {
        "scanned_at": None,
        "machine": {"os": "windows", "gpu": {"name": "RTX 5090", "vram_gb": 32, "backend": "cuda"}},
        "phase": "idle",
        "items": [],
        "install": None,
        "default_dir": "D:\\DramaStudio",
        "recommendation": None,
        "simulated": True,
    }


def test_scan_the_pc(client: TestClient) -> None:
    resp = client.post(SCAN)
    assert resp.status_code == 202
    started = resp.json()
    assert started["phase"] == "scanning"
    assert len(started["items"]) == 29
    assert {x["status"] for x in started["items"]} == {"checking"}
    assert all(x["found"] is None and not x["installable"] for x in started["items"])

    p = _wait_scanned(client)
    assert _counts(p) == {"ok": 9, "missing": 9, "old": 2, "optional": 8, "warn": 1}
    assert [x["id"] for x in p["items"]] == [x["id"] for x in started["items"]]
    assert p["recommendation"] == {"preset": "balanced", "reason": "local_video"}
    assert p["scanned_at"].endswith("Z")
    torch = next(x for x in p["items"] if x["id"] == "torch")
    assert set(torch) == ITEM_KEYS
    assert torch == {
        "id": "torch",
        "group": "rt",
        "name": {"zh": "PyTorch", "en": "PyTorch"},
        "status": "old",
        "found": {"code": "torch_not_cuda", "params": {"cuda": "13"}},
        "fix": {"code": "torch_cuda", "params": {"cuda": "13.0"}},
        "required": True,
        "installable": True,
        "install": None,
    }


def test_scan_events(client: TestClient) -> None:
    client.post(SCAN)
    _wait_scanned(client)
    events = [
        e.data
        for e in _call(client, lambda: _state(client).bus.replay(0))
        if e.type == "setup.progress"
    ]
    assert events[0] == {"phase": "scanning", "item": None}
    assert all(e["phase"] == "scanning" and e["item"] for e in events[1:-1])
    assert [e["item"]["id"] for e in events[1:-1]][:3] == ["os", "gpu", "driver"]
    assert len(events) == 29 + 2
    assert events[-1] == {"phase": "scanned", "item": None}


def test_switch_to_the_mac(client: TestClient) -> None:
    client.post(SCAN)
    _wait_scanned(client)
    resp = client.post(MACHINE, json={"machine": "mac"})
    assert resp.status_code == 200
    p = resp.json()
    assert p["phase"] == "idle" and p["items"] == [] and p["scanned_at"] is None
    assert p["machine"] == {
        "os": "macos",
        "gpu": {"name": "Apple M4 Pro", "vram_gb": 48, "backend": "mps"},
    }
    assert p["default_dir"] == "~/DramaStudio"
    client.post(SCAN)
    p = _wait_scanned(client)
    assert len(p["items"]) == 28
    assert _counts(p) == {"ok": 6, "warn": 3, "missing": 4, "optional": 7, "skip": 8}
    assert p["recommendation"] == {"preset": "balanced", "reason": "no_cuda"}
    assert client.post(MACHINE, json={"machine": "amiga"}).status_code == 422


def test_installed_items_count_on_a_sample_machine(client: TestClient) -> None:
    async def install(*item_ids: str) -> None:
        await _state(client).setup.profile()  # creates the profile row
        async with _state(client).db.session() as s:
            for item_id in item_ids:
                s.add(InstalledItem(profile_id="demo", item_id=item_id, version="8.0"))
            await s.commit()

    _call(client, lambda: install("ffmpeg", "node_h3"))
    client.post(SCAN)
    items = {x["id"]: x for x in _wait_scanned(client)["items"]}
    assert items["ffmpeg"]["status"] == "ok"
    assert items["ffmpeg"]["found"] == {"code": "installed", "params": {}}
    assert items["node_h3"]["status"] == "ok" and not items["node_h3"]["installable"]
    assert items["w_h3"]["status"] == "missing"

    # Switching machines starts over: nothing installed.
    client.post(MACHINE, json={"machine": "pc"})
    assert _call(client, lambda: _state(client).setup.installed("demo")) == set()


def test_rescan_replaces_a_running_scan(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DRAMA_SETUP_FAKE_DELAY_MS", "30")
    client.post(SCAN)
    time.sleep(0.1)
    client.post(SCAN)
    monkeypatch.setenv("DRAMA_SETUP_FAKE_DELAY_MS", "0")
    p = _wait_scanned(client)
    assert len(p["items"]) == 29 and "checking" not in _counts(p)
    jobs = [j for j in client.get("/api/v1/jobs").json() if j["kind"] == SCAN_JOB]
    assert sorted(j["state"] for j in jobs) == ["canceled", "succeeded"]


def test_no_scan_while_installing(client: TestClient) -> None:
    async def installing() -> None:
        state = _state(client)
        await state.setup.profile()
        job = await state.jobs.enqueue("unregistered", "cpu", wait_for_confirm=True)
        async with state.db.session() as s:
            row = await s.get(MachineProfileRow, "demo")
            assert row is not None
            row.data_json = {**row.data_json, "phase": "installing", "job_id": job.id}
            s.add(row)
            await s.commit()

    _call(client, installing)
    resp = client.post(SCAN)
    assert resp.status_code == 409 and _code(resp) == "setup_busy"


def test_a_scan_that_died_stops_checking(client: TestClient) -> None:
    async def died() -> None:
        state = _state(client)
        await state.setup.profile()
        job = await state.jobs.enqueue("unregistered", "cpu", wait_for_confirm=True)
        await state.jobs.cancel(job.id)
        async with state.db.session() as s:
            row = await s.get(MachineProfileRow, "demo")
            assert row is not None
            row.data_json = {**row.data_json, "phase": "scanning", "job_id": job.id}
            s.add(row)
            await s.commit()

    _call(client, died)
    p = client.get(PROFILE).json()
    assert p["phase"] == "idle" and p["items"] == []


def test_profile_survives_a_restart() -> None:
    with TestClient(create_app(), base_url=LOCAL, headers=CLIENT_HEADERS) as c:
        c.post(SCAN)
        before = _wait_scanned(c)
    with TestClient(create_app(), base_url=LOCAL, headers=CLIENT_HEADERS) as c:
        assert c.get(PROFILE).json() == before


def test_real_mode(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DRAMA_SETUP", "real")
    resp = client.post(MACHINE, json={"machine": "mac"})
    assert resp.status_code == 403 and _code(resp) == "setup_not_simulated"
    # Only the quick, read-only hardware probe of this machine.
    p = client.get(PROFILE).json()
    assert p["simulated"] is False and p["phase"] == "idle"
    expected = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")
    assert p["machine"]["os"] == expected
    # The sample machine's profile is kept apart.
    monkeypatch.setenv("DRAMA_SETUP", "fake")
    assert client.get(PROFILE).json()["simulated"] is True
