"""剧本化 and an episode's script (SPEC 5 ``script``, 9.1 ``/episodes/{id}/script``,
``/lines/…``, ``/scenes/…``; M2 plan step 9).

The demo series is seeded with episode 1's script as a Mock run makes it (2 scenes, 10 lines;
v1 local → v2 Kimi, adopted). Each episode's script depends only on what it read: its slice of
the plan, the chapters of its paragraphs, the additions on them and the bible entries it uses.
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
from drama_series_agent.core.models_db import (
    Dependency,
    ModelCall,
    Product,
    ProductVersion,
    Scene,
    ScriptLine,
)
from drama_series_agent.core.paths import REPO_ROOT
from drama_series_agent.script import service as script_service

LOCAL = "http://127.0.0.1"
V1 = "/api/v1"
DEMO = (REPO_ROOT / "tests" / "fixtures" / "demo" / "雨停之前.txt").read_bytes()
SCRIPT_MODEL = "deepseek/v4-pro"  # 剧本化's route (balanced)


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


def _product(client: TestClient, owner: str, component: str) -> dict[str, Any]:
    listed = client.get(f"{V1}/products", params={"owner": owner}).json()
    return next(p for p in listed if p["component_id"] == component)


def _script_product(client: TestClient, episode_id: str) -> dict[str, Any]:
    return _product(client, f"episode:{episode_id}", "script")


def _run(client: TestClient, product_id: str, mode: str = "run") -> dict[str, Any]:
    resp = client.post(f"{V1}/products/{product_id}/run", json={"mode": mode})
    assert resp.status_code == 200, resp.text
    job = _wait(client, resp.json()["id"])
    assert job["state"] == "succeeded", job
    return job


def _script(client: TestClient, episode_id: str = "demo-e1") -> dict[str, Any]:
    resp = client.get(f"{V1}/episodes/{episode_id}/script")
    assert resp.status_code == 200, resp.text
    data: dict[str, Any] = resp.json()
    return data


def _lines(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {x["id"]: x for x in data["lines"]}


def _outline(client: TestClient, series: str, data: dict[str, Any]) -> list[tuple[Any, ...]]:
    """What a script says, without ids (bible entries by name, an addition's span counted)."""
    bible = client.get(f"{V1}/series/{series}/bible").json()["entities"]
    name = {e["id"]: e["name"] for e in bible}
    out: list[tuple[Any, ...]] = []
    for s in data["scenes"]:
        place = name.get(s["location_id"])
        out.append((s["idx"], s["heading"], s["time_of_day"], place, s["paras"]))
        for x in data["lines"]:
            if x["scene_id"] != s["id"]:
                continue
            sug = sum(1 for sp in x["source_spans"] if sp["source_id"].startswith("sug:"))
            out.append(
                (x["idx"], x["type"], name.get(x["character_id"]), x["character_name"],
                 x["tone"], x["text"], x["mood"], x["duration_s"], x["paras"], sug,
                 x["ai_added"], x["cliffhanger"])
            )  # fmt: skip
    return out


def _version(client: TestClient, version_id: str) -> ProductVersion:
    async def read() -> ProductVersion:
        async with _state(client).db.session() as s:
            v = await s.get(ProductVersion, version_id)
        assert v is not None
        return v

    v: ProductVersion = _call(client, read)
    return v


def _deps(client: TestClient, version_id: str) -> set[str]:
    async def read() -> set[str]:
        async with _state(client).db.session() as s:
            rows = await s.exec(select(Dependency).where(Dependency.version_id == version_id))
            return {r.slice for r in rows.all()}

    out: set[str] = _call(client, read)
    return out


def _new_series_with_demo_novel(client: TestClient) -> str:
    series = str(client.post(f"{V1}/series", json={"title": "复刻"}).json()["id"])
    resp = client.post(
        f"{V1}/series/{series}/novel",
        files={"file": ("雨停之前.txt", DEMO)},
        data={"rights_confirmed": "true"},
    )
    assert resp.status_code == 200, resp.text
    return series


# --------------------------------------------------------------------------- reads


def test_demo_script_is_seeded(client: TestClient) -> None:
    data = _script(client)
    assert (data["episode_id"], data["product_id"]) == ("demo-e1", "demo-p-script-e1")
    assert (data["version_id"], data["adopted"], data["source_id"]) == (
        "demo-p-script-e1-v2", True, "demo-src",
    )  # fmt: skip
    scenes = data["scenes"]
    heads = [(s["id"], s["idx"], s["heading"], s["time_of_day"], s["location_id"]) for s in scenes]
    assert heads == [
        ("demo-b1", 1, "夜　内　老小区楼道 · 六楼林晚家门口", "night", "l-stairs"),
        ("demo-b7", 2, "夜　内　林晚出租屋", "night", "l-flat"),
    ]  # fmt: skip
    assert [s["paras"] for s in scenes] == [[0, 1], [3]]
    lines = _lines(data)
    assert list(lines) == [f"demo-b{i}" for i in (2, 3, 4, 5, 6, 8, 9, 10, 11, 12)]
    # Reading order with the headings counted (the first is 0).
    assert [x["idx"] for x in data["lines"]] == [1, 2, 3, 4, 5, 7, 8, 9, 10, 11]
    b2 = lines["demo-b2"]
    assert (b2["character_id"], b2["mood"], b2["duration_s"], b2["paras"]) == (
        "c-linwan", "疲惫", 4, [0],
    )  # fmt: skip
    # The accepted addition s1 (林晚's coat) is on paragraph 1: the line cites it.
    assert b2["source_spans"][1]["source_id"] == "sug:s1"
    b5 = lines["demo-b5"]
    assert (b5["type"], b5["tone"], b5["ai_added"]) == ("dialogue", "低声，愣住", True)
    assert lines["demo-b10"]["overlay_shot"] == "1-06" and lines["demo-b10"]["type"] == "vo"
    assert [i for i, x in lines.items() if x["cliffhanger"]] == ["demo-b12"]
    assert not any(x["edited"] for x in data["lines"])
    product = _script_product(client, "demo-e1")
    assert [(v["model_key"], v["origin"]) for v in product["versions"]] == [
        ("local/qwen3.6-27b", "run"), ("moonshot/kimi-k2.6", "switch"),
    ]  # fmt: skip
    assert product["status"] == "adopted"
    # Episodes 2 and 3: an empty product each; 场号 follow episode 1's two scenes.
    e2 = _script(client, "demo-e2")
    assert (e2["product_id"], e2["scenes"], e2["lines"]) == ("demo-p-script-e2", [], [])
    episodes = client.get(f"{V1}/series/demo/episodes").json()
    assert [(e["scene_from"], e["scene_to"]) for e in episodes] == [(1, 2), (3, 4), (5, 7)]
    assert _code(client.get(f"{V1}/episodes/nope/script")) == "episode_not_found"


def test_a_run_on_the_demo_novel_matches_the_seed(client: TestClient) -> None:
    series = _new_series_with_demo_novel(client)
    _run(client, _product(client, f"series:{series}", "enrich")["id"])
    sugs = client.get(f"{V1}/series/{series}/suggestions").json()["suggestions"]
    first = next(s for s in sugs if s["para_idx"] == 0 and s["kind"] == "appearance")
    assert client.post(f"{V1}/suggestions/{first['id']}/accept").status_code == 200
    _run(client, _product(client, f"series:{series}", "extract")["id"])
    _run(client, _product(client, f"series:{series}", "split")["id"])
    episodes = client.get(f"{V1}/series/{series}/episodes").json()
    e1 = episodes[0]["id"]
    # Every episode of the adopted plan got its 剧本化.
    for e in episodes:
        assert _script_product(client, e["id"])["status"] == "empty"
    job = _run(client, _script_product(client, e1)["id"])
    data = _script(client, e1)
    seeded = _outline(client, "demo", _script(client))
    assert _outline(client, series, data) == seeded
    assert seeded[0][3] == "老小区楼道（六楼）" and seeded[1][2] == "林晚"
    assert all(s["id"].startswith("sc-") for s in data["scenes"])
    assert all(x["id"].startswith("ln-") for x in data["lines"])
    calls = [c for c in _rows(client, ModelCall) if c.component_id == "script"]
    assert [(c.series_id, c.episode_id) for c in calls] == [(series, e1)]
    deps = _deps(client, job["result"]["version_id"])
    assert {d.split(":")[0] for d in deps} == {"episode", "chapter", "adopted", "entities"}
    assert f"episode:{e1}" in deps and "chapter:0" in deps and "adopted:0,1,2,3,4" in deps


def test_the_prompt_carries_the_episode_beats_bible_and_its_paragraphs(client: TestClient) -> None:
    job = _run(client, _script_product(client, "demo-e1")["id"], "rerun")
    v = _version(client, job["result"]["version_id"])
    sha = next(f["sha256"] for f in v.files_json if f["role"] == "prompt")
    text = _state(client).store.read_bytes(sha).decode("utf-8")
    assert "[本集]\n第 1 集《红伞》\n开头钩子：门口那把红伞，和三年没见的字迹。" in text
    assert "预计时长：34 秒；预计场数：2" in text
    assert "[节拍]\n1. 雨夜，林晚加完班回老小区，一层层爬上六楼。（P1）" in text
    assert "人物「林晚」" in text and "地点「林晚出租屋」" in text
    assert "[P1] 那天雨下得很大。" in text
    assert "【补写1】她的米色风衣湿了半边" in text
    assert "[P5] 最后，她还是拿起了那把伞。" in text
    assert "[P6]" not in text  # only the episode's own paragraphs


def test_any_other_episode_by_the_mock_rules(client: TestClient) -> None:
    _run(client, _script_product(client, "demo-e2")["id"])
    data = _script(client, "demo-e2")
    episodes = client.get(f"{V1}/series/demo/episodes").json()
    e2 = episodes[1]
    cited = {p for b in e2["beats"] for p in b["paras"]}
    assert len(data["scenes"]) == e2["scene_count"] == 2
    assert [s["idx"] for s in data["scenes"]] == [3, 4]  # after episode 1's two
    assert all(set(x["paras"]) <= cited for x in data["lines"])
    assert any(x["type"] == "dialogue" for x in data["lines"])
    assert [x["cliffhanger"] for x in data["lines"]].count(True) == 1
    assert data["lines"][-1]["cliffhanger"]
    calls = [c for c in _rows(client, ModelCall) if c.component_id == "script"]
    assert [c.episode_id for c in calls] == ["demo-e2"]  # spent from episode 2's budget
    assert e2["script_status"] == "draft"


def test_a_rerun_keeps_ids_and_waits_to_be_adopted(client: TestClient) -> None:
    before = _script(client)
    job = _run(client, _script_product(client, "demo-e1")["id"], "rerun")
    data = _script(client)
    # The page shows the new version (未采纳) with the same ids; the mirror stays adopted.
    assert (data["version_id"], data["adopted"]) == (job["result"]["version_id"], False)
    assert [x["id"] for x in data["lines"]] == [x["id"] for x in before["lines"]]
    assert {r.version_id for r in _rows(client, ScriptLine)} == {"demo-p-script-e1-v2"}
    client.post(f"{V1}/versions/{data['version_id']}/adopt")
    assert _script(client)["adopted"] is True


# --------------------------------------------------------------------------- edits


def test_edit_a_line_and_a_scene_heading(client: TestClient) -> None:
    resp = client.patch(f"{V1}/lines/demo-b5", json={"text": " ……是你？ "})
    assert resp.status_code == 200, resp.text
    b5 = _lines(resp.json())["demo-b5"]
    assert (b5["text"], b5["edited"]) == ("……是你？", True)
    product = _script_product(client, "demo-e1")
    edit = product["versions"][-1]
    assert (edit["origin"], product["adopted_version_id"]) == ("edit", edit["id"])
    assert edit["parent_version_id"] == "demo-p-script-e1-v2"
    # The edit keeps what v2 was built from, so it turns stale with it.
    assert _deps(client, edit["id"]) == _deps(client, "demo-p-script-e1-v2")
    row = next(r for r in _rows(client, ScriptLine) if r.id == "demo-b5")
    assert (row.text, row.version_id) == ("……是你？", edit["id"])
    # The 场号 a user types in front is not kept: it is counted.
    resp = client.patch(f"{V1}/scenes/demo-b7", json={"heading": "场 2　夜　内　出租屋门内"})
    scene = next(s for s in resp.json()["scenes"] if s["id"] == "demo-b7")
    assert (scene["heading"], scene["idx"], scene["edited"]) == ("夜　内　出租屋门内", 2, True)
    # The same text again: no new version.
    client.patch(f"{V1}/lines/demo-b5", json={"text": "……是你？"})
    assert len(_script_product(client, "demo-e1")["versions"]) == 4
    for path, body, status, code in (
        ("lines/demo-b5", {"text": " "}, 422, "line_empty"),
        ("lines/nope", {"text": "x"}, 404, "line_not_found"),
        ("lines/demo-b1", {"text": "x"}, 404, "line_not_found"),
        ("scenes/demo-b2", {"heading": "x"}, 404, "scene_not_found"),
        ("scenes/demo-b1", {"heading": "场 1"}, 422, "heading_empty"),
    ):
        resp = client.patch(f"{V1}/{path}", json=body)
        assert (resp.status_code, _code(resp)) == (status, code), path
    assert client.patch(f"{V1}/lines/demo-b5", json={"text": "x", "tone": "y"}).status_code == 422


def test_locked_and_busy(client: TestClient) -> None:
    pid = _script_product(client, "demo-e1")["id"]
    assert client.post(f"{V1}/products/{pid}/lock").status_code == 200
    resp = client.patch(f"{V1}/lines/demo-b2", json={"text": "x"})
    assert (resp.status_code, _code(resp)) == (409, "product_locked")
    # A proposal saves nothing: still allowed (keeping it goes through the impact preview).
    assert client.post(f"{V1}/lines/demo-b2/rewrite", json={}).status_code == 200
    client.post(f"{V1}/products/{pid}/unlock")
    settings = _state(client).registry.mock_settings
    settings.delay_s = 0.5
    job = client.post(f"{V1}/products/{pid}/run", json={"mode": "rerun"}).json()
    resp = client.patch(f"{V1}/scenes/demo-b1", json={"heading": "日　外　楼下"})
    assert (resp.status_code, _code(resp)) == (409, "product_busy")
    settings.delay_s = 0
    _wait(client, job["id"])


# --------------------------------------------------------------------------- rewrites


def test_rewrite_proposes_and_saves_nothing(client: TestClient) -> None:
    resp = client.post(f"{V1}/lines/demo-b5/rewrite", json={})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"text": "……是你啊。", "model_key": SCRIPT_MODEL}
    resp = client.post(f"{V1}/lines/demo-b5/rewrite", json={"model": "moonshot/kimi-k2.6"})
    assert resp.json()["model_key"] == "moonshot/kimi-k2.6"
    resp = client.post(f"{V1}/scenes/demo-b1/rewrite", json={"instruction": "短一点"})
    assert resp.json()["text"] == "夜　内　老小区六楼楼道"
    assert len(_script_product(client, "demo-e1")["versions"]) == 2
    calls = [c for c in _rows(client, ModelCall) if c.component_id == "script"]
    assert len(calls) == 3
    assert {(c.product_id, c.episode_id) for c in calls} == {("demo-p-script-e1", "demo-e1")}
    for path, body, status, code in (
        ("lines/nope/rewrite", {}, 404, "line_not_found"),
        ("lines/demo-b1/rewrite", {}, 404, "line_not_found"),
        ("scenes/demo-b2/rewrite", {}, 404, "scene_not_found"),
        ("lines/demo-b2/rewrite", {"model": "nope/x"}, 422, "unknown_model"),
    ):
        resp = client.post(f"{V1}/{path}", json=body)
        assert (resp.status_code, _code(resp)) == (status, code), path


