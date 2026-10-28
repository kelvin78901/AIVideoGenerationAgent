"""M5 acceptance (plan step 13), against a real backend process in Mock mode: the demo series as
the app seeds it (分镜 confirmed, 1-01–1-03 adopted at 2K, 1-04's four takes waiting to be
picked), then 生成: a shot's first run makes two local takes through ``router.call()`` (each
``model_call`` names its workflow, file hash and why it was chosen); one adopted, dropped and
another adopted; 「用 API 出终版」 at its estimate makes a 2K final from the draft; the header's
spend follows the calls; the 生成 gate refuses until every shot has an adopted take, then locks
them; the run log tells the story.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from test_novel_to_script import Api
from test_script_to_dub import _start

if TYPE_CHECKING:
    from conftest import Backend  # tests/e2e/conftest.py

pytestmark = pytest.mark.e2e

EP = "demo-e1"
LABELS = [f"1-0{n}" for n in range(1, 10)]


def _shots(api: Api) -> dict[str, dict[str, Any]]:
    return {s["label"]: s for s in api.get(f"/episodes/{EP}/shots")}


def _video(api: Api, shot: dict[str, Any]) -> dict[str, Any]:
    product: dict[str, Any] = api.get(f"/products/{shot['video_product_id']}")
    return product


def _spent(api: Api) -> float:
    return float(api.get("/metrics/summary", scope="episode", episode=EP)["spent_usd"])


def _badge(api: Api) -> dict[str, Any]:
    return dict(api.get(f"/episodes/{EP}/progress")["steps"]["generate"])


def _adopt(api: Api, version: dict[str, Any]) -> None:
    api.send("POST", f"/versions/{version['id']}/adopt")


def _dub(api: Api, shot: dict[str, Any]) -> None:
    """Dub the shot's spoken lines (「配音」 on the episode's dubbing list)."""
    spoken = {x["line_id"] for x in api.get(f"/episodes/{EP}/dub")["lines"]}
    ids = [x for x in shot["line_ids"] if x in spoken]
    started = api.send("POST", f"/episodes/{EP}/dub", json={"line_ids": ids})
    for job_id in started["jobs"]:
        assert api.until(job_id, "succeeded", "failed")["state"] == "succeeded"


def test_from_the_confirmed_storyboard_to_the_generate_gate(backend: Backend) -> None:
    backend.start()
    api = Api(backend)
    shots = _shots(api)
    assert list(shots) == LABELS
    steps = api.get(f"/episodes/{EP}/progress")["steps"]
    assert steps["storyboard"]["state"] == "confirmed"

    # The seeded takes, as in the prototype.
    videos = {label: _video(api, s) for label, s in shots.items()}
    for label in ("1-01", "1-02", "1-03"):
        adopted = next(
            v for v in videos[label]["versions"] if v["id"] == videos[label]["adopted_version_id"]
        )
        assert (adopted["stage"], adopted["where"]) == ("final", "api"), label
        draft = next(
            v for v in videos[label]["versions"] if v["id"] == adopted["parent_version_id"]
        )
        assert (draft["where"], draft["model_key"]) == ("local", "comfy/h3"), label
    waiting = videos["1-04"]["versions"]
    assert len(waiting) == 4 and videos["1-04"]["adopted_version_id"] is None
    assert {v["origin"] for v in waiting} == {"run", "fallback", "switch"}
    assert all(not videos[label]["versions"] for label in LABELS[4:])
    assert _badge(api) == {"state": "in_progress", "done": 3, "total": 9, "stale": 0}
    spent = _spent(api)

    # 1-05's first run: two local takes from its keyframe, each through router.call(); the call
    # names the workflow, its file hash and why it was chosen (as the take's params do).
    job = _start(api, shots["1-05"]["video_product_id"])
    takes = _video(api, shots["1-05"])["versions"]
    assert len(takes) == 2
    assert all((t["where"], t["stage"]) == ("local", "draft") for t in takes)
    calls = [c for c in api.calls(job["id"]) if c["status"] == "success"]
    clips = [c for c in calls if c["model_key"] == takes[0]["model_key"]]
    assert len(clips) == 2 and {t["job_id"] for t in takes} == {job["id"]}
    for c in clips:
        assert c["workflow_id"] and c["workflow_sha256"], c
        assert c["select_json"]["by"] in ("rule", "default"), c
    assert takes[0]["params"]["select"] == clips[0]["select_json"]
    # The rewrite into H3's official layout is one call for both takes.
    assert [c["component_id"] for c in calls if c["model_key"] != takes[0]["model_key"]] == [
        "vprompt"
    ]
    assert _spent(api) == pytest.approx(spent + sum(c["cost_usd"] for c in calls), abs=1e-4)

    # Adopt A, drop it, adopt B.
    _adopt(api, takes[0])
    api.send("POST", f"/products/{shots['1-05']['video_product_id']}/unadopt")
    assert _video(api, shots["1-05"])["adopted_version_id"] is None
    _adopt(api, takes[1])

    # 「用 API 出终版」 at the price the card shows: one 2K final from the draft.
    product = _video(api, shots["1-05"])
    price = product["estimate"]["final_usd"]
    assert price > 0
    spent = _spent(api)
    job = _start(api, product["id"], where="api", params={"source_version_id": takes[1]["id"]})
    final = next(v for v in _video(api, shots["1-05"])["versions"] if v["stage"] == "final")
    assert (final["model_key"], final["parent_version_id"]) == (
        "minimax/h3-regenerate-2k",
        takes[1]["id"],
    )
    assert (final["files"][0]["w"], final["files"][0]["h"]) == (1440, 2560)
    (call,) = [c for c in api.calls(job["id"]) if c["status"] == "success"]
    assert call["cost_usd"] == pytest.approx(price, abs=0.001)
    assert _spent(api) == pytest.approx(spent + call["cost_usd"], abs=1e-4)
    _adopt(api, final)

    # 生成确认 before every shot has a take: refused, with the shots still open.
    resp = api.raw("POST", "/gates/takes/confirm", json={"scope_id": EP})
    assert resp.status_code == 409, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == "takes_not_adopted" and detail["params"]["count"] == 5
    assert detail["params"]["labels"].startswith("1-04、1-06")

    # 1-04: the Seedance take. The rest one take each, in order (1-08 continues 1-06's last
    # frame, 1-09 1-08's); 1-06 is dubbed first, so its lines are dubbed before it runs. An API
    # take costs money in Mock too (it used to be 0 at the delivery tier).
    _adopt(api, next(v for v in waiting if v["model_key"] == "volc/seedance-2.5"))
    _dub(api, shots["1-06"])
    for label in ("1-06", "1-07", "1-08", "1-09"):
        _start(api, shots[label]["video_product_id"], count=1)
        _adopt(api, _video(api, shots[label])["versions"][-1])
    spent = _spent(api)
    job = _start(api, shots["1-07"]["video_product_id"], count=1, model="minimax/h3-api")
    api_calls = [c for c in api.calls(job["id"]) if c["model_key"] == "minimax/h3-api"]
    assert api_calls and all(c["cost_usd"] > 0 for c in api_calls)
    assert _spent(api) > spent
    assert _badge(api) == {"state": "in_progress", "done": 9, "total": 9, "stale": 0}

    # 生成确认: the adopted takes are locked; reopening unlocks them.
    api.send("POST", "/gates/takes/confirm", json={"scope_id": EP})
    assert _badge(api)["state"] == "confirmed"
    for label in LABELS:
        assert _video(api, shots[label])["locked_hash"], label
    api.send("POST", "/gates/takes/reopen", json={"scope_id": EP})
    assert _badge(api)["state"] == "in_progress"
    assert not _video(api, shots["1-05"])["locked_hash"]

    # The run log has 1-05's takes and its final.
    log = api.get(f"/episodes/{EP}/generate-log")
    codes = [e["message"]["code"] for e in log if e["shot_label"] == "1-05"]
    assert sorted(codes) == ["final", "take", "take"], codes
