"""分镜规划 (SPEC 5 ``plan``; M4 step 2), in Mock mode: the demo's nine shots, how long they run,
edits as ``edit`` versions, split and merge, ids across reruns, and what makes the plan stale.
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
from drama_series_agent.core.models_db import Dependency, Product, ProductVersion, Shot

LOCAL = "http://127.0.0.1"
V1 = "/api/v1"
EP1 = "demo-e1"


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(), base_url=LOCAL, headers={"X-Drama-Studio": "1"}) as c:
        yield c


def _state(client: TestClient) -> StudioState:
    state: StudioState = client.app.state.studio  # type: ignore[attr-defined]
    return state


def _rows(client: TestClient, model: Any, *where: Any) -> list[Any]:
    async def read() -> list[Any]:
        async with _state(client).db.session() as s:
            return list((await s.exec(select(model).where(*where))).all())

    return list(client.portal.call(read))  # type: ignore[union-attr]


def _shots(client: TestClient, episode: str = EP1) -> list[dict[str, Any]]:
    r = client.get(f"{V1}/episodes/{episode}/shots")
    assert r.status_code == 200, r.text
    out: list[dict[str, Any]] = r.json()
    return out


def _plan(client: TestClient, episode: str = EP1) -> dict[str, Any]:
    found = client.get(f"{V1}/products", params={"owner": f"episode:{episode}"}).json()
    plan: dict[str, Any] = next(p for p in found if p["slot"] == "shot_plan")
    return plan


def _wait(client: TestClient, job_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 30
    while True:
        job: dict[str, Any] = client.get(f"{V1}/jobs/{job_id}").json()
        if job["state"] in ("succeeded", "failed", "canceled"):
            assert job["state"] == "succeeded", job
            return job
        assert time.monotonic() < deadline, "the job did not finish"
        time.sleep(0.02)


def test_the_demo_has_the_prototypes_nine_shots(client: TestClient) -> None:
    shots = _shots(client)
    assert [s["label"] for s in shots] == [f"1-0{n}" for n in range(1, 10)]
    assert [s["id"] for s in shots] == [f"demo-shot-1-0{n}" for n in range(1, 10)]
    by = {s["label"]: s for s in shots}
    assert by["1-06"]["line_ids"] == ["demo-b8", "demo-b10"]
    assert (by["1-08"]["tail_from"], by["1-09"]["tail_from"]) == ("1-06", "1-08")
    assert by["1-01"]["scene_no"] == 1 and by["1-06"]["scene_no"] == 2
    assert by["1-04"]["dialogue"] and by["1-04"]["dialogue"].endswith("……周屿？")
    # Dialogue by its audio (not dubbed yet: the script's 4 s, a breath each side) …
    assert (by["1-04"]["duration_s"], by["1-04"]["duration_source"]) == (4.5, "audio")
    # … a voice-over only has to fit the action (Kelvin 2026-10-21).
    assert (by["1-06"]["duration_s"], by["1-06"]["duration_source"]) == (5.0, "manual")
    assert by["1-06"]["min_s"] > 0 and by["1-01"]["min_s"] == 0
    assert sum(s["duration_s"] for s in shots) == pytest.approx(34.5)
    assert by["1-01"]["longest_s"] == 15.0 and not any(s["split_hint"] for s in shots)
    # Every shot but the two continuous ones has its keyframe product.
    with_kf = [s["label"] for s in shots if s["keyframe_product_id"]]
    assert with_kf == ["1-01", "1-02", "1-03", "1-04", "1-05", "1-06", "1-07"]
    assert len(_rows(client, Shot, Shot.episode_id == EP1)) == 9


def test_an_edit_is_an_adopted_edit_version(client: TestClient) -> None:
    plan = _plan(client)
    before = len(plan["versions"])
    r = client.patch(f"{V1}/shots/demo-shot-1-05", json={"framing": "wide", "camera_move": "pan"})
    assert r.status_code == 200, r.text
    assert (r.json()["framing"], r.json()["camera_move"]) == ("wide", "pan")
    plan = _plan(client)
    assert len(plan["versions"]) == before + 1
    last = plan["versions"][-1]
    assert last["origin"] == "edit" and plan["adopted_version_id"] == last["id"]
    (row,) = _rows(client, Shot, Shot.id == "demo-shot-1-05")
    assert row.framing == "wide" and row.version_id == last["id"]
    blocking = [{"id": "camera", "kind": "camera", "label": "", "x": 0.2, "y": 0.9}]
    r = client.patch(f"{V1}/shots/demo-shot-1-05", json={"blocking": blocking})
    assert r.json()["blocking"] == blocking
    bad = client.patch(f"{V1}/shots/demo-shot-1-05", json={"asset_ids": ["nobody"]})
    assert bad.status_code == 422 and bad.json()["detail"]["code"] == "asset_not_found"
    assert client.patch(f"{V1}/shots/nope", json={"framing": "wide"}).status_code == 404


def test_a_dialogue_shot_is_never_shorter_than_its_audio(client: TestClient) -> None:
    r = client.patch(f"{V1}/shots/demo-shot-1-04", json={"duration_s": 2})
    assert r.status_code == 422
    assert r.json()["detail"] == {"code": "duration_below_audio", "params": {"min_s": 4.5}}
    longer = client.patch(f"{V1}/shots/demo-shot-1-04", json={"duration_s": 6}).json()
    assert (longer["duration_s"], longer["duration_source"], longer["manual_s"]) == (
        6.0,
        "manual",
        6.0,
    )
    back = client.patch(f"{V1}/shots/demo-shot-1-04", json={"duration_s": None}).json()
    assert (back["duration_s"], back["duration_source"]) == (4.5, "audio")
    silent = client.patch(f"{V1}/shots/demo-shot-1-05", json={"duration_s": 2.5}).json()
    assert (silent["duration_s"], silent["duration_source"]) == (2.5, "manual")


def test_split_and_merge(client: TestClient) -> None:
    after = client.post(f"{V1}/shots/demo-shot-1-06/split", json={}).json()
    assert len(after) == 10
    assert (after[5]["line_ids"], after[6]["line_ids"]) == (["demo-b8"], ["demo-b10"])
    new = after[6]
    assert new["label"] == "1-07" and new["keyframe_product_id"]
    # 1-08 (now 1-09) continued 1-06: it continues the second half.
    assert after[8]["tail_from"] == "1-07"
    back = client.post(f"{V1}/shots/demo-shot-1-06/merge").json()
    assert len(back) == 9 and back[5]["line_ids"] == ["demo-b8", "demo-b10"]
    kf = _rows(client, Product, Product.owner_id == new["id"], Product.slot == "keyframe")
    assert kf and kf[0].retired
    last = client.post(f"{V1}/shots/demo-shot-1-05/merge")
    assert last.status_code == 422 and last.json()["detail"]["code"] == "no_next_shot"
    point = client.post(f"{V1}/shots/demo-shot-1-06/split", json={"after_line_id": "demo-b10"})
    assert point.status_code == 422 and point.json()["detail"]["code"] == "split_point_invalid"


def test_a_rerun_keeps_the_shots_and_waits_to_be_adopted(client: TestClient) -> None:
    plan = _plan(client)
    job = client.post(f"{V1}/products/{plan['id']}/run", json={"mode": "rerun"}).json()
    _wait(client, job["id"])
    plan = _plan(client)
    assert plan["current_version_id"] != plan["adopted_version_id"]
    assert [s["id"] for s in _shots(client)] == [f"demo-shot-1-0{n}" for n in range(1, 10)]


def test_only_a_new_structure_makes_the_plan_stale(client: TestClient) -> None:
    """Rewording a line, spoken or not, leaves the plan as it is (Kelvin 2026-10-21); a line
    added to the script makes it stale."""
    for line_id, text in (("demo-b5", "……是你？"), ("demo-b3", "门口靠着一把红伞。")):
        r = client.patch(f"{V1}/lines/{line_id}", json={"text": text})
        assert r.status_code == 200, r.text
        assert _plan(client)["status"] != "stale"
    state = _state(client)

    async def add_a_line() -> None:
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

    client.portal.call(add_a_line)  # type: ignore[union-attr]
    assert _plan(client)["status"] == "stale"


def test_another_episode_is_planned_by_rules(client: TestClient) -> None:
    """Episode 2's script, then its plan: its product appears once the script is adopted, and
    every line is filmed."""
    found = client.get(f"{V1}/products", params={"owner": "episode:demo-e2"}).json()
    script = next(p for p in found if p["slot"] == "script")
    _wait(
        client, client.post(f"{V1}/products/{script['id']}/run", json={"mode": "run"}).json()["id"]
    )
    plan = _plan(client, "demo-e2")
    _wait(client, client.post(f"{V1}/products/{plan['id']}/run", json={"mode": "run"}).json()["id"])
    shots = _shots(client, "demo-e2")
    assert shots and shots[0]["shot_type"] == "scene_change"
    lines = client.get(f"{V1}/episodes/demo-e2/script").json()["lines"]
    filmed = {x for s in shots for x in s["line_ids"]}
    assert filmed == {x["id"] for x in lines}
    version = _plan(client, "demo-e2")["adopted_version_id"]
    deps = _rows(client, Dependency, Dependency.version_id == version)
    assert {d.slice for d in deps} >= {"shots"}


def test_an_asset_lists_the_shots_it_is_in(client: TestClient) -> None:
    """素材页「出现在」: the adopted plan's shots that reference the asset."""

    def shots_of(asset: str) -> list[str]:
        found = client.get(f"{V1}/series/demo/assets", params={"episode": EP1}).json()
        out: list[str] = next(a for a in found if a["id"] == asset)["shots"]
        return out

    by = {s["label"]: s for s in _shots(client)}
    using = [label for label, s in by.items() if "linwan" in s["asset_ids"]]
    assert using and shots_of("linwan") == using
    # A split is adopted at once: the new shot is listed and the later ones renumbered.
    client.post(f"{V1}/shots/demo-shot-1-06/split", json={})
    after = [s["label"] for s in _shots(client) if "linwan" in s["asset_ids"]]
    assert shots_of("linwan") == after and len(after) == len(using) + 1
