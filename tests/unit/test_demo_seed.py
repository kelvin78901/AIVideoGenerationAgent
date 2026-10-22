from __future__ import annotations

import asyncio

from sqlmodel import col, func, select

from drama_series_agent.bible.service import BIBLE_SLOT, materialize
from drama_series_agent.core.db import Database
from drama_series_agent.core.events import EventBus
from drama_series_agent.core.models_db import (
    Beat,
    BibleEntity,
    Chapter,
    Dependency,
    Episode,
    NovelSource,
    OutputSpecRow,
    Product,
    ProductVersion,
    Scene,
    ScriptLine,
    Series,
    Suggestion,
    SuggestionDecision,
)
from drama_series_agent.core.paths import database_path
from drama_series_agent.core.storage import BlobStore
from drama_series_agent.episodes import service as episodes
from drama_series_agent.novel.service import NovelService
from drama_series_agent.pipeline.products import ProductService
from drama_series_agent.prompts.compiler import PromptCompiler
from drama_series_agent.script import service as script_service
from drama_series_agent.studio.demo import DEMO_SERIES_ID, delete_demo, seed_demo
from drama_series_agent.studio_cli import main
from drama_series_agent.suggestions import service as suggestions


async def _count(db: Database, table: type) -> int:
    async with db.session() as session:
        return (await session.exec(select(func.count()).select_from(table))).one()


def _novel(db: Database) -> NovelService:
    return NovelService(db, BlobStore(), ProductService(db, EventBus(db)))


async def test_seed_demo_is_idempotent(studio_db: Database) -> None:
    assert await seed_demo(studio_db) is True
    assert await seed_demo(studio_db) is False
    assert (await _count(studio_db, Series), await _count(studio_db, OutputSpecRow)) == (1, 1)
    async with studio_db.session() as session:
        series = await session.get(Series, DEMO_SERIES_ID)
        spec = await session.get(OutputSpecRow, DEMO_SERIES_ID)
    assert series is not None and series.title == "雨停之前" and series.slug == "rain-stops"
    assert spec is not None
    assert (spec.platform, spec.aspect, spec.delivery, spec.fps) == ("cn", "9:16", "1080p", 24)
    assert spec.audio_json == {"sample_rate": 48000, "lufs": -14, "peak_dbtp": -1}
    assert spec.locked_at is not None and spec.locked_at.isoformat() == "2026-10-14T03:02:00+00:00"


async def test_seed_skips_when_any_series_exists(studio_db: Database) -> None:
    async with studio_db.session() as session:
        session.add(Series(id="mine", slug="mine", title="Mine"))
        await session.commit()
    assert await seed_demo(studio_db, novel=_novel(studio_db)) is False
    assert (await _count(studio_db, Series), await _count(studio_db, OutputSpecRow)) == (1, 0)
    assert await _count(studio_db, NovelSource) == 0
    # On demand (drama-studio demo) it is added next to the user's series.
    assert await seed_demo(studio_db, novel=_novel(studio_db), force=True) is True
    assert await _count(studio_db, Series) == 2


async def test_missing_blocks_are_filled_in(studio_db: Database) -> None:
    """A database seeded before the novel existed gets it on the next start, once."""
    assert await seed_demo(studio_db) is True
    assert await _count(studio_db, NovelSource) == 0
    novel = _novel(studio_db)
    assert await seed_demo(studio_db, novel=novel) is False
    await seed_demo(studio_db, novel=novel)  # already there: not imported twice
    shown = await novel.get(DEMO_SERIES_ID)
    assert shown.source is not None and shown.source.id == "demo-src"
    assert [c.id for c in shown.chapters] == ["demo-src-ch1", "demo-src-ch2", "demo-src-ch3"]
    async with studio_db.session() as session:
        product = await session.get(Product, "demo-novel")
        version = await session.get(ProductVersion, "demo-novel-v1")
    assert product is not None and product.adopted_version_id == "demo-novel-v1"
    assert version is not None and version.created_at.isoformat() == "2026-10-14T01:22:00+00:00"
    assert (await _count(studio_db, NovelSource), await _count(studio_db, Chapter)) == (1, 3)


async def test_delete_demo_takes_everything_with_it(studio_db: Database) -> None:
    await seed_demo(studio_db, novel=_novel(studio_db))
    assert await delete_demo(studio_db) is True
    assert await delete_demo(studio_db) is False
    for table in (Series, OutputSpecRow, Product, ProductVersion, NovelSource, Chapter):
        assert await _count(studio_db, table) == 0, table.__name__


