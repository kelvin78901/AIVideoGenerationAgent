"""设定提取 and the story bible (SPEC 5 ``extract``, 9.1 ``/series/{id}/bible``, ``/bible/…``).

The demo series is seeded with the bible a Mock run makes; a new series importing the demo
novel and running extraction must end up with the same entries (ids aside).
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
from drama_series_agent.bible.service import bible_product, materialize
from drama_series_agent.core.models_db import BibleEntity, Dependency, ModelCall, ProductVersion
from drama_series_agent.core.paths import REPO_ROOT
from drama_series_agent.modelhub.adapters.mock import estimate_tokens
from drama_series_agent.pipeline.components.chunks import chunk_book, render_chunk

LOCAL = "http://127.0.0.1"
V1 = "/api/v1"
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "demo"
DEMO = (FIXTURES / "雨停之前.txt").read_bytes()
FIXTURE = json.loads((FIXTURES / "extract.json").read_text(encoding="utf-8"))
LOCAL_MODEL = "local/qwen3.6-27b"
# The paragraph (0-based) of the receipt that says 黑色发圈.
BLACK_HAIRTIE = next(e["paras"][0] - 1 for e in FIXTURE["entities"] if e["id"] == "p-black-hairtie")


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


def _extract_product(client: TestClient, series: str) -> dict[str, Any]:
    listed = client.get(f"{V1}/products", params={"owner": f"series:{series}"}).json()
    return next(p for p in listed if p["component_id"] == "extract")


def _run(client: TestClient, product_id: str, mode: str = "run") -> dict[str, Any]:
    resp = client.post(f"{V1}/products/{product_id}/run", json={"mode": mode})
    assert resp.status_code == 200, resp.text
    job = _wait(client, resp.json()["id"])
    assert job["state"] == "succeeded", job
    return job


def _bible(client: TestClient, series: str = "demo") -> dict[str, Any]:
    resp = client.get(f"{V1}/series/{series}/bible")
    assert resp.status_code == 200, resp.text
    data: dict[str, Any] = resp.json()
    return data


def _new_series_with_demo_novel(client: TestClient) -> str:
    series = str(client.post(f"{V1}/series", json={"title": "复刻"}).json()["id"])
    resp = client.post(
        f"{V1}/series/{series}/novel",
        files={"file": ("雨停之前.txt", DEMO)},
        data={"rights_confirmed": "true"},
    )
    assert resp.status_code == 200, resp.text
    return series


def _comparable(bible: dict[str, Any]) -> dict[str, Any]:
    """A bible without its ids and source: entries by (kind, name), suggestions by names."""
    names = {e["id"]: e["name"] for e in bible["entities"]}
    return {
        "entities": [
            {
                **{k: v for k, v in e.items() if k not in ("id", "series_id")},
                "source_spans": [(s["start"], s["end"]) for s in e["source_spans"]],
            }
            for e in bible["entities"]
        ],
        "merge_suggestions": [
            ([names[i] for i in s["ids"]], s["reason"]) for s in bible["merge_suggestions"]
        ],
    }


# --------------------------------------------------------------------------- the demo


def test_demo_bible_is_seeded(client: TestClient) -> None:
    bible = _bible(client)
    assert (bible["product_id"], bible["version_id"]) == ("demo-p-extract", "demo-p-extract-v1")
    assert bible["adopted"] is True and bible["source_id"] == "demo-src"
    assert {e["id"] for e in bible["entities"]} == {e["id"] for e in FIXTURE["entities"]}
    kinds = [e["kind"] for e in bible["entities"]]
    assert kinds == sorted(kinds, key=["character", "location", "prop", "event", "relation"].index)

    linwan = next(e for e in bible["entities"] if e["id"] == "c-linwan")
    assert linwan["data"]["summary"] == "26 岁 · 插画师" and linwan["frozen"] is False
    assert linwan["paras"] == [p - 1 for p in FIXTURE["entities"][0]["paras"]]
    first = client.get(f"{V1}/series/demo/novel").json()["paragraphs"][0]
    assert linwan["source_spans"][0] == {
        "source_id": "demo-src", "start": first["start"], "end": first["end"],
    }  # fmt: skip
    # 「可能是同一个」: the hair tie on the receipt and the one on her wrist.
    [suggestion] = bible["merge_suggestions"]
    assert suggestion["ids"] == ["p-black-hairtie", "p-hairtie"]
    assert suggestion["reason"] == FIXTURE["judge"][0]["reason"]

    product = client.get(f"{V1}/products/demo-p-extract").json()
    assert product["status"] == "adopted"
    v1 = product["versions"][0]
    assert (v1["model_key"], v1["where"], v1["origin"]) == (LOCAL_MODEL, "local", "run")
    assert v1["created_at"] == "2026-10-14T02:05:00Z" and v1["intent"].startswith("列出所有")
    assert product["prompt"]["compiled"].startswith("你负责从小说里抽取设定")
    assert product["estimate"]["model_key"] == LOCAL_MODEL  # 均衡: extraction runs locally

    rows = _rows(client, BibleEntity)
    assert sorted(r.id for r in rows if not r.retired) == sorted(e["id"] for e in bible["entities"])


def test_a_run_on_the_demo_novel_matches_the_seed(client: TestClient) -> None:
    series = _new_series_with_demo_novel(client)
    product = _extract_product(client, series)  # made by the import
    assert product["status"] == "empty" and product["estimate"]["cost_usd"] == 0
    job = _run(client, product["id"])

    bible = _bible(client, series)
    assert bible["adopted"] is True and bible["source_id"] != "demo-src"
    assert _comparable(bible) == _comparable(_bible(client))
    assert not {e["id"] for e in bible["entities"]} & {e["id"] for e in FIXTURE["entities"]}

    calls = [c for c in _rows(client, ModelCall) if c.product_id == product["id"]]
    assert [c.status for c in calls] == ["success", "success"]  # one chunk + the judging call
    assert all(c.component_id == "extract" and c.job_id == job["id"] for c in calls)
    version = client.get(f"{V1}/products/{product['id']}").json()["versions"][0]
    assert version["params"]["calls"] == 2
    novel = next(
        p for p in client.get(f"{V1}/products", params={"owner": f"series:{series}"}).json()
        if p["slot"] == "novel"
    )  # fmt: skip
    deps = [d for d in _rows(client, Dependency) if d.version_id == version["id"]]
    assert [(d.upstream_product_id, d.slice) for d in deps] == [(novel["id"], "chapters")]
    summaries = version["payload"]["chapters"]
    assert [c["summary"] for c in summaries] == [c["summary"] for c in FIXTURE["chapters"]]


def test_a_long_novel_goes_in_chunks(client: TestClient) -> None:
    """A tiny context window: every chunk fits in 60% of it and the result is the same."""
    state = _state(client)
    state.registry.spec(LOCAL_MODEL).caps.max_context = 400
    series = _new_series_with_demo_novel(client)

    async def book_chunks() -> list[Any]:
        async with state.db.session() as session:
            book = await state.novel.book(session, series)
        assert book is not None
        return [(book, chunk) for chunk in chunk_book(book, 240)]

    chunks = _call(client, book_chunks)
    assert len(chunks) > 3
    seen = [i for _, chunk in chunks for piece in chunk for i in piece.paras]
    book = chunks[0][0]
    assert seen == list(range(len(book.offsets)))  # every paragraph once, in order
    for book, chunk in chunks:
        if sum(len(piece.paras) for piece in chunk) > 1:
            assert estimate_tokens(render_chunk(book, chunk)) <= 240

    product = _extract_product(client, series)
    _run(client, product["id"])
    calls = [c for c in _rows(client, ModelCall) if c.product_id == product["id"]]
    assert len(calls) == len(chunks) + 1
    assert _comparable(_bible(client, series)) == _comparable(_bible(client))


# --------------------------------------------------------------------------- edits


def test_edits_make_adopted_edit_versions_and_reruns_keep_ids(client: TestClient) -> None:
    resp = client.patch(f"{V1}/bible/c-zhouyu", json={"name": "周屿（成年）", "frozen": True})
    assert resp.status_code == 200, resp.text
    zhouyu = resp.json()
    assert (zhouyu["name"], zhouyu["aliases"], zhouyu["frozen"]) == ("周屿（成年）", ["周屿"], True)
    product = client.get(f"{V1}/products/demo-p-extract").json()
    v1, v2 = product["versions"]
    assert (v2["origin"], v2["parent_version_id"]) == ("edit", v1["id"])
    assert product["adopted_version_id"] == v2["id"] and v2["model_key"] is None
    deps = {d.version_id: (d.upstream_product_id, d.slice) for d in _rows(client, Dependency)}
    assert deps[v2["id"]] == deps[v1["id"]]  # an edit is built from the same novel
    assert next(r for r in _rows(client, BibleEntity) if r.id == "c-zhouyu").frozen is True
    # Sending what is already there adds no version.
    client.patch(f"{V1}/bible/c-zhouyu", json={"frozen": True})
    assert len(client.get(f"{V1}/products/demo-p-extract").json()["versions"]) == 2

    _run(client, "demo-p-extract", "rerun")
    bible = _bible(client)
    assert bible["adopted"] is False  # the rerun is current, v2 stays adopted
    assert {e["id"] for e in bible["entities"]} == {e["id"] for e in FIXTURE["entities"]}
    kept = next(e for e in bible["entities"] if e["id"] == "c-zhouyu")
    assert kept == zhouyu  # frozen: exactly as the user left it


def test_merge_distinct_and_split(client: TestClient) -> None:
    resp = client.post(
        f"{V1}/bible/merge", json={"action": "merge", "ids": ["p-hairtie", "p-black-hairtie"]}
    )
    assert resp.status_code == 200, resp.text
    bible = resp.json()
    hairtie = next(e for e in bible["entities"] if e["id"] == "p-hairtie")
    assert hairtie["aliases"] == ["黑色发圈"] and BLACK_HAIRTIE in hairtie["paras"]
    assert "p-black-hairtie" not in {e["id"] for e in bible["entities"]}
    assert bible["merge_suggestions"] == []
    retired = {r.id for r in _rows(client, BibleEntity) if r.retired}
    assert retired == {"p-black-hairtie"}
    # A rerun finds both again; they land on the merged entry.
    _run(client, "demo-p-extract", "rerun")
    again = _bible(client)
    assert "p-black-hairtie" not in {e["id"] for e in again["entities"]}
    assert again["merge_suggestions"] == []

    split = client.post(
        f"{V1}/bible/merge", json={"action": "split", "ids": ["l-store"], "alias": "便利店"}
    )
    # The rerun on screen is not adopted: edits start from what is on screen.
    assert split.status_code == 200, split.text
    store = [e for e in split.json()["entities"] if e["name"] == "便利店"]
    assert len(store) == 1 and store[0]["kind"] == "location" and store[0]["paras"]


def test_not_the_same_stays_apart_after_a_rerun(client: TestClient) -> None:
    resp = client.post(
        f"{V1}/bible/merge", json={"action": "distinct", "ids": ["p-black-hairtie", "p-hairtie"]}
    )
    assert resp.status_code == 200 and resp.json()["merge_suggestions"] == []
    _run(client, "demo-p-extract", "rerun")
    assert _bible(client)["merge_suggestions"] == []
    calls = [c for c in _rows(client, ModelCall) if c.product_id == "demo-p-extract"]
    assert len(calls) == 2  # still judged (other pairs look alike), the pair is not asked


def test_edit_errors(client: TestClient) -> None:
    resp = client.patch(f"{V1}/bible/nope", json={"frozen": True})
    assert resp.status_code == 404 and _code(resp) == "entity_not_found"
    resp = client.patch(f"{V1}/bible/c-linwan", json={"name": " "})
    assert resp.status_code == 422 and _code(resp) == "name_required"
    assert client.patch(f"{V1}/bible/c-linwan", json={"colour": "red"}).status_code == 422
    resp = client.post(f"{V1}/bible/merge", json={"action": "merge", "ids": ["c-linwan", "l-flat"]})
    assert resp.status_code == 422 and _code(resp) == "merge_kinds_differ"
    resp = client.post(f"{V1}/bible/merge", json={"action": "merge", "ids": ["c-linwan", "x"]})
    assert resp.status_code == 404 and _code(resp) == "entity_not_found"
    resp = client.post(f"{V1}/bible/merge", json={"action": "split", "ids": ["l-store"]})
    assert resp.status_code == 422 and _code(resp) == "split_needs_alias"
    resp = client.post(
        f"{V1}/bible/merge", json={"action": "split", "ids": ["l-store"], "alias": "小卖部"}
    )
    assert resp.status_code == 422 and _code(resp) == "alias_not_found"
    assert _code(client.get(f"{V1}/series/nope/bible")) == "series_not_found"

    assert client.post(f"{V1}/products/demo-p-extract/lock").status_code == 200
    resp = client.patch(f"{V1}/bible/c-linwan", json={"frozen": True})
    assert resp.status_code == 409 and _code(resp) == "product_locked"
    client.post(f"{V1}/products/demo-p-extract/unlock")

    _state(client).registry.mock_settings.delay_s = 0.5
    job = client.post(f"{V1}/products/demo-p-extract/run", json={"mode": "rerun"}).json()
    resp = client.patch(f"{V1}/bible/c-linwan", json={"frozen": True})
    assert resp.status_code == 409 and _code(resp) == "product_busy"
    _wait(client, job["id"])


def test_a_series_without_a_novel(client: TestClient) -> None:
    series = str(client.post(f"{V1}/series", json={"title": "空的"}).json()["id"])
    bible = _bible(client, series)
    assert (bible["product_id"], bible["entities"], bible["adopted"]) == (None, [], True)


# --------------------------------------------------------------------------- staleness, mirror


def test_stale_after_the_novel_changes(client: TestClient) -> None:
    def status() -> str:
        return str(client.get(f"{V1}/products/demo-p-extract").json()["status"])

    assert status() == "adopted"
    changed = DEMO.replace("便利店里没有他。".encode(), "便利店里空无一人。".encode())
    client.post(
        f"{V1}/series/demo/novel",
        files={"file": ("a.txt", changed)},
        data={"rights_confirmed": "1"},
    )
    assert status() == "stale"
    client.patch(f"{V1}/bible/c-linwan", json={"frozen": True})
    assert status() == "stale"  # an edit does not make it fresh: it was built from the old text
    client.post(
        f"{V1}/series/demo/novel", files={"file": ("b.txt", DEMO)}, data={"rights_confirmed": "1"}
    )
    assert status() == "adopted"


def test_the_mirror_can_be_rebuilt_from_the_adopted_version(client: TestClient) -> None:
    state = _state(client)
    client.post(
        f"{V1}/bible/merge", json={"action": "merge", "ids": ["p-hairtie", "p-black-hairtie"]}
    )

    def snapshot() -> list[tuple[Any, ...]]:
        return sorted(
            (r.id, r.series_id, r.version_id, r.kind, r.name, r.aliases_json, r.data_json,
             r.paras_json, r.source_spans_json, r.frozen)
            for r in _rows(client, BibleEntity) if not r.retired
        )  # fmt: skip

    before = snapshot()

    async def rebuild() -> None:
        async with state.db.session() as session:
            for row in (await session.exec(select(BibleEntity))).all():
                await session.delete(row)
            product = await bible_product(session, "demo")
            assert product is not None and product.adopted_version_id is not None
            version = await session.get(ProductVersion, product.adopted_version_id)
            assert version is not None
            await materialize(session, product, version)
            await session.commit()

    _call(client, rebuild)
    assert snapshot() == before
