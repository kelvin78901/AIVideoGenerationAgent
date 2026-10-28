"""M5 acceptance (plan step 13), against a real backend process on Mock's sample machine (the PC
sample, scanned): a community workflow from ComfyUI's own list into the library (guessed
bindings confirmed, the missing node pack installed after a snapshot, a trial on the GPU queue,
made 「我的工作流」, offered to 视频生成); and a bad node pack that breaks what worked, pointed
back to its snapshot and rolled back.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import pytest
from test_novel_to_script import Api

if TYPE_CHECKING:
    from conftest import Backend  # tests/e2e/conftest.py

pytestmark = pytest.mark.e2e

WAN = "社区/图生视频-wan22.json"  # needs ComfyUI-VideoHelperSuite
GRAIN = "社区/胶片颗粒-filmgrain.json"  # needs ComfyUI-FilmGrainFX, which takes KSampler away


def _scan(api: Api) -> None:
    assert api.raw("POST", "/setup/scan").status_code == 202
    deadline = time.monotonic() + 15
    while api.get("/setup/profile")["phase"] != "scanned":
        assert time.monotonic() < deadline, "the scan did not finish"
        time.sleep(0.05)


def _scanned(backend: Backend) -> Api:
    backend.start(DRAMA_SETUP_FAKE_DELAY_MS="0", DRAMA_SETUP_FAKE_TICK_MS="0")
    api = Api(backend)
    _scan(api)
    return api


def _trial(api: Api, workflow_id: str) -> dict[str, Any]:
    started = api.raw("POST", f"/workflows/{workflow_id}/trial")
    assert started.status_code == 202, started.text
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        w: dict[str, Any] = api.get(f"/workflows/{workflow_id}")
        if w["trial"]["status"] != "running":
            return w
        time.sleep(0.05)
    raise AssertionError("the trial did not finish")


def _checks(api: Api) -> dict[str, dict[str, Any]]:
    return {w["slug"]: w["check"] for w in api.get("/workflows")}


def test_a_community_workflow_from_comfyui_to_the_picker(backend: Backend) -> None:
    api = _scanned(backend)
    listed = {f["path"]: f for f in api.get("/comfy/workflows")}
    assert listed[WAN]["imported_as"] is None

    # Imported from ComfyUI's list: bindings guessed, not trusted; checked at once.
    w = api.send("POST", "/workflows/import", json={"comfy_path": WAN})
    assert (w["slug"], w["model_key"], w["tier"]) == ("wan22", "comfy/wan22", "unverified")
    assert w["components"] == ["vid"]
    slots = {b["slot"] for b in w["bindings"]}
    assert slots >= {"first_frame", "prompt", "negative", "seed", "fps", "video_out"}
    assert all(b["state"] == "guessed" for b in w["bindings"])
    check = w["check"]
    assert check["status"] == "missing" and check["missing_models"] == []
    assert [(p["name"], p["classes"]) for p in check["missing_packs"]] == [
        ("ComfyUI-VideoHelperSuite", ["VHS_VideoCombine"])
    ]
    assert {f["path"]: f for f in api.get("/comfy/workflows")}[WAN]["imported_as"] == w["id"]

    # No trial before the bindings are confirmed and the check is clean.
    resp = api.raw("POST", f"/workflows/{w['id']}/trial")
    assert resp.status_code == 409, resp.text
    api.send("PUT", f"/workflows/{w['id']}/bindings", json=w["bindings"])

    # The install lists its change, takes a snapshot first, and the check comes back clean.
    changes = api.send("POST", f"/workflows/{w['id']}/deps")["changes"]
    assert [c["params"]["item"] for c in changes] == ["ComfyUI-VideoHelperSuite"]
    done = api.send("POST", f"/workflows/{w['id']}/deps/install")
    assert done["packs"] == 1 and done["snapshot"] and done["failed"] == []
    assert done["workflow"]["check"]["status"] == "ok"
    snaps = api.get("/comfy/snapshots")
    assert snaps[0]["manager_name"] == done["snapshot"]
    assert snaps[0]["changes"][0]["params"]["item"] == "ComfyUI-VideoHelperSuite"

    # The trial runs on the GPU queue through router.call() (the workflow's hash recorded).
    tried = _trial(api, w["id"])
    assert tried["trial"]["status"] == "passed", tried["trial"]
    job = api.get(f"/jobs/{tried['trial']['job_id']}")
    assert (job["queue"], job["state"]) == ("gpu", "succeeded")
    (call,) = api.calls(job["id"])
    assert call["model_key"] == "comfy/wan22" and call["workflow_sha256"]

    # 我的工作流: offered to 视频生成's picker and to 「不满意换一个」.
    assert api.send("PATCH", f"/workflows/{w['id']}", json={"tier": "mine"})["tier"] == "mine"
    catalog = api.get("/config/components")
    vid = next(c for c in catalog["components"] if c["id"] == "vid")
    assert "comfy/wan22" in vid["local_models"]
    assert next(m for m in catalog["models"] if m["key"] == "comfy/wan22")["tier"] == "mine"
    route = api.get("/config/resolve", component="vid")["values"]
    assert "comfy/wan22" in route["alt_order"]


def test_a_bad_node_pack_is_found_and_rolled_back(backend: Backend) -> None:
    api = _scanned(backend)
    sdxl = api.send("POST", "/workflows/import", json={"comfy_path": "sdxl_basic.json"})
    assert sdxl["check"]["status"] == "ok"
    before = _checks(api)
    grain = api.send("POST", "/workflows/import", json={"comfy_path": GRAIN})
    assert [p["name"] for p in grain["check"]["missing_packs"]] == ["ComfyUI-FilmGrainFX"]

    # The pack goes in after a snapshot; every workflow is checked again and those that worked
    # and use what it broke (KSampler) point back to that snapshot.
    done = api.send("POST", f"/workflows/{grain['id']}/deps/install")
    snap = api.get("/comfy/snapshots")[0]
    assert snap["manager_name"] == done["snapshot"]
    after = _checks(api)
    pointer = {
        "code": "broke_after_install",
        "params": {"snapshot": snap["manager_name"], "snapshot_id": snap["id"]},
    }
    broken = sorted(slug for slug, c in after.items() if pointer in c["problems"])
    assert "sdxl-basic" in broken, broken
    assert all(before[slug]["status"] == "ok" for slug in broken)
    assert {"code": "unknown_node", "params": {"class": "KSampler"}} in after["sdxl-basic"][
        "problems"
    ]
    assert pointer not in after["h3-i2v"]["problems"]  # no KSampler in it

    # 回滚: the sample machine is back at once, every workflow checked again; the next scan
    # (after a real ComfyUI restarts) confirms the restore.
    restored = api.send("POST", f"/comfy/snapshots/{snap['id']}/restore")
    assert restored["restart_required"] is True
    final = _checks(api)
    assert all(final[slug]["status"] == before[slug]["status"] for slug in broken)
    assert not any(pointer in c["problems"] for c in final.values())
    assert final["filmgrain"]["status"] == "missing"  # its pack is gone again
    _scan(api)
    assert api.get("/comfy/snapshots")[0]["restore"]["state"] == "done"
