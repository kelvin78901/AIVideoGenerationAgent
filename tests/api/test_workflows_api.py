"""Workflow library API (M5 step 2): list, import, bindings, tiers, ComfyUI's list.

Mock's sample machine: ComfyUI's list comes from ``wflib/demo/`` (``DemoComfy``).
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from drama_series_agent.api.app import create_app
from drama_series_agent.api.state import StudioState
from drama_series_agent.core.models_db import ComfyWorkflowRow
from drama_series_agent.wflib.comfy import DEMO_DIR

V1 = "/api/v1"
LOCAL = "http://127.0.0.1"
LTX = "我的/雨夜氛围-ltx2.json"


@pytest.fixture(autouse=True)
def _fast_demo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DRAMA_SETUP_FAKE_DELAY_MS", "0")
    monkeypatch.setenv("DRAMA_SETUP_FAKE_TICK_MS", "0")


def _scan(client: TestClient) -> None:
    """Node packs go into the ComfyUI the last scan found (the PC sample machine)."""
    client.post(f"{V1}/setup/scan")
    deadline = time.monotonic() + 15
    while client.get(f"{V1}/setup/profile").json()["phase"] != "scanned":
        assert time.monotonic() < deadline, "the scan did not finish"
        time.sleep(0.02)


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(), base_url=LOCAL, headers={"X-Drama-Studio": "1"}) as c:
        yield c


def _state(client: TestClient) -> StudioState:
    state: StudioState = client.app.state.studio  # type: ignore[attr-defined]
    return state


def _ltx() -> dict[str, Any]:
    data = json.loads((DEMO_DIR / "workflows" / LTX).read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _import(client: TestClient, **body: Any) -> Any:
    res = client.post(f"{V1}/workflows/import", json=body)
    assert res.status_code == 201, res.text
    return res.json()


def _vid(client: TestClient) -> dict[str, Any]:
    comps = client.get(f"{V1}/config/components").json()["components"]
    found: dict[str, Any] = next(c for c in comps if c["id"] == "vid")
    return found


def _route(client: TestClient, component: str) -> dict[str, Any]:
    values: dict[str, Any] = client.get(
        f"{V1}/config/resolve", params={"component": component}
    ).json()["values"]
    return values


def _pass_trial(client: TestClient, workflow_id: str) -> None:
    """Step 3 runs trials; here the row is told it passed."""

    async def mark() -> None:
        async with _state(client).db.session() as s:
            row = await s.get(ComfyWorkflowRow, workflow_id)
            assert row is not None
            row.trial_json = {
                "at": "2026-10-26T12:00:00Z",
                "status": "passed",
                "job_id": None,
                "w": 768,
                "h": 1366,
                "seconds": 3,
                "duration_s": 41,
                "vram_gb": None,
                "error": None,
            }
            s.add(row)
            await s.commit()

    client.portal.call(mark)  # type: ignore[union-attr]


def test_the_repo_workflows_are_platform_recommended(client: TestClient) -> None:
    rows = client.get(f"{V1}/workflows").json()
    by_slug = {w["slug"]: w for w in rows}
    assert {"flux3-klein", "flux3-klein-t2i", "qwen-image", "qwen-image-edit"} <= set(by_slug)
    assert "selfhost" not in by_slug  # the upstream's old format
    klein = by_slug["flux3-klein"]
    assert klein["tier"] == "recommended" and klein["source"] == "repo"
    assert klein["model_key"] == "comfy/flux3-klein" and "kf" in klein["components"]
    assert klein["bindings"] and all(b["state"] == "confirmed" for b in klein["bindings"])
    assert klein["nodes"] and not klein["file_changed"]
    assert (
        client.patch(f"{V1}/workflows/{klein['id']}", json={"tier": "unverified"}).json()["detail"][
            "code"
        ]
        == "workflow_tier_repo"
    )


def test_import_guesses_bindings_and_registers_an_unverified_model(client: TestClient) -> None:
    w = _import(client, file_name="雨夜氛围-ltx2.json", workflow=_ltx())
    assert (
        w["tier"] == "unverified" and w["source"] == "user" and w["origin"] == "雨夜氛围-ltx2.json"
    )
    assert w["slug"] == "ltx2" and w["model_key"] == "comfy/ltx2"
    assert w["name"] == "雨夜氛围-ltx2" and w["components"] == ["vid"]
    assert {b["slot"] for b in w["bindings"]} >= {"first_frame", "prompt", "seed", "video_out"}
    assert all(b["state"] == "guessed" for b in w["bindings"])
    # A local model of 视频生成 now, but only by hand: not on 「不满意换一个」.
    assert "comfy/ltx2" in _vid(client)["local_models"]
    assert "comfy/ltx2" not in _route(client, "vid")["alt_order"]
    # The same file again: already in the library.
    res = client.post(
        f"{V1}/workflows/import", json={"file_name": "雨夜氛围-ltx2.json", "workflow": _ltx()}
    )
    assert res.status_code == 409 and res.json()["detail"] == {
        "code": "workflow_imported",
        "params": {"id": w["id"]},
    }


def test_mine_needs_confirmed_bindings_and_a_passed_trial(client: TestClient) -> None:
    w = _import(client, file_name="雨夜氛围-ltx2.json", workflow=_ltx())
    url = f"{V1}/workflows/{w['id']}"
    pending = client.patch(url, json={"tier": "mine"}).json()["detail"]
    assert pending == {
        "code": "workflow_bindings_pending",
        "params": {"count": len(w["bindings"])},
    }
    unknown = [{**w["bindings"][0], "node_title": "Nope"}]
    res = client.put(f"{url}/bindings", json=unknown)
    assert res.status_code == 422 and res.json()["detail"]["code"] == "workflow_unknown_node"

    confirmed = client.put(f"{url}/bindings", json=w["bindings"]).json()
    assert all(b["state"] == "confirmed" for b in confirmed["bindings"])
    assert client.patch(url, json={"tier": "mine"}).json()["detail"]["code"] == (
        "workflow_needs_trial"
    )
    _pass_trial(client, w["id"])
    assert client.patch(url, json={"tier": "mine"}).json()["tier"] == "mine"
    assert "comfy/ltx2" in _route(client, "vid")["alt_order"]  # 我的工作流 is offered too
    # Changing a binding makes it a different workflow.
    again = client.put(f"{url}/bindings", json=w["bindings"][:-1]).json()
    assert again["tier"] == "unverified"


def test_comfyui_list_flags_the_board_and_what_is_imported(client: TestClient) -> None:
    files = client.get(f"{V1}/comfy/workflows").json()
    by_path = {f["path"]: f for f in files}
    assert by_path[LTX]["imported_as"] is None and not by_path[LTX]["board"]
    board = next(f for f in files if f["board"])
    res = client.post(f"{V1}/workflows/import", json={"comfy_path": board["path"]})
    assert res.status_code == 409 and res.json()["detail"]["code"] == "workflow_is_board"

    w = _import(client, comfy_path=LTX)
    assert w["origin"] == LTX
    files = {f["path"]: f for f in client.get(f"{V1}/comfy/workflows").json()}
    assert files[LTX]["imported_as"] == w["id"]


def test_a_ui_format_file_is_converted_on_import(client: TestClient) -> None:
    w = _import(client, comfy_path="sdxl_basic.json")
    assert w["slug"] == "sdxl-basic" and w["components"] == ["img", "kf"]
    assert {b["slot"] for b in w["bindings"]} >= {"prompt", "negative", "seed", "image_out"}
    sampler = next(n for n in w["nodes"] if n["class_type"] == "KSampler")
    assert {"seed", "steps", "cfg"} <= set(sampler["fields"])


def test_imports_survive_a_restart(client: TestClient) -> None:
    w = _import(client, file_name="雨夜氛围-ltx2.json", workflow=_ltx())
    client.put(f"{V1}/workflows/{w['id']}/bindings", json=w["bindings"])
    with TestClient(create_app(), base_url=LOCAL, headers={"X-Drama-Studio": "1"}) as again:
        got = again.get(f"{V1}/workflows/{w['id']}").json()
        assert got["tier"] == "unverified" and got["origin"] == "雨夜氛围-ltx2.json"
        assert all(b["state"] == "confirmed" for b in got["bindings"])
        assert "comfy/ltx2" in _vid(again)["local_models"]


def _wait_trial(client: TestClient, workflow_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        w: dict[str, Any] = client.get(f"{V1}/workflows/{workflow_id}").json()
        if w["trial"] and w["trial"]["status"] != "running":
            return w
        time.sleep(0.05)
    raise AssertionError("the trial did not finish")


def test_the_check_lists_missing_packs_and_models_and_install_takes_a_snapshot(
    client: TestClient,
) -> None:
    _scan(client)
    w = _import(client, comfy_path=LTX)  # checked right away
    check = w["check"]
    assert check["status"] == "missing"
    assert check["node_classes"] == {"found": 9, "total": 11}
    assert check["missing_packs"] == [
        {
            "name": "ComfyUI-LTXVideo",
            "classes": ["EmptyLTXVLatentVideo", "LTXVConditioning"],
            "source": "git",
            "version": None,
            "url": "https://github.com/Lightricks/ComfyUI-LTXVideo",
        }
    ]
    assert check["missing_models"] == [
        {
            "folder": "checkpoints",
            "name": "ltx-2-19b-distilled-fp8.safetensors",
            "size_bytes": None,
            "url": None,
        }
    ]
    changes = client.post(f"{V1}/workflows/{w['id']}/deps").json()["changes"]
    assert [c["params"]["item"] for c in changes] == [
        "ComfyUI-LTXVideo",
        "checkpoints/ltx-2-19b-distilled-fp8.safetensors",
    ]
    res = client.post(f"{V1}/workflows/{w['id']}/deps/install").json()
    assert res["packs"] == 1 and res["snapshot"] and res["restart_required"] is False
    after = res["workflow"]["check"]
    assert after["missing_packs"] == [] and after["node_classes"] == {"found": 11, "total": 11}
    assert after["status"] == "missing"  # the checkpoint is still not there
    snaps = client.get(f"{V1}/comfy/snapshots").json()
    assert snaps[0]["changes"][0]["params"]["item"] == "ComfyUI-LTXVideo"
    # No trial until the check is clean.
    res2 = client.post(f"{V1}/workflows/{w['id']}/trial")
    assert res2.status_code == 409 and res2.json()["detail"]["code"] == (
        "workflow_bindings_pending"
    )


def test_a_trial_run_on_the_gpu_queue_makes_it_mine(client: TestClient) -> None:
    w = _import(client, comfy_path="sdxl_basic.json")
    assert w["check"]["status"] == "ok"
    url = f"{V1}/workflows/{w['id']}"
    client.put(f"{url}/bindings", json=w["bindings"])
    started = client.post(f"{url}/trial")
    assert started.status_code == 202
    trial = started.json()["trial"]
    assert trial["status"] == "running" and (trial["w"], trial["h"]) == (768, 1366)
    assert trial["seconds"] == 0  # a picture
    done = _wait_trial(client, w["id"])
    assert done["trial"]["status"] == "passed" and done["trial"]["duration_s"] is not None
    assert client.patch(url, json={"tier": "mine"}).json()["tier"] == "mine"
    job = client.get(f"{V1}/jobs/{trial['job_id']}").json()
    assert job["queue"] == "gpu" and job["state"] == "succeeded"
    calls = client.get(f"{V1}/dev/model-calls").json()
    assert any(c["model_key"] == "comfy/sdxl-basic" for c in calls)


def test_a_workflow_broken_after_a_node_install_points_at_the_snapshot(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _scan(client)
    sdxl = _import(client, comfy_path="sdxl_basic.json")
    ltx = _import(client, comfy_path=LTX)
    access = _state(client).workflows.comfy()
    real = access.object_info

    async def without_ksampler() -> dict[str, Any]:
        info = await real()
        return {k: v for k, v in info.items() if k != "KSampler"}

    # The pack install breaks KSampler (as a bad node pack can).
    res = client.post(f"{V1}/workflows/{ltx["id"]}/deps/install").json()
    monkeypatch.setattr(access, "object_info", without_ksampler)
    rows = {w["id"]: w for w in client.post(f"{V1}/workflows/check-all").json()}
    broken = rows[sdxl["id"]]["check"]
    assert broken["status"] == "broken"
    assert {"code": "broke_after_install", "params": {"snapshot": res["snapshot"]}} in broken[
        "problems"
    ]
