"""``/setup/install`` and ``/setup/items/{id}/retry|skip`` on the sample machines (FakeRunner)."""

from __future__ import annotations

import time
from collections import Counter
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from drama_series_agent.api.app import create_app
from drama_series_agent.api.state import StudioState
from drama_series_agent.core.models_db import MachineProfileRow
from drama_series_agent.setup.installer import INSTALL_JOB, FakeRunner
from drama_series_agent.setup.manifest import Manifest, load_manifest
from drama_series_agent.setup.steps import RealRunner

LOCAL = "http://127.0.0.1"
CLIENT_HEADERS = {"X-Drama-Studio": "1"}
V1 = "/api/v1"
PROFILE = f"{V1}/setup/profile"
INSTALL = f"{V1}/setup/install"

# PC: everything the scan offers (9 missing + 2 old + 5 optional with install steps).
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


def _call(client: TestClient, fn: Any) -> Any:
    return client.portal.call(fn)  # type: ignore[union-attr]


def _code(resp: Any) -> str:
    return resp.json()["detail"]["code"]  # type: ignore[no-any-return]


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


def _install(client: TestClient, items: list[str], **kw: Any) -> Any:
    body = {"items": items, "mirror": "auto", "dir": "D:\\DramaStudio", **kw}
    return client.post(INSTALL, json=body)


def _states(p: dict[str, Any]) -> dict[str, str]:
    return {x["id"]: x["install"]["state"] for x in p["items"] if x["install"]}


def _logs(client: TestClient) -> list[tuple[str, str, dict[str, Any]]]:
    events = _call(client, lambda: _state(client).bus.replay(0))
    return [
        (e.data["level"], e.data["code"], e.data["params"]) for e in events if e.type == "setup.log"
    ]


def test_install_everything_on_the_pc(client: TestClient) -> None:
    scanned = _scan(client)
    offered = [x["id"] for x in scanned["items"] if x["installable"]]
    assert sorted(offered) == sorted(PC_INSTALLABLE)

    resp = _install(client, [*offered, "os", "nope"])  # not installable / unknown: ignored
    assert resp.status_code == 202
    started = resp.json()
    assert started["phase"] == "installing"
    assert started["install"]["mirror"] == "auto" and started["install"]["confirm"] == []
    assert sorted(started["install"]["items"]) == sorted(PC_INSTALLABLE)
    assert set(_states(started).values()) == {"queued"}

    done = _wait(client, "done")
    states = _states(done)
    assert Counter(states.values()) == {"done": 15, "failed": 1}
    sage = next(x for x in done["items"] if x["id"] == "sage")
    assert sage["install"] == {
        "state": "failed",
        "pct": 60,
        "error": {"code": "no_wheel", "params": {}},
    }
    assert {x["install"]["pct"] for x in done["items"] if x["id"] != "sage" and x["install"]} == {
        100
    }

    logs = _logs(client)
    assert logs[0] == ("info", "mirror", {"mirror": "auto", "dir": "D:\\DramaStudio"})
    assert ("warn", "fail_optional", {"item": "sage"}) in logs
    assert logs[-1] == ("ok", "finish", {})
    starts = [p["item"] for _, code, p in logs if code == "start"]
    assert starts == started["install"]["items"]  # dependency order, one at a time
    assert starts.index("torch") < starts.index("comfy") < starts.index("node_h3")
    assert _call(client, lambda: _state(client).setup.installed()) == set(PC_INSTALLABLE) - {"sage"}


def test_rescan_only_reports_the_difference(client: TestClient) -> None:
    _scan(client)
    _install(client, PC_INSTALLABLE)
    _wait(client, "done")
    after = _scan(client)
    by_id = {x["id"]: x for x in after["items"]}
    assert Counter(x["status"] for x in after["items"]) == {"ok": 24, "optional": 4, "warn": 1}
    assert by_id["ffmpeg"]["found"] == {"code": "installed", "params": {}}
    assert by_id["sage"]["status"] == "optional" and by_id["sage"]["installable"]
    assert all(x["install"] is None for x in after["items"])


