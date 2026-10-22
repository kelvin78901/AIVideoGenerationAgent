"""确认并同步 (M2 plan step 10b): after a confirmed change, what it made stale reruns and is
adopted, layer by layer down to the scripts; each rerun goes through the budget check, and a
stop between two steps is picked up again on start.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import select

from drama_series_agent.api.app import create_app
from drama_series_agent.api.state import StudioState
from drama_series_agent.core.models_db import Event, ModelCall

LOCAL = "http://127.0.0.1"
V1 = "/api/v1"
BIBLE, ENRICH, SPLIT = "demo-p-extract", "demo-p-enrich", "demo-p-split"
SCRIPT1, SCRIPT2 = "demo-p-script-e1", "demo-p-script-e2"
ASSETS1 = "demo-p-assets-e1"
# The suggestions first (the bible reads the accepted ones), the bible, then the suggestions
# again: the Mock bible of an edited novel has other names (only the demo text gets the demo
# answer), and the suggestions read the names. Then the plan, the script and the episode's
# asset list (M3: it reads the script; the assets' pictures and voices never rerun by
# themselves).
SYNCED = [ENRICH, BIBLE, ENRICH, SPLIT, SCRIPT1, ASSETS1]


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(), base_url=LOCAL, headers={"X-Drama-Studio": "1"}) as c:
        yield c


def _state(client: TestClient) -> StudioState:
    state: StudioState = client.app.state.studio  # type: ignore[attr-defined]
    return state


def _call(client: TestClient, fn: Any, *args: Any) -> Any:
    return client.portal.call(fn, *args)  # type: ignore[union-attr]


def _product(client: TestClient, product_id: str) -> dict[str, Any]:
    data: dict[str, Any] = client.get(f"{V1}/products/{product_id}").json()
    return data


def _jobs(client: TestClient) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = client.get(f"{V1}/jobs", params={"limit": 500}).json()
    return jobs


def _cascade_jobs(client: TestClient) -> list[dict[str, Any]]:
    jobs = [j for j in _jobs(client) if "cascade" in j["params"]]
    return sorted(jobs, key=lambda j: j["created_at"])


def _drain(client: TestClient, *, until: str = "idle") -> None:
    """Wait until the cascade has nothing queued or running (``until="waiting"``: until a job
    waits for a confirmation)."""
    deadline = time.monotonic() + 30
    quiet = 0
    while time.monotonic() < deadline:
        jobs = _jobs(client)
        if until == "waiting" and any(j["state"] == "waiting_confirm" for j in jobs):
            return
        busy = any(j["state"] in ("queued", "running") for j in jobs)
        busy = busy or _state(client).cascade._lock.locked()
        quiet = 0 if busy else quiet + 1
        if quiet >= 5 and until == "idle":
            return
        time.sleep(0.03)
    raise AssertionError(f"cascade did not settle ({until})")


def _gate(client: TestClient, gate: str, action: str, scope: str) -> None:
    resp = client.post(f"{V1}/gates/{gate}/{action}", json={"scope_id": scope})
    assert resp.status_code == 200, resp.text


def _progress(client: TestClient) -> dict[str, Any]:
    steps: dict[str, Any] = client.get(f"{V1}/episodes/demo-e1/progress").json()["steps"]
    return steps


def _edit_first_paragraph(client: TestClient) -> dict[str, Any]:
    novel = client.get(f"{V1}/series/demo/novel", params={"chapter": 0}).json()
    paras = [p["text"] for p in novel["paragraphs"]]
    patch = {
        "chapter": 0,
        "title": novel["chapters"][0]["title"],
        "paragraphs": [paras[0] + "楼道的灯又闪了一下。", *paras[1:]],
    }
    resp = client.post(
        f"{V1}/impact/preview", json={"kind": "novel_edit", "target_id": "demo", "patch": patch}
    )
    assert resp.status_code == 200, resp.text
    impact: dict[str, Any] = resp.json()
    return impact


def _model_calls(client: TestClient) -> int:
    async def count() -> int:
        async with _state(client).db.session() as s:
            return len(list((await s.exec(select(ModelCall.id))).all()))

    n: int = _call(client, count)
    return n


def _toasts(client: TestClient, code: str) -> list[dict[str, Any]]:
    async def read() -> list[dict[str, Any]]:
        async with _state(client).db.session() as s:
            rows = (await s.exec(select(Event).where(Event.type == "toast"))).all()
        return [r.data_json for r in rows if r.data_json.get("code") == code]

    found: list[dict[str, Any]] = _call(client, read)
    return found


def _adopted_origin(client: TestClient, product_id: str) -> str:
    p = _product(client, product_id)
    adopted = next(v for v in p["versions"] if v["id"] == p["adopted_version_id"])
    return str(adopted["origin"])


def test_sync_after_editing_a_confirmed_novel(client: TestClient) -> None:
    _gate(client, "novel", "confirm", "demo-e1")
    _gate(client, "script", "confirm", "demo-e1")
    calls = _model_calls(client)
    impact = _edit_first_paragraph(client)

    resp = client.post(f"{V1}/impact/apply", json={"impact_id": impact["id"], "action": "rerun"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["action"] == "rerun" and data["stale"] == {"novel": 2, "script": 2}
    # The suggestions first: the bible reads the accepted ones, the rest reads both.
    (first,) = data["job_ids"]
    assert client.get(f"{V1}/jobs/{first}").json()["product_id"] == ENRICH

    _drain(client)
    jobs = _cascade_jobs(client)
    assert [j["product_id"] for j in jobs] == SYNCED
    assert {j["state"] for j in jobs} == {"succeeded"}
    assert len({j["params"]["cascade"]["id"] for j in jobs}) == 1
    for pid in (BIBLE, ENRICH, SPLIT, SCRIPT1):
        p = _product(client, pid)
        assert p["adopted_version_id"] == p["current_version_id"], pid
        assert _adopted_origin(client, pid) == "rerun", pid
        assert p["status"] == "adopted", (pid, p["status"])  # fresh, and unlocked
    assert _model_calls(client) >= calls + 4
    # Both gates reopened: the new content is the model's, to confirm again.
    steps = _progress(client)
    assert steps["novel"]["state"] == "in_progress" and steps["novel"]["stale"] == 0
    assert steps["script"]["state"] == "in_progress" and steps["script"]["stale"] == 0
    # The history keeps the old versions.
    assert len(_product(client, SCRIPT1)["versions"]) == 3
    # Once, at the end: 「已同步：N 个产物更新」.
    assert _toasts(client, "cascade_done") == [
        {"level": "success", "code": "cascade_done", "params": {"count": 5, "failed": 0}}
    ]


def test_a_rerun_over_the_cap_waits_and_the_rest_follows_after_the_yes(
    client: TestClient,
) -> None:
    override = {"scope": "component", "scope_id": None, "component_id": "split"}
    resp = client.put(
        f"{V1}/config/override", json={**override, "data": {"per_call_cap_usd": 0.0001}}
    )
    assert resp.status_code == 200, resp.text
    impact = _edit_first_paragraph(client)
    resp = client.post(f"{V1}/impact/apply", json={"impact_id": impact["id"], "action": "rerun"})
    assert resp.status_code == 200, resp.text

    _drain(client, until="waiting")
    _drain(client)
    jobs = _cascade_jobs(client)
    waiting = [j for j in jobs if j["state"] == "waiting_confirm"]
    assert [j["product_id"] for j in waiting] == [SPLIT]
    assert SCRIPT1 not in {j["product_id"] for j in jobs}  # held up below the plan
    assert _product(client, SPLIT)["running"]["cascade_id"] == jobs[0]["params"]["cascade"]["id"]

    assert client.post(f"{V1}/jobs/{waiting[0]['id']}/confirm").status_code == 200
    _drain(client)
    jobs = _cascade_jobs(client)
    assert [j["product_id"] for j in jobs] == SYNCED
    assert {j["state"] for j in jobs} == {"succeeded"}
    assert _adopted_origin(client, SCRIPT1) == "rerun"


def test_moving_a_beat_syncs_both_scripts(client: TestClient) -> None:
    resp = client.post(f"{V1}/products/{SCRIPT2}/run", json={"mode": "run"})
    assert resp.status_code == 200, resp.text
    _drain(client)
    resp = client.post(
        f"{V1}/impact/preview",
        json={
            "kind": "beat_move",
            "target_id": "demo-bt5",
            "patch": {"episode_id": "demo-e2", "position": 0},
        },
    )
    impact = resp.json()
    resp = client.post(f"{V1}/impact/apply", json={"impact_id": impact["id"], "action": "rerun"})
    assert len(resp.json()["job_ids"]) == 2  # the two scripts, side by side
    _drain(client)
    for pid in (SCRIPT1, SCRIPT2):
        assert _product(client, pid)["status"] == "adopted"
        assert _adopted_origin(client, pid) == "rerun"


def test_nothing_downstream_syncs_nothing(client: TestClient) -> None:
    _gate(client, "script", "confirm", "demo-e1")
    resp = client.post(
        f"{V1}/impact/preview",
        json={"kind": "line_edit", "target_id": "demo-b5", "patch": {"text": "……是周屿吗？"}},
    )
    impact = resp.json()  # rewording dialogue: nothing downstream reads it
    resp = client.post(f"{V1}/impact/apply", json={"impact_id": impact["id"], "action": "rerun"})
    assert resp.status_code == 200 and resp.json()["job_ids"] == []
    # The user's own edit: the gate stays confirmed.
    assert _progress(client)["script"]["state"] == "confirmed"
    assert _adopted_origin(client, SCRIPT1) == "edit"


def test_a_stop_between_two_steps_is_picked_up_on_start(client: TestClient) -> None:
    state = _state(client)
    hooks = state.jobs._finished
    saved = list(hooks)
    hooks.clear()  # the job ends, but nothing hears it (as if the backend stopped right then)
    impact = _edit_first_paragraph(client)
    client.post(f"{V1}/impact/apply", json={"impact_id": impact["id"], "action": "rerun"})
    deadline = time.monotonic() + 15
    while _cascade_jobs(client)[0]["state"] != "succeeded":
        assert time.monotonic() < deadline
        time.sleep(0.02)
    assert [j["product_id"] for j in _cascade_jobs(client)] == [ENRICH]
    assert _adopted_origin(client, ENRICH) != "rerun"  # not adopted yet

    hooks.extend(saved)
    _call(client, state.cascade.resume)  # what StudioState.run() does on start
    _drain(client)
    assert [j["product_id"] for j in _cascade_jobs(client)] == SYNCED
    assert _adopted_origin(client, ENRICH) == "rerun"
    assert _adopted_origin(client, SCRIPT1) == "rerun"


def test_cascade_jobs_are_found_by_their_tag(client: TestClient) -> None:
    # json_extract on params_json is what both the hook and the resume use.
    impact = _edit_first_paragraph(client)
    client.post(f"{V1}/impact/apply", json={"impact_id": impact["id"], "action": "rerun"})
    _drain(client)
    cascade_id = _cascade_jobs(client)[0]["params"]["cascade"]["id"]
    found = _call(client, _state(client).cascade._jobs, cascade_id)
    assert [j.product_id for j in found] == SYNCED