def test_rewrite_over_the_cap_or_the_episode_budget_asks_first(client: TestClient) -> None:
    body = {"scope": "component", "scope_id": None, "component_id": "script"}
    data = {"mode": "api", "per_call_cap_usd": 0.0000001}
    assert client.put(f"{V1}/config/override", json={**body, "data": data}).status_code == 200
    resp = client.post(f"{V1}/lines/demo-b2/rewrite", json={})
    assert (resp.status_code, _code(resp)) == (409, "over_budget")
    params = resp.json()["detail"]["params"]
    assert params["reason"] == "per_call" and params["estimate_usd"] > params["limit_usd"]
    assert not [c for c in _rows(client, ModelCall) if c.component_id == "script"]
    resp = client.post(f"{V1}/lines/demo-b2/rewrite", json={"confirm_budget": True})
    assert resp.status_code == 200, resp.text
    # What is left of the episode counts too.
    data = {"mode": "api", "per_call_cap_usd": 100}
    client.put(f"{V1}/config/override", json={**body, "data": data})
    client.patch(f"{V1}/episodes/demo-e1", json={"budget_usd": 0})
    resp = client.post(f"{V1}/scenes/demo-b1/rewrite", json={})
    assert (resp.status_code, _code(resp)) == (409, "over_budget")
    assert resp.json()["detail"]["params"]["reason"] == "episode"


