"""素材分析 and assets (SPEC 5 ``assets``, 9.1 ``/series/{id}/assets``, ``/assets/{id}``,
``/episodes/{id}/assets/…``; M3 step 2).

The demo series is seeded with episode 1's asset list as a Mock run makes it: the prototype's
13 assets with their ids. The list only adds; what the user sets lives on each asset's product.
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
from drama_series_agent.core.models_db import Asset, AssetUse, ModelCall, Product

LOCAL = "http://127.0.0.1"
V1 = "/api/v1"
DEMO_IDS = [
    "linwan", "zhouyu", "hall", "room", "store", "umbrella", "note", "band", "phone",
    "txt1", "txt2", "vlinwan", "vzhouyu",
]  # fmt: skip


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(), base_url=LOCAL, headers={"X-Drama-Studio": "1"}) as c:
        yield c


def _state(client: TestClient) -> StudioState:
    state: StudioState = client.app.state.studio  # type: ignore[attr-defined]
    return state


def _rows(client: TestClient, model: Any) -> list[Any]:
    async def read() -> list[Any]:
        async with _state(client).db.session() as s:
            return list((await s.exec(select(model))).all())

    return list(client.portal.call(read))  # type: ignore[union-attr]


def _code(resp: Any) -> str:
    return str(resp.json()["detail"]["code"])


def _wait(client: TestClient, job_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        job: dict[str, Any] = client.get(f"{V1}/jobs/{job_id}").json()
        if job["state"] in ("succeeded", "failed", "canceled"):
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def _assets(client: TestClient, episode: str | None = "demo-e1") -> dict[str, dict[str, Any]]:
    params = {"episode": episode} if episode else {}
    resp = client.get(f"{V1}/series/demo/assets", params=params)
    assert resp.status_code == 200, resp.text
    return {a["id"]: a for a in resp.json()}


def _list_product(client: TestClient, episode: str) -> dict[str, Any]:
    listed = client.get(f"{V1}/products", params={"owner": f"episode:{episode}"}).json()
    return next(p for p in listed if p["component_id"] == "assets")


def test_the_demo_has_the_prototypes_thirteen_assets(client: TestClient) -> None:
    assets = _assets(client)
    assert list(assets) == DEMO_IDS  # characters, scenes, props, text, voices
    linwan = assets["linwan"]
    assert (linwan["kind"], linwan["name"]) == ("character", "林晚")
    assert linwan["status"] == "not_generated"
    assert linwan["intent"].startswith("26 岁女性，插画师。")
    assert linwan["product_id"] == "demo-p-asset-linwan"
    assert linwan["source"] == {"code": "script_line", "params": {"scene": 1, "line": 1}}
    assert [s["number"] for s in linwan["scenes"]] == [1, 2]
    assert assets["hall"]["source"] == {"code": "scene_heading", "params": {"scene": 1}}
    assert assets["note"]["name"] == "黄色便利贴" and assets["band"]["name"] == "旧黑发圈"
    assert assets["txt1"]["text"] == {
        "exact": "楼下便利店，等你到十二点。", "method": "model", "style": "handwritten"
    }  # fmt: skip
    assert assets["txt2"]["text"]["method"] == "composite"
    voice = assets["vlinwan"]["voice"]
    assert voice["method"] == "design"
    assert [line["text"] for line in voice["lines"]] == ["……周屿？", "三年了。他凭什么。"]
    assert assets["vlinwan"]["source"] == {"code": "dialogue_count", "params": {"count": 2}}
    # Coming up in episode 2: named now, used nowhere yet.
    assert assets["store"]["scenes"] == [] and assets["store"]["note"] == "第 2 集出场"
    assert assets["store"]["source"]["code"] == "note"
    kinds = {a["product_id"]: a["kind"] for a in assets.values()}
    products = {p.id: p for p in _rows(client, Product) if p.owner_type == "asset"}
    assert {products[pid].slot for pid, k in kinds.items() if k == "text"} == {"text_image"}
    assert {products[pid].component_id for pid, k in kinds.items() if k == "voice"} == {"voice"}


def test_the_matrix_is_scenes_by_assets(client: TestClient) -> None:
    resp = client.get(f"{V1}/episodes/demo-e1/assets/matrix")
    assert resp.status_code == 200, resp.text
    m = resp.json()
    assert [s["number"] for s in m["scenes"]] == [1, 2]
    hall, room = (s["id"] for s in m["scenes"])
    cells = {(c["asset_id"], c["scene_id"]): c["line_ids"] for c in m["cells"]}
    assert cells[("hall", hall)] == [] and ("hall", room) not in cells  # a scene: all of it
    assert set(cells) >= {("linwan", hall), ("linwan", room), ("umbrella", hall)}
    assert cells[("txt1", hall)] == ["demo-b4"] and cells[("txt2", room)] == ["demo-b9"]
    assert cells[("vlinwan", hall)] == ["demo-b5"] and cells[("vlinwan", room)] == ["demo-b10"]
    assert "store" not in {a["id"] for a in m["assets"]}
    assert client.get(f"{V1}/episodes/nope/assets/matrix").status_code == 404


def test_a_mock_run_on_the_demo_matches_the_seed(client: TestClient) -> None:
    product = _list_product(client, "demo-e1")
    seeded = next(v for v in product["versions"] if v["id"] == product["adopted_version_id"])
    resp = client.post(f"{V1}/episodes/demo-e1/assets/analyze")
    assert resp.status_code == 200, resp.text
    job = _wait(client, resp.json()["id"])
    assert job["state"] == "succeeded" and job["queue"] == "api:deepseek"
    product = _list_product(client, "demo-e1")
    latest = product["versions"][-1]
    assert product["adopted_version_id"] == latest["id"]  # 重新分析 is adopted every time
    assert latest["payload"] == seeded["payload"]  # same ids, same list
    calls = [c for c in _rows(client, ModelCall) if c.product_id == product["id"]]
    assert len(calls) == 1 and calls[0].component_id == "assets"
    assert len(_rows(client, Asset)) == 13


def test_edits_live_on_the_assets_product(client: TestClient) -> None:
    resp = client.patch(f"{V1}/assets/linwan", json={"intent": "26 岁，短发。"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["intent"] == "26 岁，短发。"
    product = client.get(f"{V1}/products/demo-p-asset-linwan").json()
    assert product["prompt"]["intent"] == "26 岁，短发。"
    resp = client.patch(f"{V1}/assets/txt1", json={"text": {"method": "composite"}})
    assert resp.json()["text"] == {
        "exact": "楼下便利店，等你到十二点。", "method": "composite", "style": "handwritten"
    }  # fmt: skip
    assert client.get(f"{V1}/products/demo-p-asset-txt1").json()["settings"]["text"]["method"] == (
        "composite"
    )
    resp = client.patch(f"{V1}/assets/vlinwan", json={"voice": {"method": "local"}})
    assert resp.json()["voice"]["method"] == "local"
    # A re-analysis keeps them: they are not in the list's payload.
    _wait(client, client.post(f"{V1}/episodes/demo-e1/assets/analyze").json()["id"])
    assets = _assets(client)
    assert assets["linwan"]["intent"] == "26 岁，短发。"
    assert assets["txt1"]["text"]["method"] == "composite"
    assert assets["vlinwan"]["voice"]["method"] == "local"


def test_patch_errors(client: TestClient) -> None:
    assert _code(client.patch(f"{V1}/assets/linwan", json={"pick": 1})) == "nothing_to_pick"
    assert client.patch(f"{V1}/assets/nope", json={"intent": "x"}).status_code == 404
    bad = client.patch(f"{V1}/assets/txt1", json={"text": {"exact": "x", "font": "宋体"}})
    assert bad.status_code == 422


def test_rewording_dialogue_leaves_the_list_fresh(client: TestClient) -> None:
    resp = client.patch(f"{V1}/lines/demo-b5", json={"text": "……是周屿吗？"})
    assert resp.status_code == 200, resp.text
    assert _list_product(client, "demo-e1")["status"] == "adopted"
    resp = client.patch(f"{V1}/lines/demo-b3", json={"text": "门口靠着一把红伞。"})
    assert resp.status_code == 200, resp.text
    assert _list_product(client, "demo-e1")["status"] == "stale"


def test_a_later_episode_only_adds(client: TestClient) -> None:
    script = next(
        p
        for p in client.get(f"{V1}/products", params={"owner": "episode:demo-e2"}).json()
        if p["component_id"] == "script"
    )
    job = client.post(f"{V1}/products/{script['id']}/run", json={"mode": "run"}).json()
    assert _wait(client, job["id"])["state"] == "succeeded"
    job = client.post(f"{V1}/episodes/demo-e2/assets/analyze").json()
    assert _wait(client, job["id"])["state"] == "succeeded"
    every = _assets(client, None)
    assert set(DEMO_IDS) <= set(every)  # episode 1's assets are all still there
    assert not any(a.retired for a in _rows(client, Asset))
    uses = _rows(client, AssetUse)
    assert {u.episode_id for u in uses} == {"demo-e1", "demo-e2"}
    assert {u.asset_id for u in uses if u.episode_id == "demo-e1"} >= {"linwan", "hall"}
    # 周屿 and his voice, named in episode 1, keep their ids where they appear.
    assert {"zhouyu", "vzhouyu"} <= {u.asset_id for u in uses if u.episode_id == "demo-e2"}


def test_analyze_before_the_script(client: TestClient) -> None:
    assert _code(client.post(f"{V1}/episodes/demo-e3/assets/analyze")) == "upstream_not_ready"
    assert client.post(f"{V1}/episodes/nope/assets/analyze").status_code == 404
