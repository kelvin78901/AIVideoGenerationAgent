"""Products and versions (SPEC 4.2): append-only, current vs adopted, lock, materializers."""

from __future__ import annotations

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from drama_series_agent.core.db import Database
from drama_series_agent.core.events import EventBus
from drama_series_agent.core.models_db import Dependency, Event, Product, ProductVersion
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
    created = {"product_id": p.id, "version_id": v.id, "n": 1, "origin": "run"}
    assert ("version.created", created) in events
    assert (
        "product.updated",
        {"product_id": p.id, "series_id": "demo", "status": "adopted"},
    ) in events
