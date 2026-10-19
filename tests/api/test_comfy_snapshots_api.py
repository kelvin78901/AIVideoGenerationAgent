"""Changing the user's own ComfyUI: change list, snapshot first, rollback (SPEC 6.4.1, step 5c)."""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from drama_series_agent.api.app import create_app
from drama_series_agent.api.state import StudioState
from drama_series_agent.setup.probe import FakeProbe
from drama_series_agent.setup.snapshots import FakeSnapshots, SnapshotFailure

LOCAL = "http://127.0.0.1"
CLIENT_HEADERS = {"X-Drama-Studio": "1"}
V1 = "/api/v1"
PROFILE = f"{V1}/setup/profile"
SNAPSHOTS = f"{V1}/comfy/snapshots"
SEEDVR2 = "https://github.com/numz/ComfyUI-SeedVR2_VideoUpscaler"


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


def _install(client: TestClient, items: list[str]) -> dict[str, Any]:
    body = {"items": items, "mirror": "auto", "dir": "D:\\DramaStudio"}
    resp = client.post(f"{V1}/setup/install", json=body)
    assert resp.status_code == 202
    return resp.json()  # type: ignore[no-any-return]


def _confirm(client: TestClient) -> None:
    assert client.post(f"{V1}/setup/install/confirm").status_code == 200


def _installs(p: dict[str, Any]) -> dict[str, Any]:
    return {x["id"]: x["install"] for x in p["items"] if x["install"]}


def _logs(client: TestClient) -> list[tuple[str, dict[str, Any]]]:
    events = client.portal.call(lambda: _state(client).bus.replay(0))  # type: ignore[union-attr]
    return [(e.data["code"], e.data["params"]) for e in events if e.type == "setup.log"]


def _failing_snapshots(client: TestClient, reason: SnapshotFailure | None) -> None:
    _state(client).setup._snapshots = lambda row, data: FakeSnapshots(fail=reason)


def test_a_change_waits_for_approval_and_takes_a_snapshot_first(client: TestClient) -> None:
    _scan(client)
    started = _install(client, ["ffmpeg", "node_seedvr2"])
    change = {
        "code": "comfy_change",
        "params": {"item": "node_seedvr2", "action": "install", "to": "v2.5.23", "source": SEEDVR2},
    }
    assert started["install"]["confirm"] == [change]  # FFmpeg does not touch ComfyUI
    time.sleep(0.1)  # nothing runs before the user says yes
    assert {x["state"] for x in _installs(client.get(PROFILE).json()).values()} == {"queued"}

    _confirm(client)
    done = _wait(client, "done")
    assert {i: x["state"] for i, x in _installs(done).items()} == {
        "ffmpeg": "done",
        "node_seedvr2": "done",
    }
    snaps = client.get(SNAPSHOTS).json()
    assert len(snaps) == 1
    snap = snaps[0]
    assert (snap["reason"], snap["changes"], snap["restored_at"]) == ("install", [change], None)
    assert snap["env_hash"] == client.get(f"{V1}/comfy/env").json()["env"]["hash"]
    assert done["install"]["snapshot"] == snap["id"]
    # The snapshot comes after FFmpeg (which leaves ComfyUI alone) and before SeedVR2's steps.
    order = [(c, p.get("item")) for c, p in _logs(client) if c in ("start", "snapshot", "done")]
    assert order == [
        ("start", "ffmpeg"),
        ("done", "ffmpeg"),
        ("start", "node_seedvr2"),
        ("snapshot", None),
        ("done", "node_seedvr2"),
    ]


def test_installs_that_leave_comfyui_alone_need_neither(client: TestClient) -> None:
    _scan(client)
    started = _install(client, ["ffmpeg"])
    assert started["install"]["confirm"] == []
    _wait(client, "done")
    assert client.get(SNAPSHOTS).json() == []
    # On the Mac there is no ComfyUI of the user's: installing one is not a change to theirs.
    scanned = _scan(client, "mac")
    assert not any(x["touches_comfy"] for x in scanned["items"])
    assert _install(client, ["torch", "comfy"])["install"]["confirm"] == []