async def test_demo_suggestions_bible_plan_and_script_are_seeded_once(studio_db: Database) -> None:
    products = ProductService(studio_db, EventBus(studio_db))
    products.on_adopt(BIBLE_SLOT, materialize)
    products.on_adopt(suggestions.SUGGESTIONS_SLOT, suggestions.materialize)
    products.on_adopt(episodes.EPISODES_SLOT, episodes.materialize)
    products.on_adopt(episodes.SCRIPT_SLOT, script_service.materialize)
    novel = NovelService(studio_db, BlobStore(), products)

    async def hook(series_id: str) -> None:  # what the app's hook does
        for slot, component in (
            (BIBLE_SLOT, "extract"),
            ("suggestions", "enrich"),
            ("episodes", "split"),
        ):
            await products.ensure(
                series_id=series_id, owner_type="series", owner_id=series_id, slot=slot,
                component_id=component,
            )  # fmt: skip

    novel.after_import = hook
    for _ in range(2):
        await seed_demo(studio_db, novel=novel, products=products, compiler=PromptCompiler())
    async with studio_db.session() as session:
        product = await session.get(Product, "demo-p-extract")  # not a random id from the hook
        version = await session.get(ProductVersion, "demo-p-extract-v1")
        enrich = await session.get(Product, "demo-p-enrich")
        deps = (
            await session.exec(
                select(Dependency).where(Dependency.version_id == "demo-p-extract-v1")
            )
        ).all()
        accepted = await session.get(SuggestionDecision, "s1")
        split = await session.get(Product, "demo-p-split")
        split_deps = (
            await session.exec(select(Dependency).where(Dependency.version_id == "demo-p-split-v1"))
        ).all()
        rows = (await session.exec(select(Episode).order_by(col(Episode.idx)))).all()
        scripts = (
            await session.exec(
                select(Product).where(Product.slot == "script").order_by(col(Product.id))
            )
        ).all()
        script_deps = (
            await session.exec(
                select(Dependency).where(Dependency.version_id == "demo-p-script-e1-v2")
            )
        ).all()
    assert product is not None and product.adopted_version_id == "demo-p-extract-v1"
    assert version is not None and version.created_at.isoformat() == "2026-10-14T02:05:00+00:00"
    assert version.payload_json["source_id"] == "demo-src"
    # 小说补全 v1 → v2 (adopted), read by the bible through its accepted addition.
    assert enrich is not None and enrich.adopted_version_id == "demo-p-enrich-v2"
    assert accepted is not None and accepted.status == "accepted"
    assert {(d.upstream_product_id, d.slice) for d in deps} == {
        ("demo-novel", "chapters"),
        ("demo-p-enrich", "adopted"),
    }
    # 分集规划 v1 (adopted): three episodes of $15, read from the bible and the addition.
    assert split is not None and split.adopted_version_id == "demo-p-split-v1"
    assert {(d.upstream_product_id, d.slice) for d in split_deps} == {
        ("demo-novel", "chapters"),
        ("demo-p-extract", "chapters"),
        ("demo-p-extract", "names"),
        ("demo-p-enrich", "adopted"),
    }
    assert [(r.id, r.idx, r.title, r.budget_usd) for r in rows] == [
        ("demo-e1", 1, "红伞", 15.0),
        ("demo-e2", 2, "十二点", 15.0),
        ("demo-e3", 3, "旧发圈", 15.0),
    ]
    # 剧本化: every episode has its product (fixed ids); episode 1's v1 local → v2 Kimi
    # (adopted) reads its slice of the plan, chapter 1, the addition on its paragraphs and the
    # bible entries it uses.
    assert [(p.id, p.owner_id, p.adopted_version_id) for p in scripts] == [
        ("demo-p-script-e1", "demo-e1", "demo-p-script-e1-v2"),
        ("demo-p-script-e2", "demo-e2", None),
        ("demo-p-script-e3", "demo-e3", None),
    ]
    assert {(d.upstream_product_id, d.slice.split(":")[0]) for d in script_deps} == {
        ("demo-p-split", "episode"),
        ("demo-novel", "chapter"),
        ("demo-p-enrich", "adopted"),
        ("demo-p-extract", "entities"),
    }
    assert {d.slice for d in script_deps} >= {"episode:demo-e1", "chapter:0", "adopted:0,1,2,3,4"}
    # novel, enrich ×2, bible, plan, script ×2, episode 1's asset list: once each
    assert await _count(studio_db, ProductVersion) == 8
    assert await _count(studio_db, Scene) == 2
    assert await _count(studio_db, ScriptLine) == 10
    assert await _count(studio_db, BibleEntity) == len(version.payload_json["entities"]) == 18
    assert await _count(studio_db, Suggestion) == 4
    assert await _count(studio_db, Beat) == 22


def test_demo_command_resets() -> None:
    assert main(["demo"]) == 0
    assert main(["demo", "--reset"]) == 0
    db = Database(database_path())

    async def check() -> None:
        assert await _count(db, Series) == 1
        assert await _count(db, NovelSource) == 1
        assert await _count(db, BibleEntity) == 18
        await db.dispose()

    asyncio.run(check())