def test_retry_and_skip(client: TestClient) -> None:
    _scan(client)
    _install(client, ["ffmpeg", "sage"])
    _wait(client, "done")

    resp = client.post(f"{V1}/setup/items/sage/retry")
    assert resp.status_code == 200
    assert _states(resp.json())["sage"] == "queued"
    assert resp.json()["phase"] == "installing"
    p = _wait(client, "done")
    assert _states(p) == {"ffmpeg": "done", "sage": "failed"}  # still no wheel

    resp = client.post(f"{V1}/setup/items/sage/skip")
    assert resp.status_code == 200 and _states(resp.json())["sage"] == "skipped"
    jobs = [j for j in client.get(f"{V1}/jobs").json() if j["kind"] == INSTALL_JOB]
    assert [j["state"] for j in jobs] == ["succeeded", "succeeded"]

    # A skipped item can be retried; a finished one cannot.
    _state(client).setup._runner = lambda row: FakeRunner(failing=None)
    client.post(f"{V1}/setup/items/sage/retry")
    assert _states(_wait(client, "done"))["sage"] == "done"
    resp = client.post(f"{V1}/setup/items/sage/skip")
    assert resp.status_code == 409 and _code(resp) == "setup_item_state"
    assert client.post(f"{V1}/setup/items/ffmpeg/retry").status_code == 409
    resp = client.post(f"{V1}/setup/items/git/retry")  # never queued
    assert resp.status_code == 404 and _code(resp) == "setup_item_not_found"
    assert client.post(f"{V1}/setup/items/nope/skip").status_code == 404


