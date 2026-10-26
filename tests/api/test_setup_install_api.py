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
from drama_series_agent.setup.steps import RealRunner

LOCAL = "http://127.0.0.1"
CLIENT_HEADERS = {"X-Drama-Studio": "1"}
V1 = "/api/v1"
PROFILE = f"{V1}/setup/profile"
INSTALL = f"{V1}/setup/install"

# PC: everything the scan offers (10 missing + 2 old + 3 optional with install steps). The H3,
# ControlNet and SeedVR2 nodes come with ComfyUI itself and our own nodes are not out yet, so
# the scan finds them missing but offers no install.
PC_INSTALLABLE = [
    "torch", "ffmpeg", "rt_qwentts", "rt_indextts", "rt_ocr", "comfy", "node_flashvsr", "sage",
    "w_h3", "w_te", "w_img", "w_img_t2i", "w_flux3", "w_sr", "w_tts", "llmsrv",
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


def _go(client: TestClient, items: list[str], **kw: Any) -> Any:
    """Install and approve what it asks (on the PC: the change list for its own ComfyUI)."""
    resp = _install(client, items, **kw)
    if resp.status_code == 202 and resp.json()["install"]["confirm"]:
        assert client.post(f"{V1}/setup/install/confirm").status_code == 200
    return resp


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
    assert started["install"]["mirror"] == "auto"
    assert sorted(started["install"]["items"]) == sorted(PC_INSTALLABLE)
    assert set(_states(started).values()) == {"queued"}
    # D:\ComfyUI is the user's own: everything that changes it is listed for approval.
    touching = [x["id"] for x in started["items"] if x["touches_comfy"] and x["install"]]
    # (the weights for ComfyUI too: they go into its model folders; IndexTTS does not)
    assert touching == [
        "torch", "comfy", "node_flashvsr", "sage", "w_h3", "w_te", "w_img", "w_img_t2i",
        "w_flux3", "w_sr",
    ]  # fmt: skip
    confirm = started["install"]["confirm"]
    changes = [c for c in confirm if c["code"] == "comfy_change"]
    assert [c["params"]["item"] for c in changes] == [
        i for i in started["install"]["items"] if i in touching
    ]
    big = [c["params"] for c in confirm if c["code"] == "large_download"]
    assert big == [
        {"item": "w_h3", "gb": 49.3},
        {"item": "w_te", "gb": 15.7},
        {"item": "w_img", "gb": 31.0},
        {"item": "w_img_t2i", "gb": 31.8},
        {"item": "w_flux3", "gb": 20.8},
    ]
    assert changes[0] == {
        "code": "comfy_change",
        "params": {
            "item": "torch",
            "action": "update",
            "from": "2.7.1+cu128",
            "source": "torch torchvision torchaudio",
        },
    }
    assert client.post(f"{V1}/setup/install/confirm").status_code == 200

    done = _wait(client, "done")
    states = _states(done)
    assert Counter(states.values()) == {"done": 15, "failed": 1}
    assert done["download_bps"] == 25e6  # what the weights' downloads measured
    sage = next(x for x in done["items"] if x["id"] == "sage")
    assert sage["install"] == {
        "state": "failed",
        "pct": 60,
        "error": {"code": "no_wheel", "params": {}},
        "bytes_done": None,
        "bytes_total": None,
        "speed": None,
        "eta_s": None,
        "verifying": False,
    }
    assert {x["install"]["pct"] for x in done["items"] if x["id"] != "sage" and x["install"]} == {
        100
    }

    logs = _logs(client)
    assert logs[0] == ("info", "mirror", {"mirror": "auto", "dir": "D:\\DramaStudio"})
    # One snapshot, before the first change to ComfyUI (PyTorch, which goes into its Python).
    codes = [code for _, code, _ in logs]
    assert codes.count("snapshot") == 1
    first = next(i for i, (_, c, p) in enumerate(logs) if c == "start" and p["item"] == "torch")
    assert codes.index("snapshot") == first + 1  # after "start", before any of its steps
    assert codes.index("snapshot") < codes.index("done")
    assert ("warn", "fail_optional", {"item": "sage"}) in logs
    assert logs[-1] == ("ok", "finish", {})
    starts = [p["item"] for _, code, p in logs if code == "start"]
    assert starts == started["install"]["items"]  # dependency order, one at a time
    assert starts.index("torch") < starts.index("comfy") < starts.index("node_flashvsr")
    assert starts.index("comfy") < starts.index("w_h3")
    assert _call(client, lambda: _state(client).setup.installed()) == set(PC_INSTALLABLE) - {"sage"}


def test_install_location_inside_the_program_folder(client: TestClient) -> None:
    """IndexTTS once went into the repo (2026-10-18): such a location is logged as a warning."""
    assert _scan(client)["app_dir"] == "C:\\dev\\drama-studio"
    _install(client, ["ffmpeg"], dir="c:/Dev/Drama-Studio/models")
    _wait(client, "done")
    assert ("warn", "dir_in_app", {"dir": "c:/Dev/Drama-Studio/models"}) in _logs(client)
    _scan(client)
    _install(client, ["llmsrv"], dir="C:\\dev\\drama-studio-models")  # only alike
    _wait(client, "done")
    assert [x for x in _logs(client) if x[1] == "dir_in_app"] == [
        ("warn", "dir_in_app", {"dir": "c:/Dev/Drama-Studio/models"})
    ]


def test_rescan_only_reports_the_difference(client: TestClient) -> None:
    _scan(client)
    _go(client, PC_INSTALLABLE)
    _wait(client, "done")
    after = _scan(client)
    by_id = {x["id"]: x for x in after["items"]}
    assert Counter(x["status"] for x in after["items"]) == {
        "ok": 25,
        "missing": 3,
        "optional": 6,
        "warn": 1,
    }
    # Still missing: only what the installer does not offer (nodes that come with a newer
    # ComfyUI, our own nodes).
    missing = [x for x in after["items"] if x["status"] == "missing"]
    assert [x["id"] for x in missing] == ["node_h3", "node_seedvr2", "node_dramastudio"]
    assert not any(x["installable"] for x in missing)
    assert by_id["ffmpeg"]["found"] == {"code": "installed", "params": {}}
    assert by_id["sage"]["status"] == "optional" and by_id["sage"]["installable"]
    assert all(x["install"] is None for x in after["items"])


def test_retry_and_skip(client: TestClient) -> None:
    _scan(client)
    _go(client, ["ffmpeg", "sage"])
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
    _go(client, ["ffmpeg", "node_flashvsr", "llmsrv"])
    assert client.post(f"{V1}/setup/items/llmsrv/skip").status_code == 200
    monkeypatch.setenv("DRAMA_SETUP_FAKE_TICK_MS", "0")
    states = _states(_wait(client, "done"))
    assert states == {"ffmpeg": "done", "node_flashvsr": "done", "llmsrv": "skipped"}
    starts = [p["item"] for _, code, p in _logs(client) if code == "start"]
    assert "llmsrv" not in starts


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
    # PC: ComfyUI is installed but old. Its update failing does not block the nodes that need it.
    _scan(client)
    _state(client).setup._runner = lambda row: FakeRunner(failing="comfy")
    _go(client, ["comfy", "node_flashvsr"])
    assert _states(_wait(client, "done")) == {"comfy": "failed", "node_flashvsr": "done"}


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


def test_large_download_waits_for_a_yes(client: TestClient) -> None:
    _scan(client)
    resp = _install(client, ["ffmpeg", "w_h3"])
    p = resp.json()
    assert p["phase"] == "installing"
    assert p["install"]["confirm"] == [
        {
            "code": "comfy_change",
            "params": {
                "item": "w_h3",
                "action": "install",
                "to": "e5eb578",  # the pinned Hugging Face revision
                "source": "Comfy-Org/MiniMax-H3",
                "gb": 49.3,
            },
        },
        {"code": "large_download", "params": {"item": "w_h3", "gb": 49.3}},
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
    monkeypatch.setenv("DRAMA_SETUP_FAKE_TICK_MS", "100")
    # Neither changes ComfyUI nor needs a yes: the install is running when the switch comes.
    assert _install(client, ["ffmpeg", "llmsrv"]).json()["install"]["confirm"] == []
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