# --------------------------------------------------------------------------- staleness


def test_a_dragged_beat_makes_both_scripts_stale(client: TestClient) -> None:
    _run(client, _script_product(client, "demo-e2")["id"])
    _run(client, _script_product(client, "demo-e3")["id"])
    assert client.patch(f"{V1}/beats/demo-bt5", json={"episode_id": "demo-e2"}).status_code == 200
    statuses = [_script_product(client, f"demo-e{n}")["status"] for n in (1, 2, 3)]
    assert statuses == ["stale", "stale", "adopted"]
    steps = client.get(f"{V1}/episodes/demo-e3/progress").json()["steps"]
    assert steps["script"]["stale"] == 0


def test_a_bible_entry_only_reaches_the_scripts_that_use_it(client: TestClient) -> None:
    _run(client, _script_product(client, "demo-e3")["id"])
    # 公交站台 is in episode 3 only.
    resp = client.patch(f"{V1}/bible/l-busstop", json={"data": {"summary": "雨里的旧站台"}})
    assert resp.status_code == 200, resp.text
    assert _script_product(client, "demo-e1")["status"] == "adopted"
    assert _script_product(client, "demo-e3")["status"] == "stale"


def test_the_mirror_can_be_rebuilt_from_the_adopted_version(client: TestClient) -> None:
    client.patch(f"{V1}/lines/demo-b5", json={"text": "……是你？"})

    def rows() -> list[tuple[Any, ...]]:
        scenes = sorted(
            (r.id, r.episode_id, r.version_id, r.idx, r.heading, r.location_id, r.time_of_day,
             r.paras_json, r.retired)
            for r in _rows(client, Scene)
        )  # fmt: skip
        lines = sorted(
            (r.id, r.scene_id, r.version_id, r.idx, r.type, r.character_id, r.text, r.tone,
             r.mood, r.duration_s, r.overlay_shot, r.paras_json, r.source_spans_json,
             r.ai_added, r.cliffhanger, r.retired)
            for r in _rows(client, ScriptLine)
        )  # fmt: skip
        return [*scenes, *lines]

    before = rows()

    async def rebuild() -> None:
        async with _state(client).db.session() as s:
            for model in (Scene, ScriptLine):
                for r in (await s.exec(select(model))).all():
                    await s.delete(r)
            p = await s.get(Product, "demo-p-script-e1")
            assert p is not None and p.adopted_version_id
            v = await s.get(ProductVersion, p.adopted_version_id)
            assert v is not None
            await script_service.materialize(s, p, v)
            await s.commit()

    _call(client, rebuild)
    assert rows() == before
