"""Workflow library API (M5 step 2): list, import, bindings, tiers, ComfyUI's list.

Mock's sample machine: ComfyUI's list comes from ``wflib/demo/`` (``DemoComfy``).
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient

from drama_series_agent.api.app import create_app
from drama_series_agent.api.state import StudioState
from drama_series_agent.core.models_db import ComfyWorkflowRow
from drama_series_agent.modelhub.workflows import load_workflow, user_workflows_dir
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


def _tier(client: TestClient, key: str) -> str | None:
    models = client.get(f"{V1}/config/components").json()["models"]
    tier: str | None = next(m for m in models if m["key"] == key)["tier"]
    return tier


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
    # A workflow a providers.yaml model runs is that model, not a second one.
    h3 = by_slug["h3-i2v"]
    assert h3["model_key"] == "comfy/h3" and "vid" in h3["components"]
    assert not any(w["model_key"] == "comfy/h3-i2v" for w in rows)
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
    # The picker lists it apart from the shipped workflows.
    assert _tier(client, "comfy/ltx2") == "unverified"
    assert _tier(client, "comfy/h3") == "recommended"
    assert _tier(client, "local/qwen3.6-27b") is None
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
    assert _tier(client, "comfy/ltx2") == "mine"
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


def test_a_changed_repo_workflow_drops_its_old_check_and_models(client: TestClient) -> None:
    """Step 14e took the Turbo LoRA out of h3-i2v: the library's row follows the new file."""
    turbo = {"folder": "loras", "name": "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors"}

    async def age() -> None:
        async with _state(client).db.session() as s:
            row = await s.get(ComfyWorkflowRow, "wf_h3-i2v")
            assert row is not None
            row.file_sha256 = "old"
            row.deps_json = {"models": [turbo], "packs": []}
            row.check_json = {"status": "ok"}
            s.add(row)
            await s.commit()

    client.portal.call(age)  # type: ignore[union-attr]
    client.portal.call(_state(client).workflows.sync)  # type: ignore[union-attr]
    h3 = client.get(f"{V1}/workflows/wf_h3-i2v").json()
    assert h3["tier"] == "recommended" and h3["check"] is None and not h3["file_changed"]
    [row] = [r for r in client.portal.call(_state(client).workflows.rows) if r.slug == "h3-i2v"]  # type: ignore[union-attr]
    assert turbo not in row.deps_json["models"] and row.deps_json["models"]


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
    res = client.post(f"{V1}/workflows/{ltx['id']}/deps/install").json()
    monkeypatch.setattr(access, "object_info", without_ksampler)
    rows = {w["id"]: w for w in client.post(f"{V1}/workflows/check-all").json()}
    broken = rows[sdxl["id"]]["check"]
    assert broken["status"] == "broken"
    assert {"code": "broke_after_install", "params": {"snapshot": res["snapshot"]}} in broken[
        "problems"
    ]


def _dramastudio_graph() -> dict[str, Any]:
    """A video workflow made of DramaStudio's nodes (two reference pictures, same title)."""

    def node(cls: str, title: str, **inputs: Any) -> dict[str, Any]:
        return {"class_type": cls, "inputs": inputs, "_meta": {"title": title}}

    return {
        "1": node("DramaStudioFirstFrame", "首帧", image="dramastudio/a.png"),
        "2": node("DramaStudioRefImage", "参考图", index=1, image="dramastudio/b.png"),
        "3": node("DramaStudioRefImage", "参考图", index=2, image="dramastudio/c.png"),
        "4": node("DramaStudioPrompt", "提示词", text=""),
        "5": node("DramaStudioSize", "尺寸", width=768, height=1344),
        "6": node("DramaStudioDuration", "时长", fps=24.0, seconds=5.0),
        "7": node("DramaStudioSeed", "种子", seed=0),
        "8": node("CreateVideo", "Create Video", images=["1", 0], fps=["6", 0]),
        "9": node("DramaStudioVideoOut", "视频", video=["8", 0], filename_prefix="x"),
    }


