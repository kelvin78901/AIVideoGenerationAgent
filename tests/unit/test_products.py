"""Products and versions (SPEC 4.2): append-only, current vs adopted, lock, materializers."""

from __future__ import annotations

import hashlib

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from drama_series_agent.core.db import Database
from drama_series_agent.core.events import EventBus
from drama_series_agent.core.models_db import Dependency, Event, Product, ProductVersion
from drama_series_agent.pipeline.drafts import file_entry
from drama_series_agent.pipeline.errors import PipelineError
from drama_series_agent.pipeline.hashing import content_hash, hash_json
from drama_series_agent.pipeline.products import DependencyDraft, ProductService, VersionDraft
from drama_series_agent.studio.demo import seed_demo


async def _service(db: Database) -> tuple[ProductService, Product]:
    await seed_demo(db)
    svc = ProductService(db, EventBus(db))
    p = await svc.ensure(
        series_id="demo", owner_type="series", owner_id="demo", slot="bible", component_id="extract"
    )
    return svc, p


def test_hash_is_canonical() -> None:
    assert hash_json({"b": 1, "a": "林晚"}) == hash_json({"a": "林晚", "b": 1})
    assert hash_json({"a": 1}).startswith("sha256:")
    files = [{"sha256": "x", "path": "/a"}]
    assert content_hash({}, files) == content_hash({}, [{"sha256": "x", "path": "/b"}])
    assert content_hash({}, files) != content_hash({}, [])


async def test_ensure_is_idempotent(studio_db: Database) -> None:
    svc, p = await _service(studio_db)
    again = await svc.ensure(
        series_id="demo", owner_type="series", owner_id="demo", slot="bible", component_id="extract"
    )
    assert again.id == p.id
    assert (await svc.get(p.id)).status == "empty"


async def test_first_version_is_adopted_later_runs_only_current(studio_db: Database) -> None:
    svc, p = await _service(studio_db)
    v1 = await svc.append(p.id, VersionDraft(payload={"n": 1}), origin="run")
    v2 = await svc.append(
        p.id, VersionDraft(payload={"n": 2}), origin="rerun", parent_version_id=v1.id
    )
    out = await svc.get(p.id)
    assert [v.n for v in out.versions] == [1, 2]
    assert out.adopted_version_id == v1.id  # hard rule 5: never replaced automatically
    assert out.current_version_id == v2.id
    assert out.status == "adopted"
    assert out.versions[1].parent_version_id == v1.id
    assert out.versions[0].content_hash == content_hash({"n": 1}, [])


async def test_edit_versions_are_adopted(studio_db: Database) -> None:
    svc, p = await _service(studio_db)
    await svc.append(p.id, VersionDraft(payload={"n": 1}), origin="run")
    v2 = await svc.append(p.id, VersionDraft(payload={"n": 2}), origin="edit", adopt=True)
    assert (await svc.get(p.id)).adopted_version_id == v2.id


async def test_set_current_and_adopt(studio_db: Database) -> None:
    svc, p = await _service(studio_db)
    v1 = await svc.append(p.id, VersionDraft(payload={"n": 1}), origin="run")
    v2 = await svc.append(p.id, VersionDraft(payload={"n": 2}), origin="rerun")
    out = await svc.set_current(v1.id)
    assert out.current_version_id == v1.id and out.adopted_version_id == v1.id
    out = await svc.adopt(v2.id)
    assert out.current_version_id == v2.id and out.adopted_version_id == v2.id


async def test_lock(studio_db: Database) -> None:
    svc, p = await _service(studio_db)
    try:
        await svc.lock(p.id)
    except PipelineError as e:
        assert (e.status, e.code) == (409, "nothing_adopted")
    else:
        raise AssertionError("locking with nothing adopted")
    v1 = await svc.append(p.id, VersionDraft(payload={"n": 1}), origin="run")
    out = await svc.lock(p.id)
    assert out.locked_hash == v1.content_hash and out.status == "locked"
    # A locked product still takes new versions, but none can be adopted.
    v2 = await svc.append(p.id, VersionDraft(payload={"n": 2}), origin="rerun")
    assert (await svc.get(p.id)).adopted_version_id == v1.id
    try:
        await svc.adopt(v2.id)
    except PipelineError as e:
        assert (e.status, e.code) == (409, "product_locked")
    else:
        raise AssertionError("adopted a locked product")
    out = await svc.unlock(p.id)
    assert out.locked_hash is None and out.status == "adopted"


async def test_dependencies_are_written(studio_db: Database) -> None:
    svc, p = await _service(studio_db)
    draft = VersionDraft(
        payload={},
        dependencies=[
            DependencyDraft("up-1", "sha256:a"),
            DependencyDraft("up-2", "sha256:b", "episode:e1"),
        ],
    )
    v = await svc.append(p.id, draft, origin="run")
    async with studio_db.session() as s:
        rows = (await s.exec(select(Dependency).where(Dependency.version_id == v.id))).all()
    assert {(r.upstream_product_id, r.slice, r.upstream_hash, r.product_id) for r in rows} == {
        ("up-1", "", "sha256:a", p.id),
        ("up-2", "episode:e1", "sha256:b", p.id),
    }