def test_no_snapshot_no_change(client: TestClient) -> None:
    _scan(client)
    _failing_snapshots(client, "not_running")
    _install(client, ["ffmpeg", "node_seedvr2", "node_vhs", "sage"])
    _confirm(client)
    done = _installs(_wait(client, "done"))
    assert done["ffmpeg"]["state"] == "done"
    for item in ("node_seedvr2", "sage"):
        assert done[item]["state"] == "failed"
        assert done[item]["error"] == {"code": "snapshot_not_running", "params": {}}
    assert "node_vhs" not in done  # already there: not installable, ignored
    assert [p for c, p in _logs(client) if c == "snapshot_failed"] == [{"reason": "not_running"}]
    assert client.get(SNAPSHOTS).json() == []

    # ComfyUI is open now: a retry takes the snapshot and goes ahead.
    _failing_snapshots(client, None)
    assert client.post(f"{V1}/setup/items/node_seedvr2/retry").status_code == 200
    assert _installs(_wait(client, "done"))["node_seedvr2"]["state"] == "done"
    assert len(client.get(SNAPSHOTS).json()) == 1


def test_without_manager_it_is_installed_first(client: TestClient) -> None:
    probe = FakeProbe.load("pc")
    probe.files.discard(
        "D:/ComfyUI/venv/Lib/site-packages/comfyui_manager-4.2.2.dist-info/METADATA"
    )
    _state(client).setup.probe_for = lambda row: probe  # type: ignore[method-assign]
    scanned = _scan(client)
    manager = next(x for x in scanned["items"] if x["id"] == "comfy_manager")
    assert (manager["status"], manager["installable"], manager["touches_comfy"]) == (
        "optional",
        True,
        True,
    )
    started = _install(client, ["node_seedvr2"])
    assert started["install"]["items"] == ["comfy_manager", "node_seedvr2"]
    assert [c["params"]["item"] for c in started["install"]["confirm"]] == [
        "comfy_manager",
        "node_seedvr2",
    ]
    _confirm(client)
    done = _installs(_wait(client, "done"))
    assert done["comfy_manager"]["state"] == "done"  # needs no snapshot: it takes them
    # It only loads when ComfyUI restarts, so nothing else is changed this time.
    assert done["node_seedvr2"]["error"] == {"code": "snapshot_restart", "params": {}}


def test_without_comfyui_manager_follows_the_comfyui_we_install(client: TestClient) -> None:
    scanned = _scan(client, "mac")
    assert not any(x["touches_comfy"] for x in scanned["items"])
    started = _install(client, ["comfy_manager", "torch", "comfy"])
    assert started["install"]["items"] == ["torch", "comfy", "comfy_manager"]
    assert started["install"]["confirm"] == []


def test_rollback(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _scan(client)
    resp = client.post(SNAPSHOTS)
    assert resp.status_code == 201
    snap = resp.json()
    assert (snap["reason"], snap["changes"]) == ("manual", [])

    resp = client.post(f"{SNAPSHOTS}/{snap['id']}/restore")
    assert resp.status_code == 200
    body = resp.json()
    assert body["restart_required"] is True
    assert body["snapshot"]["id"] == snap["id"] and body["snapshot"]["restored_at"] is not None
    assert client.get(SNAPSHOTS).json()[0]["restored_at"] == body["snapshot"]["restored_at"]

    resp = client.post(f"{SNAPSHOTS}/nope/restore")
    assert resp.status_code == 404 and resp.json()["detail"]["code"] == "comfy_snapshot_not_found"

    # Not while an install is changing things.
    monkeypatch.setenv("DRAMA_SETUP_FAKE_TICK_MS", "60")
    _install(client, ["ffmpeg"])
    resp = client.post(f"{SNAPSHOTS}/{snap['id']}/restore")
    assert resp.status_code == 409 and resp.json()["detail"]["code"] == "setup_busy"
    monkeypatch.setenv("DRAMA_SETUP_FAKE_TICK_MS", "0")
    _wait(client, "done")

    # Manager refuses (its security level): nothing is marked restored.
    _failing_snapshots(client, "forbidden")
    resp = client.post(f"{SNAPSHOTS}/{snap['id']}/restore")
    assert resp.status_code == 409
    assert resp.json()["detail"] == {
        "code": "comfy_snapshot_failed",
        "params": {"reason": "forbidden"},
    }

    # The Mac sample has no ComfyUI to snapshot; switching sample machines starts over.
    _scan(client, "mac")
    resp = client.post(SNAPSHOTS)
    assert resp.status_code == 409 and resp.json()["detail"]["code"] == "comfy_not_found"
    assert client.get(SNAPSHOTS).json() == []