def test_a_dramastudio_workflow_binds_itself_and_installs_our_pack(client: TestClient) -> None:
    _scan(client)
    w = _import(client, file_name="ds-video.json", workflow=_dramastudio_graph())
    assert w["uses_dramastudio_nodes"] and w["components"] == ["vid"]
    got = {(b["slot"], b["index"]): (b["node_title"], b["field"]) for b in w["bindings"]}
    assert got == {
        ("first_frame", None): ("首帧", "image"),
        ("ref_image", 1): ("参考图 #2", "image"),
        ("ref_image", 2): ("参考图", "image"),
        ("prompt", None): ("提示词", "text"),
        ("width", None): ("尺寸", "width"),
        ("height", None): ("尺寸", "height"),
        ("fps", None): ("时长", "fps"),
        ("seconds", None): ("时长", "seconds"),
        ("seed", None): ("种子", "seed"),
        ("video_out", None): ("视频", None),
    }
    assert {b["state"] for b in w["bindings"]} == {"dramastudio"}
    # Nothing to confirm, nothing to edit.
    res = client.put(f"{V1}/workflows/{w['id']}/bindings", json=w["bindings"])
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "workflow_dramastudio_bindings"
    # The reference pictures are optional: a shot with one leaves the second node out.
    wf = load_workflow(w["slug"], user_workflows_dir())
    graph = wf.fill({"first_frame": "dramastudio/f.png", "seed": 7}, refs=["dramastudio/r.png"])
    assert "3" not in graph and graph["2"]["inputs"]["image"] == "dramastudio/r.png"
    assert graph["7"]["inputs"]["seed"] == 7
    # ComfyUI does not have our nodes yet: the check names our pack, from the repo.
    check = w["check"]
    assert check["status"] == "missing" and check["problems"] == []
    assert check["missing_packs"] == [
        {
            "name": "DramaStudio",
            "classes": [
                "DramaStudioDuration", "DramaStudioFirstFrame", "DramaStudioPrompt",
                "DramaStudioRefImage", "DramaStudioSeed", "DramaStudioSize",
                "DramaStudioVideoOut",
            ],
            "source": "studio",
            "version": "0.1.0",
            "url": None,
        }
    ]  # fmt: skip
    changes = client.post(f"{V1}/workflows/{w['id']}/deps").json()["changes"]
    assert [c["params"] for c in changes] == [
        {"item": "DramaStudio", "action": "install", "to": "0.1.0"}
    ]
    # Installed through the setup item (a snapshot first), then the check is clean.
    res = client.post(f"{V1}/workflows/{w['id']}/deps/install").json()
    assert res["packs"] == 1 and res["snapshot"] and res["failed"] == []
    assert res["workflow"]["check"]["status"] == "ok"
    snaps = client.get(f"{V1}/comfy/snapshots").json()
    assert snaps[0]["changes"][0]["params"]["item"] == "DramaStudio"
    started = client.post(f"{V1}/workflows/{w['id']}/trial")
    assert started.status_code == 202
    assert _wait_trial(client, w["id"])["trial"]["status"] == "passed"
    assert client.patch(f"{V1}/workflows/{w['id']}", json={"tier": "mine"}).json()["tier"] == "mine"


def test_each_branch_has_its_own_trial(client: TestClient) -> None:
    w = _import(client, comfy_path="sdxl_basic.json")
    url = f"{V1}/workflows/{w['id']}"
    client.put(f"{url}/bindings", json=w["bindings"]).raise_for_status()
    folder = user_workflows_dir() / w["slug"]
    meta = yaml.safe_load((folder / "workflow.yaml").read_text("utf-8"))
    bound = {b["node_title"] for b in client.get(url).json()["bindings"]}
    free = next(n["title"] for n in w["nodes"] if n["title"] not in bound)
    meta["branches"] = [{"id": "detail", "kind": "upscale", "nodes": [free], "default": False}]
    (folder / "workflow.yaml").write_text(yaml.safe_dump(meta, allow_unicode=True), "utf-8")
    listed = client.get(url).json()["branches"]
    assert listed == [
        {"id": "detail", "kind": "upscale", "name": "detail", "default": False, "trial": None}
    ]
    res = client.post(f"{url}/trial", json={"branch": "nope"})
    assert res.status_code == 422 and res.json()["detail"]["code"] == "workflow_unknown_branch"
    started = client.post(f"{url}/trial", json={"branch": "detail"})
    assert started.status_code == 202
    assert started.json()["trial"] is None  # the workflow's own trial has not run
    deadline = time.monotonic() + 20
    while (b := client.get(url).json()["branches"][0])["trial"]["status"] == "running":
        assert time.monotonic() < deadline, "the branch trial did not finish"
        time.sleep(0.05)
    assert b["trial"]["status"] == "passed"
    # The workflow's own trial keeps the branch's.
    client.post(f"{url}/trial").raise_for_status()
    done = _wait_trial(client, w["id"])
    assert done["trial"]["status"] == "passed"
    assert done["branches"][0]["trial"]["status"] == "passed"


def test_a_shot_switches_a_branch_through_its_config(client: TestClient) -> None:
    body = {"scope": "item", "scope_id": "shot:demo-shot-1-04", "component_id": "vid"}
    res = client.put(f"{V1}/config/override", json={**body, "data": {"branches": {"lora": True}}})
    assert res.status_code == 200, res.text
    resolved = res.json()
    assert resolved["values"]["branches"] == {"lora": True}
