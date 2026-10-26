"""M4 acceptance (plan step 8), against a real backend process in Mock mode: a new series from
the demo novel up to episode 1's locked assets (as in M3), then 分镜规划 (the prototype's nine
shots), a local draft of three for each of the seven keyframes, one picked and finished on the
API model, every shot confirmed with its hashes in ``gate_decision`` and the 分镜 gate; after
全部配音 a dialogue shot runs as long as its audio and a breath each side; and what a new
aspect, or an edit of a locked character, would touch.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest
from test_novel_to_script import Api
from test_script_to_dub import _confirmed_script, _gates, _start

if TYPE_CHECKING:
    from conftest import Backend  # tests/e2e/conftest.py

pytestmark = pytest.mark.e2e

PRE_ROLL_S, POST_ROLL_S = 0.3, 0.2  # pipeline/timing.py


def _locked_assets(api: Api, series: str, e1: str) -> list[dict[str, Any]]:
    """素材分析, a reference for every asset (a voice: its final), each locked; 素材闸门."""
    job = api.send("POST", f"/episodes/{e1}/assets/analyze")
    assert api.until(job["id"], "succeeded", "failed")["state"] == "succeeded"
    assets: list[dict[str, Any]] = api.get(f"/series/{series}/assets", episode=e1)
    for a in assets:
        job = _start(api, a["product_id"])
        if a["kind"] == "voice":
            params = {"source_version_id": job["result"]["version_id"], "source_idx": 0}
            _start(api, a["product_id"], where="api", params=params)
        api.send("POST", f"/assets/{a['id']}/lock", json={"force": True})
    api.send("POST", "/gates/assets/confirm", json={"scope_id": e1})
    return assets


def _shots(api: Api, e1: str) -> dict[str, dict[str, Any]]:
    return {s["label"]: s for s in api.get(f"/episodes/{e1}/shots")}


def _preview(api: Api, kind: str, target: str, patch: dict[str, Any]) -> dict[str, Any]:
    impact: dict[str, Any] = api.send(
        "POST", "/impact/preview", json={"kind": kind, "target_id": target, "patch": patch}
    )
    return impact


def test_from_the_script_to_a_confirmed_storyboard(backend: Backend) -> None:
    backend.start()
    api = Api(backend)
    series, e1 = _confirmed_script(api, "雨停之前（M4 验收）")
    assets = _locked_assets(api, series, e1)
    linwan = next(a for a in assets if (a["kind"], a["name"]) == ("character", "林晚"))

    # 分镜规划: nine shots, 1-08 and 1-09 continue an earlier one; the rest get a keyframe.
    plan = api.product(f"episode:{e1}", "plan")
    _start(api, plan["id"])
    shots = _shots(api, e1)
    assert list(shots) == [f"1-0{n}" for n in range(1, 10)]
    assert (shots["1-08"]["tail_from"], shots["1-09"]["tail_from"]) == ("1-06", "1-08")
    drawn = [s for s in shots.values() if s["keyframe_product_id"]]
    assert [s["label"] for s in drawn] == [f"1-0{n}" for n in range(1, 8)]
    assert linwan["id"] in shots["1-04"]["asset_ids"]
    assert sum(s["duration_s"] for s in shots.values()) == pytest.approx(34.5)

    # 分镜确认 before any shot is confirmed: refused, with the shots.
    resp = api.raw("POST", "/gates/storyboard/confirm", json={"scope_id": e1})
    assert resp.status_code == 409 and resp.json()["detail"]["code"] == "shots_not_confirmed"
    assert resp.json()["detail"]["params"]["count"] == 9

    # Seven keyframes: a local draft of three each, through router.call() (model_call names the
    # product). Candidates wait to be picked: nothing is adopted, the spec stays open.
    for s in drawn:
        job = _start(api, s["keyframe_product_id"])
        v = api.get(f"/products/{s['keyframe_product_id']}")["versions"][-1]
        assert (v["stage"], v["where"]) == ("draft", "local"), s["label"]
        assert len([f for f in v["files"] if f["role"] == "candidate"]) == 3
        calls = [c for c in api.calls(job["id"]) if c["status"] == "success"]
        assert calls and {c["product_id"] for c in calls} == {s["keyframe_product_id"]}
    assert api.get(f"/series/{series}/spec")["locked_at"] is None

    # 1-04: candidate B picked, then finished on the API model from it.
    kf = shots["1-04"]["keyframe_product_id"]
    draft = api.get(f"/products/{kf}")["versions"][-1]
    picked = api.send("PATCH", f"/shots/{shots['1-04']['id']}", json={"keyframe_pick": 1})
    b = next(f for f in draft["files"] if f["role"] == "candidate" and f["idx"] == 1)
    assert picked["keyframe_sha256"] == b["sha256"]
    _start(api, kf, where="api", params={"source_version_id": draft["id"], "source_idx": 1})
    final = api.get(f"/products/{kf}")["versions"][-1]
    assert (final["stage"], final["where"], final["parent_version_id"]) == (
        "final",
        "api",
        draft["id"],
    )

    # Every shot confirmed (the first keyframe adopted locks the spec, SPEC 13.3), then 分镜确认:
    # the keyframes and the plan are locked.
    for s in shots.values():
        api.send("PATCH", f"/shots/{s['id']}", json={"confirmed": True})
    assert api.get(f"/series/{series}/spec")["locked_at"] is not None
    api.send("POST", "/gates/storyboard/confirm", json={"scope_id": e1})
    progress = api.get(f"/episodes/{e1}/progress")["steps"]["storyboard"]
    assert progress == {"state": "confirmed", "done": 9, "total": 9, "stale": 0}
    assert api.get(f"/products/{plan['id']}")["locked_hash"]
    for s in drawn:
        assert api.get(f"/products/{s['keyframe_product_id']}")["locked_hash"], s["label"]

    # Each shot's decision holds the hashes of its settings (the plan) and of its keyframe.
    decisions = _gates(backend, series)
    by_shot = {
        scope: json.loads(hashes)
        for gate, scope, action, hashes in decisions
        if gate == "shot" and action == "confirm"
    }
    assert set(by_shot) == {s["id"] for s in shots.values()}
    for s in shots.values():
        mine = {plan["id"], *([s["keyframe_product_id"]] if s["keyframe_product_id"] else [])}
        assert set(by_shot[s["id"]]) == mine, s["label"]
        assert all(h.startswith("sha256:") for h in by_shot[s["id"]].values())
    assert ("storyboard", e1, "confirm") in {(g, sc, a) for g, sc, a, _ in decisions}

    # 全部配音: a dialogue shot runs as long as its audio with a breath each side; a voice-over
    # only has to fit. Nothing confirmed goes stale: the length is worked out when read.
    started = api.send("POST", f"/episodes/{e1}/dub", json={})
    for job_id in started["jobs"]:
        assert api.until(job_id, "succeeded", "failed")["state"] == "succeeded"
    audio = {
        x["line_id"]: x["audio"]["duration_s"] for x in api.get(f"/episodes/{e1}/dub")["lines"]
    }
    after = _shots(api, e1)
    spoken = audio[after["1-04"]["line_ids"][0]]
    assert after["1-04"]["duration_s"] == pytest.approx(PRE_ROLL_S + spoken + POST_ROLL_S)
    assert after["1-04"]["duration_source"] == "audio"
    over = audio[after["1-06"]["line_ids"][1]]
    assert after["1-06"]["duration_s"] == pytest.approx(max(5.0, PRE_ROLL_S + over + POST_ROLL_S))
    assert all(s["confirmed"] and not s["confirm_stale"] for s in after.values())

    # 改画幅: the seven keyframes would be drawn again, an API final each.
    impact = _preview(api, "spec_aspect", series, {"aspect": "16:9", "platform": "wide"})
    redraw = next(x for x in impact["lines"] if x["code"] == "keyframes_redraw")
    assert redraw["params"] == {"count": 7, "shots": 9}
    assert redraw["cost_usd"] == pytest.approx(7 * 0.0504, abs=0.01)  # a Nano Banana 2.1 final each

    # Editing the locked 林晚 lists the shots she is in.
    impact = _preview(api, "asset_edit", linwan["id"], {"intent": "26 岁，短发，米色风衣。"})
    refs = next(x for x in impact["lines"] if x["code"] == "shot_refs")
    assert refs["params"] == {"ids": "1-01、1-04、1-05、1-06、1-08、1-09", "count": 6}
    redrawn = next(x for x in impact["lines"] if x["code"] == "shots_confirmed_redraw")
    # Those with a keyframe of their own are drawn again (1-08 and 1-09 have none).
    assert redrawn["params"] == {"shots": "1-01、1-04、1-05、1-06", "count": 4}
