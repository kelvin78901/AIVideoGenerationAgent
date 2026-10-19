"""分集规划 and its episodes (SPEC 5 ``split``, 9.1 ``/series/{id}/episodes``, ``/episodes/…``,
``/beats/…``; M2 plan step 8).

The demo series is seeded with the plan a Mock run makes (three episodes, $15 each). Edits
make an adopted ``edit`` version; dragging a beat changes exactly the two episodes' slices
(what their scripts are written from).
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
from drama_series_agent.core.models_db import Beat, Episode, ModelCall, ProductVersion
from drama_series_agent.core.paths import REPO_ROOT
from drama_series_agent.episodes import service as episodes

LOCAL = "http://127.0.0.1"
V1 = "/api/v1"
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "demo"
DEMO = (FIXTURES / "雨停之前.txt").read_bytes()
FIXTURE = json.loads((FIXTURES / "split.json").read_text(encoding="utf-8"))
SPLIT_MODEL = "deepseek/v4.1-flash"  # 分集规划's route (balanced)


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


def _rows(client: TestClient, model: Any) -> list[Any]:
    async def read() -> list[Any]:
        async with _state(client).db.session() as s:
            return list((await s.exec(select(model))).all())

    return list(_call(client, read))


def _wait(client: TestClient, job_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        job: dict[str, Any] = client.get(f"{V1}/jobs/{job_id}").json()
        if job["state"] in ("succeeded", "failed", "canceled"):
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def _product(client: TestClient, series: str, component: str) -> dict[str, Any]:
    listed = client.get(f"{V1}/products", params={"owner": f"series:{series}"}).json()
    return next(p for p in listed if p["component_id"] == component)


def _status(client: TestClient, series: str, component: str) -> str:
    return str(_product(client, series, component)["status"])


def _run(client: TestClient, product_id: str, mode: str = "run") -> dict[str, Any]:
    resp = client.post(f"{V1}/products/{product_id}/run", json={"mode": mode})
    assert resp.status_code == 200, resp.text
    job = _wait(client, resp.json()["id"])
    assert job["state"] == "succeeded", job
    return job


def _episodes(client: TestClient, series: str = "demo") -> list[dict[str, Any]]:
    resp = client.get(f"{V1}/series/{series}/episodes")
    assert resp.status_code == 200, resp.text
    data: list[dict[str, Any]] = resp.json()
    return data


def _plan(data: list[dict[str, Any]]) -> list[tuple[Any, ...]]:
    """What a plan says, without ids."""
    return [
        (
            e["idx"], e["title"], e["hook"], e["cliffhanger"], e["target_seconds"],
            e["scene_count"], [(b["text"], b["emotion"], b["paras"]) for b in e["beats"]],
        )
        for e in data
    ]  # fmt: skip


def _new_series_with_demo_novel(client: TestClient) -> str:
    series = str(client.post(f"{V1}/series", json={"title": "复刻"}).json()["id"])
    resp = client.post(
        f"{V1}/series/{series}/novel",
        files={"file": ("雨停之前.txt", DEMO)},
        data={"rights_confirmed": "true"},
    )
    assert resp.status_code == 200, resp.text
    return series


def _hashes(client: TestClient, ids: list[str]) -> dict[str, str | None]:
    async def read() -> dict[str, str | None]:
        inv = _state(client).components.services.invalidation
        async with _state(client).db.session() as s:
            return {i: await inv.current_hash(s, "demo-p-split", f"episode:{i}") for i in ids}

    out: dict[str, str | None] = _call(client, read)
    return out


def _versions(client: TestClient) -> int:
    return len(_product(client, "demo", "split")["versions"])


# --------------------------------------------------------------------------- reads


def test_demo_plan_is_seeded(client: TestClient) -> None:
    data = _episodes(client)
    assert [(e["id"], e["idx"], e["title"]) for e in data] == [
        ("demo-e1", 1, "红伞"), ("demo-e2", 2, "十二点"), ("demo-e3", 3, "旧发圈"),
    ]  # fmt: skip
    e1 = data[0]
    assert (e1["hook"], e1["cliffhanger"]) == ("门口那把红伞，和三年没见的字迹。", "她拿起了那把伞")
    assert [e["budget_usd"] for e in data] == [15, 15, 15]
    assert [(e["scene_from"], e["scene_to"]) for e in data] == [(1, 2), (3, 4), (5, 7)]
    assert [e["target_seconds"] for e in data] == [34, 70, 80]
    assert [len(e["beats"]) for e in data] == [5, 9, 8]
    assert all(e["script_status"] == "none" and e["stage"] == "script_pending" for e in data)
    assert all(e["shot_count"] is None for e in data)
    first = e1["beats"][0]
    assert (first["id"], first["idx"], first["paras"]) == ("demo-bt1", 1, [0])
    novel = client.get(f"{V1}/series/demo/novel").json()
    p0 = novel["paragraphs"][0]
    assert first["source_spans"] == [
        {"source_id": "demo-src", "start": p0["start"], "end": p0["end"]}
    ]
    split = _product(client, "demo", "split")
    assert split["id"] == "demo-p-split" and split["status"] == "adopted"
    assert [v["model_key"] for v in split["versions"]] == ["deepseek/v4.1-flash"]


def test_a_run_on_the_demo_novel_matches_the_seed(client: TestClient) -> None:
    series = _new_series_with_demo_novel(client)
    assert _episodes(client, series) == []
    split = _product(client, series, "split")
    resp = client.post(f"{V1}/products/{split['id']}/run", json={"mode": "run"})
    assert (resp.status_code, _code(resp)) == (409, "upstream_not_ready")
    assert resp.json()["detail"]["params"] == {"slot": "bible"}
    _run(client, _product(client, series, "extract")["id"])
    job = _run(client, split["id"])
    data = _episodes(client, series)
    assert _plan(data) == _plan(_episodes(client))
    assert all(e["id"].startswith("ep-") and e["budget_usd"] is None for e in data)
    calls = [c for c in _rows(client, ModelCall) if c.component_id == "split"]
    assert len(calls) == 1 and calls[0].series_id == series and calls[0].episode_id is None
    version = _product(client, series, "split")["versions"][-1]
    assert version["id"] == job["result"]["version_id"]

    async def deps() -> set[str]:
        async with _state(client).db.session() as s:
            from drama_series_agent.core.models_db import Dependency

            rows = await s.exec(select(Dependency).where(Dependency.version_id == version["id"]))
            return {r.slice for r in rows.all()}

    # No accepted addition in this series yet: novel, bible summaries and names.
    assert _call(client, deps) == {"chapters", "names"}


def test_the_prompt_carries_the_spec_names_and_summaries(client: TestClient) -> None:
    client.put(f"{V1}/series/demo/spec", json={"episode_len": "mid"})
    job = _run(client, _product(client, "demo", "split")["id"])

    async def prompt() -> str:
        async with _state(client).db.session() as s:
            v = await s.get(ProductVersion, job["result"]["version_id"])
        assert v is not None
        sha = next(f["sha256"] for f in v.files_json if f["role"] == "prompt")
        return _state(client).store.read_bytes(sha).decode("utf-8")

    text = str(_call(client, prompt))
    assert "[成片规格]\n每集时长：90–180 秒" in text
    assert "[设定]\n人物：林晚" in text
    assert "[章节摘要]\n[第 1 章] 第一章 红伞（P1–P5）：" in text
    assert "【补写】" in text  # the accepted addition s1 goes with its paragraph
    assert "[P71] 红伞底下，雨还没有停。" in text


def test_a_long_novel_goes_in_chunks(client: TestClient) -> None:
    """A tiny context window: several chunks, the plan continued across them."""
    series = _new_series_with_demo_novel(client)
    _run(client, _product(client, series, "extract")["id"])
    _state(client).registry.spec(SPLIT_MODEL).caps.max_context = 400
    split = _product(client, series, "split")
    _run(client, split["id"])
    calls = [c for c in _rows(client, ModelCall) if c.product_id == split["id"]]
    assert len(calls) > 2

    def outline(data: list[dict[str, Any]]) -> list[tuple[Any, ...]]:
        return [(e["idx"], e["title"], [b["text"] for b in e["beats"]]) for e in data]

    # Episode 2 is cut by a chunk and continued in the next one (same ep number); a beat
    # across the cut only cites the paragraphs of its own chunk.
    data = _episodes(client, series)
    assert outline(data) == outline(_episodes(client))
    assert all(b["paras"] for e in data for b in e["beats"])


def test_any_other_novel_by_the_mock_rules(client: TestClient) -> None:
    series = str(client.post(f"{V1}/series", json={"title": "别的"}).json()["id"])
    chapters = [
        f"第{n}章 {title}\n\n"
        + "\n".join(f"{title}的第{i}段，老陈推开门走了进去。" for i in range(7))
        for n, title in (("一", "开端"), ("二", "转折"))
    ]
    resp = client.post(
        f"{V1}/series/{series}/novel",
        files={"file": ("别的.txt", "\n\n".join(chapters).encode())},
        data={"rights_confirmed": "true"},
    )
    assert resp.status_code == 200, resp.text
    _run(client, _product(client, series, "extract")["id"])
    _run(client, _product(client, series, "split")["id"])
    data = _episodes(client, series)
    assert [(e["idx"], e["title"]) for e in data] == [(1, "第一章 开端"), (2, "第二章 转折")]
    assert [[b["paras"] for b in e["beats"]] for e in data] == [
        [[0, 1, 2], [3, 4, 5], [6]],
        [[7, 8, 9], [10, 11, 12], [13]],
    ]
    assert all(e["beats"][-1]["emotion"] == 0.6 for e in data)


def test_a_rerun_keeps_ids_and_waits_to_be_adopted(client: TestClient) -> None:
    _run(client, _product(client, "demo", "split")["id"], "rerun")
    split = _product(client, "demo", "split")
    assert split["current_version_id"] != split["adopted_version_id"]
    # The list stays on the adopted plan until 采纳.
    assert [len(e["beats"]) for e in _episodes(client)] == [5, 9, 8]

    async def payload() -> dict[str, Any]:
        async with _state(client).db.session() as s:
            v = await s.get(ProductVersion, split["current_version_id"])
        assert v is not None
        return v.payload_json

    rerun = _call(client, payload)
    assert [e["id"] for e in rerun["episodes"]] == ["demo-e1", "demo-e2", "demo-e3"]
    assert rerun["episodes"][0]["beats"][0]["id"] == "demo-bt1"


# --------------------------------------------------------------------------- edits


def test_budget_is_a_setting(client: TestClient) -> None:
    resp = client.patch(f"{V1}/episodes/demo-e1", json={"budget_usd": 9.5})
    assert resp.status_code == 200, resp.text
    assert resp.json()["budget_usd"] == 9.5
    assert _versions(client) == 1  # no new version of the plan
    assert _call(client, _state(client).budget.left, "demo-e1") == pytest.approx(9.5)
    assert (
        client.patch(f"{V1}/episodes/demo-e1", json={"budget_usd": None}).json()["budget_usd"]
        is None
    )
    assert _call(client, _state(client).budget.left, "demo-e1") is None
    # A rerun and its adoption never touch it.
    client.patch(f"{V1}/episodes/demo-e2", json={"budget_usd": 3})
    job = _run(client, _product(client, "demo", "split")["id"], "rerun")
    client.post(f"{V1}/versions/{job['result']['version_id']}/adopt")
    assert [e["budget_usd"] for e in _episodes(client)] == [None, 3, 15]


def test_edit_an_episode(client: TestClient) -> None:
    resp = client.patch(
        f"{V1}/episodes/demo-e2", json={"title": "零点", "cliffhanger": " ", "target_seconds": 75}
    )
    assert resp.status_code == 200, resp.text
    e2 = resp.json()
    assert (e2["title"], e2["cliffhanger"], e2["target_seconds"]) == ("零点", None, 75)
    split = _product(client, "demo", "split")
    edit = split["versions"][-1]
    assert (edit["origin"], split["adopted_version_id"]) == ("edit", edit["id"])
    assert _episodes(client)[1]["title"] == "零点"
    # Only episode 2's slice changed.
    assert split["status"] == "adopted"
    resp = client.patch(f"{V1}/episodes/demo-e2", json={"title": "  "})
    assert (resp.status_code, _code(resp)) == (422, "title_required")
    resp = client.patch(f"{V1}/episodes/nope", json={"title": "x"})
    assert (resp.status_code, _code(resp)) == (404, "episode_not_found")
    assert client.patch(f"{V1}/episodes/demo-e2", json={"stage": "done"}).status_code == 422


def test_drag_a_beat_to_another_episode(client: TestClient) -> None:
    ids = ["demo-e1", "demo-e2", "demo-e3"]
    before = _hashes(client, ids)
    resp = client.patch(f"{V1}/beats/demo-bt5", json={"episode_id": "demo-e2", "position": 0})
    assert resp.status_code == 200, resp.text
    data = {e["id"]: e for e in resp.json()}
    assert [b["id"] for b in data["demo-e1"]["beats"]] == [f"demo-bt{i}" for i in range(1, 5)]
    e2 = [(b["id"], b["idx"], b["episode_id"]) for b in data["demo-e2"]["beats"]][:2]
    assert e2 == [("demo-bt5", 1, "demo-e2"), ("demo-bt6", 2, "demo-e2")]
    after = _hashes(client, ids)
    assert [i for i in ids if before[i] != after[i]] == ["demo-e1", "demo-e2"]
    beat = next(b for b in _rows(client, Beat) if b.id == "demo-bt5")
    assert (beat.episode_id, beat.idx) == ("demo-e2", 1)
    # Text and emotion; then the errors.
    resp = client.patch(f"{V1}/beats/demo-bt6", json={"text": "她冲下楼。", "emotion": -0.25})
    bt6 = next(
        b
        for b in next(e for e in resp.json() if e["id"] == "demo-e2")["beats"]
        if b["id"] == "demo-bt6"
    )
    assert (bt6["text"], bt6["emotion"]) == ("她冲下楼。", -0.25)
    assert _versions(client) == 3
    for body, status, code in (
        ({"text": " "}, 422, "beat_empty"),
        ({"episode_id": "nope"}, 404, "episode_not_found"),
    ):
        resp = client.patch(f"{V1}/beats/demo-bt6", json=body)
        assert (resp.status_code, _code(resp)) == (status, code)
    assert client.patch(f"{V1}/beats/demo-bt6", json={"emotion": 2}).status_code == 422
    assert _code(client.patch(f"{V1}/beats/nope", json={"text": "x"})) == "beat_not_found"


def test_locked_and_busy(client: TestClient) -> None:
    pid = _product(client, "demo", "split")["id"]
    assert client.post(f"{V1}/products/{pid}/lock").status_code == 200
    resp = client.patch(f"{V1}/beats/demo-bt1", json={"text": "x"})
    assert (resp.status_code, _code(resp)) == (409, "product_locked")
    # The budget is a setting: not locked with the plan.
    assert client.patch(f"{V1}/episodes/demo-e1", json={"budget_usd": 1}).status_code == 200
    client.post(f"{V1}/products/{pid}/unlock")
    settings = _state(client).registry.mock_settings
    settings.delay_s = 0.5
    job = client.post(f"{V1}/products/{pid}/run", json={"mode": "rerun"}).json()
    resp = client.patch(f"{V1}/episodes/demo-e1", json={"title": "x"})
    assert (resp.status_code, _code(resp)) == (409, "product_busy")
    settings.delay_s = 0
    _wait(client, job["id"])


def test_a_series_without_a_plan(client: TestClient) -> None:
    series = str(client.post(f"{V1}/series", json={"title": "空"}).json()["id"])
    assert _episodes(client, series) == []
    assert _code(client.get(f"{V1}/series/nope/episodes")) == "series_not_found"


# --------------------------------------------------------------------------- progress


def test_progress_of_the_novel_and_script_steps(client: TestClient) -> None:
    resp = client.get(f"{V1}/episodes/demo-e1/progress")
    assert resp.status_code == 200, resp.text
    steps = resp.json()["steps"]
    assert list(steps) == ["novel", "script", "assets", "storyboard", "generate", "post"]
    assert steps["novel"] == {"state": "in_progress", "done": None, "total": None, "stale": 0}
    assert steps["script"]["state"] == "not_started" and steps["script"]["stale"] == 0
    assert all(steps[s]["state"] == "not_started" for s in ("assets", "post"))
    # Accepting an addition: the bible and the plan both read it (待更新 1 each).
    client.post(f"{V1}/suggestions/s2/accept")
    steps = client.get(f"{V1}/episodes/demo-e1/progress").json()["steps"]
    assert (steps["novel"]["stale"], steps["script"]["stale"]) == (1, 1)
    assert _status(client, "demo", "split") == "stale"
    assert _code(client.get(f"{V1}/episodes/nope/progress")) == "episode_not_found"


def test_the_mirror_can_be_rebuilt_from_the_adopted_version(client: TestClient) -> None:
    client.patch(f"{V1}/beats/demo-bt5", json={"episode_id": "demo-e2"})

    def rows() -> list[tuple[Any, ...]]:
        eps = sorted(
            (r.id, r.version_id, r.idx, r.title, r.hook, r.cliffhanger, r.target_seconds,
             r.scene_count, r.budget_usd, r.retired)
            for r in _rows(client, Episode)
        )  # fmt: skip
        beats = sorted(
            (r.id, r.episode_id, r.version_id, r.idx, r.text, r.emotion, r.paras_json, r.retired)
            for r in _rows(client, Beat)
        )
        return [*eps, *beats]

    before = rows()

    async def rebuild() -> None:
        """Beats from nothing; episodes keep only their rows (the budget is a setting)."""
        async with _state(client).db.session() as s:
            for b in (await s.exec(select(Beat))).all():
                await s.delete(b)
            for e in (await s.exec(select(Episode))).all():
                e.title, e.hook, e.cliffhanger, e.idx = "", None, None, 0
                e.target_seconds = e.scene_count = None
                s.add(e)
            await s.commit()
            p = await episodes.split_product(s, "demo")
            assert p is not None and p.adopted_version_id is not None
            v = await s.get(ProductVersion, p.adopted_version_id)
            assert v is not None
            await episodes.materialize(s, p, v)
            await s.commit()

    _call(client, rebuild)
    assert rows() == before