def test_skip_a_queued_item(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _scan(client)
    monkeypatch.setenv("DRAMA_SETUP_FAKE_TICK_MS", "40")
    _install(client, ["ffmpeg", "w_h3", "w_tts"])
    assert client.post(f"{V1}/setup/items/w_tts/skip").status_code == 200
    monkeypatch.setenv("DRAMA_SETUP_FAKE_TICK_MS", "0")
    states = _states(_wait(client, "done"))
    assert states == {"ffmpeg": "done", "w_h3": "done", "w_tts": "skipped"}
    starts = [p["item"] for _, code, p in _logs(client) if code == "start"]
    assert "w_tts" not in starts


def test_dependencies_that_did_not_make_it(client: TestClient) -> None:
    # Mac: ComfyUI and PyTorch are both missing. ComfyUI needs PyTorch, VHS needs ComfyUI.
    _scan(client, "mac")
    _install(client, ["comfy", "node_vhs", "ffmpeg"])
    p = _wait(client, "done")
    items = {x["id"]: x["install"] for x in p["items"] if x["install"]}
    assert items["comfy"]["state"] == "skipped"
    assert items["comfy"]["error"] == {"code": "dependency_missing", "params": {"item": "torch"}}
    assert items["node_vhs"]["error"] == {"code": "dependency_failed", "params": {"item": "comfy"}}
    assert items["ffmpeg"]["state"] == "done"
    assert ("warn", "skip_dep", {"item": "node_vhs", "dep": "comfy"}) in _logs(client)

    # With PyTorch in the same run, a failed ComfyUI still stops its nodes.
    _state(client).setup._runner = lambda row: FakeRunner(failing="comfy")
    _install(client, ["torch", "comfy", "node_vhs"])
    items = {x["id"]: x["install"] for x in _wait(client, "done")["items"] if x["install"]}
    assert [items[i]["state"] for i in ("torch", "comfy", "node_vhs")] == [
        "done",
        "failed",
        "skipped",
    ]


def test_an_old_dependency_still_counts(client: TestClient) -> None:
    # PC: ComfyUI is installed but old. Its update failing does not block the H3 nodes.
    _scan(client)
    _state(client).setup._runner = lambda row: FakeRunner(failing="comfy")
    _install(client, ["comfy", "node_h3"])
    assert _states(_wait(client, "done")) == {"comfy": "failed", "node_h3": "done"}


def test_install_errors(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    resp = _install(client, ["ffmpeg"])  # nothing scanned yet
    assert resp.status_code == 422 and _code(resp) == "nothing_selected"
    _scan(client)
    assert _code(_install(client, ["git", "os"])) == "nothing_selected"
    assert _install(client, ["ffmpeg"], mirror="ftp").status_code == 422
    assert _install(client, ["ffmpeg"], dir="").status_code == 422
    monkeypatch.setenv("DRAMA_SETUP_FAKE_TICK_MS", "500")  # still running for the next calls
    _install(client, ["ffmpeg"])
    resp = _install(client, ["ffmpeg"])
    assert resp.status_code == 409 and _code(resp) == "setup_busy"
    assert client.post(f"{V1}/setup/scan").status_code == 409


def _big_h3() -> Manifest:
    data = load_manifest().model_dump()
    for x in data["items"]:
        if x["id"] == "w_h3":
            x["size_gb"] = 24
    return Manifest.model_validate(data)


def test_large_download_waits_for_a_yes(client: TestClient) -> None:
    _state(client).setup._manifest = _big_h3
    _scan(client)
    resp = _install(client, ["ffmpeg", "w_h3"])
    p = resp.json()
    assert p["phase"] == "installing"
    assert p["install"]["confirm"] == [
        {"code": "large_download", "params": {"item": "w_h3", "gb": 24.0}}
    ]
    time.sleep(0.2)
    assert set(_states(client.get(PROFILE).json()).values()) == {"queued"}  # nothing ran
    jobs = [j for j in client.get(f"{V1}/jobs").json() if j["kind"] == INSTALL_JOB]
    assert jobs[0]["state"] == "waiting_confirm"
    assert ("warn", "confirm", {}) in _logs(client)

    resp = client.post(f"{V1}/setup/install/confirm")
    assert resp.status_code == 200 and resp.json()["install"]["confirm"] == []
    assert _states(_wait(client, "done")) == {"ffmpeg": "done", "w_h3": "done"}
    resp = client.post(f"{V1}/setup/install/confirm")
    assert resp.status_code == 409 and _code(resp) == "setup_no_confirm"


def test_declining_the_confirmation(client: TestClient) -> None:
    _state(client).setup._manifest = _big_h3
    _scan(client)
    _install(client, ["w_h3"])
    resp = client.post(f"{V1}/setup/install/cancel")
    assert resp.status_code == 200
    p = resp.json()
    assert p["phase"] == "scanned" and _states(p) == {}
    jobs = [j for j in client.get(f"{V1}/jobs").json() if j["kind"] == INSTALL_JOB]
    assert jobs[0]["state"] == "canceled"
    assert ("info", "cancel", {}) in _logs(client)
    assert client.post(f"{V1}/setup/install/cancel").status_code == 409
    assert _install(client, ["w_h3"]).status_code == 202  # can start over


def test_switching_machines_stops_the_install(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _scan(client)
    monkeypatch.setenv("DRAMA_SETUP_FAKE_TICK_MS", "50")
    _install(client, ["w_h3", "w_te"])
    time.sleep(0.15)
    p = client.post(f"{V1}/dev/setup/machine", json={"machine": "mac"}).json()
    assert p["phase"] == "idle" and p["install"] is None
    jobs = [j for j in client.get(f"{V1}/jobs").json() if j["kind"] == INSTALL_JOB]
    assert jobs[0]["state"] == "canceled"
    time.sleep(0.2)
    assert client.get(PROFILE).json()["machine"]["os"] == "macos"
    assert _call(client, lambda: _state(client).setup.installed()) == set()


def test_an_install_that_died_stops_queueing(client: TestClient) -> None:
    _scan(client)

    async def died() -> None:
        state = _state(client)
        job = await state.jobs.enqueue("unregistered", "cpu", wait_for_confirm=True)
        await state.jobs.cancel(job.id)
        async with state.db.session() as s:
            row = await s.get(MachineProfileRow, "demo")
            assert row is not None
            items = row.data_json["items"]
            for x in items:
                if x["id"] in ("ffmpeg", "torch"):
                    x["install"] = {
                        "state": "running" if x["id"] == "torch" else "queued",
                        "pct": 0,
                        "error": None,
                    }
            row.data_json = {
                **row.data_json,
                "phase": "installing",
                "job_id": job.id,
                "items": items,
                "install": {"items": ["torch", "ffmpeg"], "mirror": "auto", "dir": "D:/M"},
            }
            s.add(row)
            await s.commit()

    _call(client, died)
    p = client.get(PROFILE).json()
    assert p["phase"] == "done"
    assert {x["id"]: x["install"]["error"]["code"] for x in p["items"] if x["install"]} == {
        "torch": "interrupted",
        "ffmpeg": "interrupted",
    }
    assert client.post(f"{V1}/setup/items/torch/retry").status_code == 200
    assert _states(_wait(client, "done"))["torch"] == "done"


def test_real_machine_gets_the_real_runner(client: TestClient) -> None:
    setup = _state(client).setup
    assert isinstance(setup.runner_for(MachineProfileRow(id="demo", machine="pc")), FakeRunner)
    assert isinstance(setup.runner_for(MachineProfileRow(id="local")), RealRunner)
