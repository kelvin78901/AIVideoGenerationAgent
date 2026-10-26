"""分镜确认, the 分镜 badge and the storyboard's impact lines (M4 step 4), in Mock mode.

The demo: 9 shots, 1-01–1-03 confirmed (each with a locked API final), 1-04–1-07 with a local
draft, 1-08 and 1-09 continuous.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import select

from drama_series_agent.api.app import create_app
from drama_series_agent.api.state import StudioState
from drama_series_agent.core.models_db import Product, ProductVersion

LOCAL = "http://127.0.0.1"
V1 = "/api/v1"
EP1 = "demo-e1"
PLAN = "demo-p-plan-e1"


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(), base_url=LOCAL, headers={"X-Drama-Studio": "1"}) as c:
        yield c


def _state(client: TestClient) -> StudioState:
    state: StudioState = client.app.state.studio  # type: ignore[attr-defined]
    return state


def _code(resp: Any) -> str:
    return str(resp.json()["detail"]["code"])


def _shots(client: TestClient) -> dict[str, dict[str, Any]]:
    return {s["label"]: s for s in client.get(f"{V1}/episodes/{EP1}/shots").json()}


def _badge(client: TestClient) -> dict[str, Any]:
    steps: dict[str, Any] = client.get(f"{V1}/episodes/{EP1}/progress").json()["steps"]
    return dict(steps["storyboard"])


def _product(client: TestClient, product_id: str) -> dict[str, Any]:
    data: dict[str, Any] = client.get(f"{V1}/products/{product_id}").json()
    return data


def _preview(client: TestClient, kind: str, target: str, patch: dict[str, Any]) -> dict[str, Any]:
    resp = client.post(
        f"{V1}/impact/preview", json={"kind": kind, "target_id": target, "patch": patch}
    )
    assert resp.status_code == 200, resp.text
    data: dict[str, Any] = resp.json()
    return data


def _apply(client: TestClient, impact_id: str, action: str) -> dict[str, Any]:
    resp = client.post(f"{V1}/impact/apply", json={"impact_id": impact_id, "action": action})
    assert resp.status_code == 200, resp.text
    data: dict[str, Any] = resp.json()
    return data


def _lines(impact: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {x["code"]: x for x in impact["lines"]}


def _wait(client: TestClient, job_id: str) -> None:
    deadline = time.monotonic() + 30
    while True:
        job = client.get(f"{V1}/jobs/{job_id}").json()
        if job["state"] in ("succeeded", "failed", "canceled"):
            assert job["state"] == "succeeded", job
            return
        assert time.monotonic() < deadline, "the job did not finish"
        time.sleep(0.02)


def _confirm_all(client: TestClient) -> None:
    for label, shot in _shots(client).items():
        if not shot["confirmed"]:
            resp = client.patch(f"{V1}/shots/{shot['id']}", json={"confirmed": True})
            assert resp.status_code == 200, (label, resp.text)


def test_the_badge_counts_the_confirmed_shots(client: TestClient) -> None:
    assert _badge(client) == {"state": "in_progress", "done": 3, "total": 9, "stale": 0}
    assert client.get(f"{V1}/series/demo/episodes").json()[0]["shot_count"] == 9


def test_the_gate_needs_every_shot_confirmed(client: TestClient) -> None:
    resp = client.post(f"{V1}/gates/storyboard/confirm", json={"scope_id": EP1})
    assert resp.status_code == 409 and _code(resp) == "shots_not_confirmed"
    params = resp.json()["detail"]["params"]
    assert params == {"count": 6, "labels": "1-04、1-05、1-06、1-07、1-08、1-09"}
    _confirm_all(client)
    resp = client.post(f"{V1}/gates/storyboard/confirm", json={"scope_id": EP1})
    assert resp.status_code == 200, resp.text
    assert _product(client, PLAN)["locked_hash"]
    assert _badge(client) == {"state": "confirmed", "done": 9, "total": 9, "stale": 0}
    # Taking one shot back reopens the gate and unlocks the plan.
    client.patch(f"{V1}/shots/demo-shot-1-04", json={"confirmed": False}).raise_for_status()
    assert _badge(client)["state"] == "in_progress"
    assert not _product(client, PLAN)["locked_hash"]


def test_editing_a_shot_of_a_confirmed_storyboard(client: TestClient) -> None:
    _confirm_all(client)
    client.post(f"{V1}/gates/storyboard/confirm", json={"scope_id": EP1}).raise_for_status()
    assert client.patch(f"{V1}/shots/demo-shot-1-05", json={"framing": "wide"}).status_code == 409
    impact = _preview(client, "shot_edit", "demo-shot-1-05", {"framing": "wide"})
    lines = _lines(impact)
    assert lines["self_shot_plan"]["params"] == {"n": 1}
    assert lines["stale_keyframe"]["params"] == {"n": 1, "count": 1, "shots": "1-05"}
    assert lines["shot_reconfirm"]["params"] == {"shots": "1-05", "count": 1}
    assert lines["gate_storyboard"]["params"] == {"n": 1}
    assert _apply(client, impact["id"], "mark")["job_ids"] == []
    shots = _shots(client)
    assert shots["1-05"]["framing"] == "wide" and not shots["1-05"]["confirmed"]
    assert shots["1-04"]["confirmed"]  # only the edited one
    assert _badge(client)["state"] == "in_progress"
    assert not _product(client, PLAN)["locked_hash"]
    kf = _product(client, shots["1-05"]["keyframe_product_id"])
    assert kf["status"] == "stale" and not kf["locked_hash"]


def test_a_confirmed_shot_with_a_new_description_is_drawn_again(client: TestClient) -> None:
    impact = _preview(
        client, "shot_edit", "demo-shot-1-02", {"intent": "门口的红伞，伞尖还在滴水。"}
    )
    lines = _lines(impact)
    assert set(lines) == {"shot_reconfirm", "shot_redraw"}  # no plan change: no slice moves
    applied = _apply(client, impact["id"], "rerun")
    assert len(applied["job_ids"]) == 1
    _wait(client, applied["job_ids"][0])
    shot = _shots(client)["1-02"]
    assert shot["intent"] == "门口的红伞，伞尖还在滴水。" and not shot["confirmed"]
    kf = _product(client, shot["keyframe_product_id"])
    assert kf["versions"][-1]["stage"] == "draft" and kf["versions"][-1]["intent"] == shot["intent"]


def test_splitting_a_confirmed_shot_goes_through_the_preview(client: TestClient) -> None:
    resp = client.post(f"{V1}/shots/demo-shot-1-01/split", json={})
    assert resp.status_code == 409 and _code(resp) == "shot_confirmed"
    impact = _preview(client, "shot_edit", "demo-shot-1-01", {"split": {}})
    assert _lines(impact)["shot_reconfirm"]["params"] == {"shots": "1-01", "count": 1}
    _apply(client, impact["id"], "mark")
    shots = _shots(client)
    assert len(shots) == 10 and not shots["1-01"]["confirmed"] and shots["1-02"]["line_ids"]


def test_a_new_aspect_lists_the_keyframes(client: TestClient) -> None:
    impact = _preview(client, "spec_aspect", "demo", {"aspect": "16:9", "platform": "wide"})
    lines = _lines(impact)
    redraw = lines["keyframes_redraw"]
    assert redraw["params"] == {"count": 7, "shots": 9}
    assert redraw["cost_usd"] == pytest.approx(7 * 0.134, abs=0.01)  # an API final each
    # Scene pictures are drawn 16:9 whatever the spec (components.yaml): nothing to redraw.
    assert "ref_images_suggest" not in lines
    assert impact["stale"] == {"storyboard": 7}
    assert impact["unaffected"]["code"] == "unaffected_spec"
    assert impact["rerun_cost_usd"] == pytest.approx(redraw["cost_usd"])
    # 只改这里: the spec changes, the confirmed shots are taken back, the keyframes are stale.
    assert _apply(client, impact["id"], "mark")["job_ids"] == []
    assert client.get(f"{V1}/series/demo/spec").json()["aspect"] == "16:9"
    shots = _shots(client)
    assert not any(s["confirmed"] for s in shots.values())
    assert _product(client, shots["1-04"]["keyframe_product_id"])["status"] == "stale"
    assert _badge(client) == {"state": "in_progress", "done": 0, "total": 9, "stale": 7}


def test_a_new_aspect_and_sync_draws_the_keyframes_again(client: TestClient) -> None:
    impact = _preview(client, "spec_aspect", "demo", {"aspect": "16:9", "platform": "wide"})
    applied = _apply(client, impact["id"], "rerun")
    assert len(applied["job_ids"]) == 7
    for job_id in applied["job_ids"]:
        _wait(client, job_id)
    kf = _product(client, _shots(client)["1-04"]["keyframe_product_id"])
    assert kf["versions"][-1]["payload"]["aspect"] == "16:9" and kf["status"] != "stale"


def test_editing_a_locked_character_lists_her_shots(client: TestClient) -> None:
    impact = _preview(client, "asset_edit", "linwan", {"intent": "26 岁，短发，米色风衣。"})
    lines = _lines(impact)
    assert lines["shot_refs"]["params"] == {"ids": "1-01、1-04、1-05、1-06、1-08、1-09", "count": 6}
    assert lines["shots_confirmed_redraw"]["params"] == {"shots": "1-01", "count": 1}
    assert lines["uses_keyframe"]["params"] == {"count": 4, "names": "1-01、1-04、1-05、1-06"}


def test_an_action_line_makes_one_keyframe_stale(client: TestClient) -> None:
    client.post(f"{V1}/gates/script/confirm", json={"scope_id": EP1}).raise_for_status()
    impact = _preview(client, "line_edit", "demo-b2", {"text": "她把伞靠在门边。"})
    _apply(client, impact["id"], "mark")
    shots = _shots(client)
    assert [label for label, s in shots.items() if s["confirm_stale"]] == ["1-01"]
    stale = [
        label
        for label, s in shots.items()
        if s["keyframe_product_id"]
        and _product(client, s["keyframe_product_id"])["status"] == "stale"
    ]
    assert stale == ["1-01"]
    assert _badge(client)["stale"] == 1
    # A spoken line: its shot runs as long as the new audio, nothing to redraw.
    spoken = _preview(client, "line_edit", "demo-b5", {"text": "……是周屿吗？"})
    assert _lines(spoken)["shot_duration_follows"]["params"] == {"shots": "1-04", "count": 1}
    assert "stale_keyframe" not in _lines(spoken)


def test_a_sync_never_redoes_the_plan(client: TestClient) -> None:
    """A line added to the script makes the plan stale; 确认并同步 leaves it to the user."""
    state = _state(client)
    before = len(_product(client, PLAN)["versions"])

    async def add_a_line() -> str:
        async with state.db.session() as s:
            script = (
                await s.exec(
                    select(Product).where(Product.owner_id == EP1, Product.slot == "script")
                )
            ).one()
            base = await s.get(ProductVersion, script.adopted_version_id)
        assert base is not None
        payload = json.loads(json.dumps(base.payload_json))
        payload["scenes"][0]["lines"].append(
            {"id": "demo-new", "type": "action", "text": "雨更大了。"}
        )
        await state.products.append_edit(script.id, base, payload)
        return script.id

    script_id = client.portal.call(add_a_line)  # type: ignore[union-attr]
    assert _product(client, PLAN)["status"] == "stale"
    jobs = client.portal.call(state.cascade.start, "demo", script_id)  # type: ignore[union-attr]
    for job_id in jobs:
        _wait(client, job_id)
    ran = [j["params"].get("product_id") for j in client.get(f"{V1}/jobs").json()]
    assert PLAN not in ran
    plan = _product(client, PLAN)
    assert len(plan["versions"]) == before and plan["status"] == "stale"