async def test_materializer_runs_on_adopt_only(studio_db: Database) -> None:
    svc, p = await _service(studio_db)
    seen: list[int] = []

    async def materialize(session: AsyncSession, product: Product, version: ProductVersion) -> None:
        assert product.adopted_version_id == version.id
        seen.append(version.n)

    svc.on_adopt("bible", materialize)
    await svc.append(p.id, VersionDraft(payload={}), origin="run")  # auto-adopted
    v2 = await svc.append(p.id, VersionDraft(payload={"x": 1}), origin="rerun")  # current only
    await svc.set_current(v2.id)
    assert seen == [1]
    await svc.adopt(v2.id)
    assert seen == [1, 2]


async def test_events(studio_db: Database) -> None:
    svc, p = await _service(studio_db)
    v = await svc.append(p.id, VersionDraft(payload={}), origin="run")
    async with studio_db.session() as s:
        events = [(e.type, e.data_json) for e in (await s.exec(select(Event))).all()]
    # The slot lets the front end refresh only what shows it (a line's audio: the dubbing).
    created = {"product_id": p.id, "slot": p.slot, "version_id": v.id, "n": 1, "origin": "run"}
    assert ("version.created", created) in events
    assert (
        "product.updated",
        {"product_id": p.id, "series_id": "demo", "slot": p.slot, "status": "adopted"},
    ) in events


# --------------------------------------------------------------------------- candidates (M3)


def _candidates(n: int, tag: str = "a") -> VersionDraft:
    files = [
        file_entry(
            "candidate", hashlib.sha256(f"{tag}{i}".encode()).hexdigest(), "image/png", idx=i
        )
        for i in range(n)
    ]
    return VersionDraft(payload={"candidates": [{"label": f"c{i}"} for i in range(n)]}, files=files)


async def _asset_product(db: Database) -> tuple[ProductService, Product]:
    await seed_demo(db)
    svc = ProductService(db, EventBus(db))
    p = await svc.ensure(
        series_id="demo", owner_type="asset", owner_id="a1", slot="ref_image", component_id="img"
    )
    return svc, p


async def test_candidates_are_not_adopted_and_need_not_become_current(studio_db: Database) -> None:
    svc, p = await _asset_product(studio_db)
    v1 = await svc.append(p.id, _candidates(4), origin="run", adopt=False)
    out = await svc.get(p.id)
    assert out.adopted_version_id is None and out.current_version_id == v1.id
    v2 = await svc.append(p.id, _candidates(4, "b"), origin="run", adopt=False, make_current=False)
    out = await svc.get(p.id)
    assert out.current_version_id == v1.id and [v.id for v in out.versions] == [v1.id, v2.id]


async def test_lock_pick_makes_one_locked_version_of_the_chosen_file(studio_db: Database) -> None:
    svc, p = await _asset_product(studio_db)
    v1 = await svc.append(p.id, _candidates(4), origin="run", adopt=False)
    await svc.set_pick(p.id, v1.id, 2)
    assert (await svc.get(p.id)).pick is not None
    recorded: list[str] = []

    async def record(session: AsyncSession, product: Product, version: ProductVersion) -> None:
        recorded.append(version.id)

    pick = await svc.lock_pick(p.id, v1.id, 2, record=record)
    out = await svc.get(p.id)
    assert pick.origin == "pick" and pick.parent_version_id == v1.id
    assert [f["role"] for f in pick.files_json] == ["ref"]
    assert pick.files_json[0]["sha256"] == v1.files_json[2]["sha256"]
    assert pick.payload_json == {"candidate": {"label": "c2"}}
    assert out.adopted_version_id == pick.id and out.locked_hash == pick.content_hash
    assert out.current_version_id == v1.id  # the grid keeps showing the candidates
    assert out.pick is not None and (out.pick.version_id, out.pick.idx) == (v1.id, 2)
    assert recorded == [pick.id]
    # The same picture gives the same hash, whichever version it came from.
    assert pick.content_hash == content_hash({"candidate": {"label": "c2"}}, pick.files_json)


async def test_lock_pick_errors_and_whole_version_lock(studio_db: Database) -> None:
    svc, p = await _asset_product(studio_db)
    v1 = await svc.append(p.id, _candidates(2), origin="run", adopt=False)
    for call, code in [
        (svc.lock_pick(p.id, v1.id, 7), "no_such_candidate"),
        (svc.set_pick(p.id, v1.id, 9), "no_such_candidate"),
    ]:
        try:
            await call
        except PipelineError as e:
            assert e.code == code
        else:
            raise AssertionError(code)
    upload = await svc.append(
        p.id, VersionDraft(payload={}, files=[file_entry("ref", "f" * 64, "image/png")]),
        origin="upload", adopt=False,
    )  # fmt: skip
    locked = await svc.lock_pick(p.id, upload.id, None)
    assert locked.id == upload.id
    out = await svc.get(p.id)
    assert out.adopted_version_id == upload.id and out.locked_hash == upload.content_hash
    try:
        await svc.lock_pick(p.id, v1.id, 0)
    except PipelineError as e:
        assert e.code == "product_locked"
    else:
        raise AssertionError("locked twice")
