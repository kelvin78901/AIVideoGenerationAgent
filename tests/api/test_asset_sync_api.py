"""素材闸门、影响范围、级联 (M3 step 8), in Mock mode: an episode's assets gate needs every
asset it uses locked; unlocking one reopens it; a reworded line re-dubs that line alone; a new
voice makes its character's lines stale; a script sync never redraws nor unlocks an asset.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from drama_series_agent.api.app import create_app
from drama_series_agent.api.state import StudioState

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


def _call(client: TestClient, fn: Any, *args: Any) -> Any:
    return client.portal.call(fn, *args)  # type: ignore[union-attr]


def _code(resp: Any) -> str:
    return str(resp.json()["detail"]["code"])


def _jobs(client: TestClient) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = client.get(f"{V1}/jobs", params={"limit": 500}).json()
    return jobs


def _drain(client: TestClient) -> None:
    """Wait until nothing is queued or running and the cascade has settled."""
    deadline = time.monotonic() + 30
    quiet = 0
    while time.monotonic() < deadline:
        busy = any(j["state"] in ("queued", "running") for j in _jobs(client))
        busy = busy or _state(client).cascade._lock.locked()
        quiet = 0 if busy else quiet + 1
        if quiet >= 5:
            return
        time.sleep(0.03)
    raise AssertionError("jobs did not settle")


def _wait(client: TestClient, job_id: str, *states: str) -> dict[str, Any]:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        job: dict[str, Any] = client.get(f"{V1}/jobs/{job_id}").json()
        if job["state"] in (states or ("succeeded", "failed", "canceled")):
            return job
        time.sleep(0.02)
    raise AssertionError("job did not get there")


def _assets(client: TestClient) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = client.get(
        f"{V1}/series/demo/assets", params={"episode": EP1}
    ).json()
    return out


def _steps(client: TestClient) -> dict[str, Any]:
    steps: dict[str, Any] = client.get(f"{V1}/episodes/{EP1}/progress").json()["steps"]
    return steps


def _dub(client: TestClient) -> dict[str, Any]:
    out: dict[str, Any] = client.get(f"{V1}/episodes/{EP1}/dub").json()
    return out


def _dub_all(client: TestClient) -> None:
    started = client.post(f"{V1}/episodes/{EP1}/dub", json={}).json()
    for job_id in started["jobs"]:
        assert _wait(client, job_id)["state"] == "succeeded"


def _preview(client: TestClient, kind: str, target: str, patch: dict[str, Any]) -> dict[str, Any]:
    resp = client.post(
        f"{V1}/impact/preview", json={"kind": kind, "target_id": target, "patch": patch}
    )
    assert resp.status_code == 200, resp.text
    out: dict[str, Any] = resp.json()
    return out


def _apply(client: TestClient, impact_id: str, action: str) -> dict[str, Any]:
    resp = client.post(f"{V1}/impact/apply", json={"impact_id": impact_id, "action": action})
    assert resp.status_code == 200, resp.text
    out: dict[str, Any] = resp.json()
    return out


def _versions(client: TestClient, product_id: str) -> int:
    return len(client.get(f"{V1}/products/{product_id}").json()["versions"])


def test_the_assets_gate_needs_every_asset_of_the_episode_locked(client: TestClient) -> None:
    used = [a for a in _assets(client) if a["scenes"]]
    waiting = [a for a in used if a["status"] != "locked"]
    assert len(used) == 10 and len(waiting) == 3
    resp = client.post(f"{V1}/gates/assets/confirm", json={"scope_id": EP1})
    assert resp.status_code == 409 and _code(resp) == "assets_not_locked"
    params = resp.json()["detail"]["params"]
    assert params["count"] == 3 and set(params["names"].split("、")) == {a["name"] for a in waiting}

    for a in waiting:  # force: on-screen text OCR may read the first candidate differently
        resp = client.post(f"{V1}/assets/{a['id']}/lock", json={"force": True})
        assert resp.status_code == 200, resp.text
    assert _steps(client)["assets"] == {
        "state": "in_progress", "done": 10, "total": 10, "stale": 0
    }  # fmt: skip
    resp = client.post(f"{V1}/gates/assets/confirm", json={"scope_id": EP1})
    assert resp.status_code == 200, resp.text
    assert _steps(client)["assets"]["state"] == "confirmed"

    # Unlocking one reopens the episode; its other assets stay locked.
    target = waiting[0]
    impact = _preview(client, "asset_unlock", target["id"], {})
    _apply(client, impact["id"], "mark")
    steps = _steps(client)["assets"]
    assert (steps["state"], steps["done"]) == ("in_progress", 9)
    assert {a["id"] for a in _assets(client) if a["status"] == "locked"} >= {
        a["id"] for a in used if a["id"] != target["id"]
    }


def test_a_reworded_line_redubs_that_line_alone(client: TestClient) -> None:
    _dub_all(client)
    lines = {x["text"]: x for x in _dub(client)["lines"]}
    target, other = lines["……周屿？"], lines["三年了。他凭什么。"]
    impact = _preview(client, "line_edit", target["line_id"], {"text": "……是周屿吗？"})
    dubbing = [x for x in impact["lines"] if x["code"] == "stale_line_audio"]
    assert len(dubbing) == 1 and dubbing[0]["params"] == {"count": 1}
    assert dubbing[0]["cost_usd"] and impact["stale"] == {"assets": 1}

    out = _apply(client, impact["id"], "rerun")
    assert len(out["job_ids"]) == 1
    _drain(client)
    now = {x["line_id"]: x for x in _dub(client)["lines"]}
    assert now[target["line_id"]]["status"] == "done"
    assert now[target["line_id"]]["text"] == "……是周屿吗？"
    assert _versions(client, target["product_id"]) == 2
    assert _versions(client, other["product_id"]) == 1


def test_a_new_voice_makes_its_characters_lines_stale(client: TestClient) -> None:
    _dub_all(client)
    assert {x["status"] for x in _dub(client)["lines"]} == {"done"}
    impact = _preview(client, "asset_unlock", "vlinwan", {})
    _apply(client, impact["id"], "mark")
    # Another final, from audition B, locked: the dubbing read the old voice.
    voice = client.get(f"{V1}/products/demo-p-asset-vlinwan").json()
    draft = next(v for v in voice["versions"] if any(f["role"] == "candidate" for f in v["files"]))
    body = {
        "mode": "run",
        "where": "api",
        "params": {"source_version_id": draft["id"], "source_idx": 1},
    }
    job = client.post(f"{V1}/products/demo-p-asset-vlinwan/run", json=body).json()
    job = _wait(client, job["id"], "waiting_confirm")  # over the $3 cap
    client.post(f"{V1}/jobs/{job['id']}/confirm").raise_for_status()
    assert _wait(client, job["id"])["state"] == "succeeded"
    resp = client.post(f"{V1}/assets/vlinwan/lock", json={})
    assert resp.status_code == 200, resp.text
    lines = _dub(client)["lines"]
    assert lines and {x["status"] for x in lines} == {"stale"}
    assert _steps(client)["assets"]["stale"] == len(lines)


def test_a_script_sync_never_redraws_nor_unlocks_an_asset(client: TestClient) -> None:
    locked = {a["id"]: a for a in _assets(client) if a["status"] == "locked"}
    counts = {i: _versions(client, a["product_id"]) for i, a in locked.items()}
    novel = client.get(f"{V1}/series/demo/novel", params={"chapter": 0}).json()
    paras = [p["text"] for p in novel["paragraphs"]]
    patch = {
        "chapter": 0,
        "title": novel["chapters"][0]["title"],
        "paragraphs": [paras[0] + "楼道的灯又闪了一下。", *paras[1:]],
    }
    impact = _preview(client, "novel_edit", "demo", patch)
    _apply(client, impact["id"], "rerun")
    _drain(client)
    now = {a["id"]: a for a in _assets(client)}
    for asset_id, before in locked.items():
        assert now[asset_id]["status"] == "locked", asset_id
        assert _versions(client, before["product_id"]) == counts[asset_id], asset_id


def test_candidates_are_the_cascades_stop_set(client: TestClient) -> None:
    """Pictures, on-screen text and voices wait for the user's pick: a cascade never reruns
    them (settling would adopt a take nobody chose). Views and dubbing follow."""
    _dub_all(client)
    state = _state(client)

    async def slots() -> dict[str, bool]:
        from sqlmodel import select

        from drama_series_agent.core.models_db import Product

        async with state.db.session() as s:
            rows = (await s.exec(select(Product).where(Product.series_id == "demo"))).all()
        return {p.slot: state.cascade._cascades(p) for p in rows}

    found: dict[str, bool] = _call(client, slots)
    assert {k: found[k] for k in ("ref_image", "text_image", "voice")} == dict.fromkeys(
        ("ref_image", "text_image", "voice"), False
    )
    assert all(found[k] for k in ("ref_views", "line_audio", "script", "asset_list"))


def _product(client: TestClient, asset_id: str) -> dict[str, Any]:
    out: dict[str, Any] = client.get(f"{V1}/products/demo-p-asset-{asset_id}").json()
    return out


def test_editing_a_locked_asset_previews_what_follows(client: TestClient) -> None:
    before = _product(client, "linwan")
    impact = _preview(client, "asset_edit", "linwan", {"intent": "二十六岁，短发。"})
    codes = {x["code"]: x for x in impact["lines"]}
    assert codes["asset_redraw"]["params"] == {"name": "林晚", "kind": "character"}
    assert codes["uses_ref_views"]["params"] == {"name": "林晚"}
    assert codes["asset_in_scenes"]["params"] == {"scenes": "1、2", "count": 2}
    assert impact["unaffected"]["code"] == "edit_keeps_ref"
    # 只改这里: the description is saved, the locked picture and what reads it stay.
    assert _apply(client, impact["id"], "mark")["job_ids"] == []
    after = _product(client, "linwan")
    assert after["prompt"]["intent"] == "二十六岁，短发。"
    assert after["locked_hash"] == before["locked_hash"]
    assert len(after["versions"]) == len(before["versions"])
    views = client.get(f"{V1}/products", params={"owner": "asset:linwan"}).json()
    assert all(p["status"] != "stale" for p in views)

    bad = client.post(
        f"{V1}/impact/preview",
        json={"kind": "asset_edit", "target_id": "room", "patch": {"intent": "x"}},
    )
    assert bad.status_code == 409 and _code(bad) == "not_locked"  # edited in place instead
    bad = client.post(
        f"{V1}/impact/preview",
        json={"kind": "asset_edit", "target_id": "linwan", "patch": {"pick": 1}},
    )
    assert bad.status_code == 422


def test_sync_after_editing_a_locked_voice_draws_new_auditions(client: TestClient) -> None:
    _dub_all(client)
    unlock = _preview(client, "asset_unlock", "vlinwan", {})
    dubbing = next(x for x in unlock["lines"] if x["code"] == "uses_line_audio")
    assert dubbing["params"] == {"name": "林晚", "count": 2}
    client.post(f"{V1}/impact/apply", json={"impact_id": unlock["id"], "action": "undo"})

    before = _product(client, "vlinwan")
    impact = _preview(client, "asset_edit", "vlinwan", {"intent": "更低沉一点。"})
    assert {x["code"] for x in impact["lines"]} >= {"asset_redraw", "uses_line_audio"}
    out = _apply(client, impact["id"], "rerun")
    assert len(out["job_ids"]) == 1
    assert _wait(client, out["job_ids"][0])["state"] == "succeeded"
    after = _product(client, "vlinwan")
    # New auditions to choose from; the locked final still voices the lines.
    assert len(after["versions"]) == len(before["versions"]) + 1
    assert after["locked_hash"] == before["locked_hash"]
    assert after["adopted_version_id"] == before["adopted_version_id"]
    assert {x["status"] for x in _dub(client)["lines"]} == {"done"}


def test_a_redub_sync_stopped_halfway_is_picked_up_on_start(client: TestClient) -> None:
    _dub_all(client)
    state = _state(client)
    hooks = state.jobs._finished
    saved = list(hooks)
    hooks.clear()  # the take ends, but nothing hears it (as if the backend stopped right then)
    target = next(x for x in _dub(client)["lines"] if x["text"] == "……周屿？")
    impact = _preview(client, "line_edit", target["line_id"], {"text": "……是你吗？"})
    out = _apply(client, impact["id"], "rerun")
    assert _wait(client, out["job_ids"][0])["state"] == "succeeded"

    hooks.extend(saved)
    _call(client, state.cascade.resume)  # what StudioState.run() does on start
    _drain(client)
    redone = next(x for x in _dub(client)["lines"] if x["line_id"] == target["line_id"])
    assert (redone["status"], redone["text"]) == ("done", "……是你吗？")
    assert _versions(client, target["product_id"]) == 2
    cascade = [j for j in _jobs(client) if "cascade" in j["params"]]
    assert [j["product_id"] for j in cascade] == [target["product_id"]]
