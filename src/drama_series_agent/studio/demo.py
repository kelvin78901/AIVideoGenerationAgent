"""The demo series 《雨停之前》 (prototype/README.md「示例数据」).

Mock mode seeds it at startup when the database has no series yet, so pages whose MSW
handlers have been removed still have a series to show. Then each block the demo series lacks
is added (only what is missing, so an existing database picks up new blocks on the next
start): the novel (``tests/fixtures/demo/雨停之前.txt``), its enrichment suggestions (小说补全
v1 local → v2 DeepSeek, adopted, the first suggestion accepted; ``enrich.json``) and its story
bible (设定提取 v1, read with that accepted addition; ``extract.json``), each assembled exactly
as a Mock run would. Ids and times match ``web/src/mocks/fixtures/demo/``.
``drama-studio demo [--reset]`` runs the same seeding on demand; ``--reset`` deletes the demo
series first.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from loguru import logger
from sqlmodel import select

from drama_series_agent.bible.service import BIBLE_SLOT, bible_slicer, materialize
from drama_series_agent.core.config import SpecConfig, get_config
from drama_series_agent.core.db import Database, migrate
from drama_series_agent.core.events import EventBus
from drama_series_agent.core.models_db import Product, Series, SuggestionDecision
from drama_series_agent.core.paths import REPO_ROOT, database_path
from drama_series_agent.core.storage import BlobStore
from drama_series_agent.novel.service import NOVEL_SLOT, FixedIds, NovelService, novel_slicer
from drama_series_agent.pipeline.components import enrich
from drama_series_agent.pipeline.components.extract import demo_payload
from drama_series_agent.pipeline.drafts import VersionDraft
from drama_series_agent.pipeline.invalidation import Invalidation
from drama_series_agent.pipeline.products import ProductService
from drama_series_agent.prompts.compiler import PromptCompiler
from drama_series_agent.spec.schema import default_row
from drama_series_agent.suggestions import service as suggestions

DEMO_SERIES_ID = "demo"
DEMO_NOVEL = REPO_ROOT / "tests" / "fixtures" / "demo" / "雨停之前.txt"
# Imported 09:22 +08:00, two minutes after the series was created.
NOVEL_IDS = FixedIds(
    product_id="demo-novel",
    version_id="demo-novel-v1",
    source_id="demo-src",
    at=datetime(2026, 10, 14, 1, 22, tzinfo=UTC),
)
ENRICH_PRODUCT = "demo-p-enrich"
# 小说补全 v1 on the local model 09:41 +08:00, v2 「不满意换一个」 on DeepSeek 10:02 (adopted).
ENRICH_VERSIONS = (
    ("demo-p-enrich-v1", "local/qwen3.6-27b", "local", "run", datetime(2026, 10, 14, 1, 41)),
    ("demo-p-enrich-v2", "deepseek/v4-pro", "api", "switch", datetime(2026, 10, 14, 2, 2)),
)  # fmt: skip
BIBLE_PRODUCT = "demo-p-extract"
BIBLE_VERSION = "demo-p-extract-v1"
BIBLE_MODEL = "local/qwen3.6-27b"
# 设定提取 v1 on the local model, 10:05 +08:00 (MSW fixtures/demo/products.ts).
BIBLE_AT = datetime(2026, 10, 14, 2, 5, tzinfo=UTC)


async def seed_demo(
    db: Database,
    *,
    novel: NovelService | None = None,
    products: ProductService | None = None,
    compiler: PromptCompiler | None = None,
    cfg: SpecConfig | None = None,
    force: bool = False,
) -> bool:
    """Create the demo series if there is no series at all (or ``force``), then fill in its
    missing blocks. Returns True if the series was created."""
    created = await _seed_series(db, cfg, force=force)
    async with db.session() as session:
        exists = await session.get(Series, DEMO_SERIES_ID) is not None
    if exists and novel is not None:
        if products is not None:
            # Before the import: its hook would create the products with random ids.
            await _series_product(products, ENRICH_PRODUCT, suggestions.SUGGESTIONS_SLOT, "enrich")
            await _series_product(products, BIBLE_PRODUCT, BIBLE_SLOT, "extract")
        await _seed_novel(novel)
        if products is not None and compiler is not None:
            await _seed_enrich(db, novel, products, compiler)
            await _seed_bible(db, novel, products, compiler)
    return created


async def delete_demo(db: Database) -> bool:
    """Delete the demo series; its spec, products, versions and novel go with it (cascade)."""
    async with db.session() as session:
        row = await session.get(Series, DEMO_SERIES_ID)
        if row is None:
            return False
        await session.delete(row)
        await session.commit()
    return True


async def build_demo(*, reset: bool) -> None:
    """``drama-studio demo [--reset]``: seed (or rebuild) the demo series in the data dir."""
    path = database_path()
    await asyncio.to_thread(migrate, path)
    db = Database(path)
    try:
        products = ProductService(db, EventBus(db), slicers())
        products.on_adopt(BIBLE_SLOT, materialize)
        products.on_adopt(suggestions.SUGGESTIONS_SLOT, suggestions.materialize)
        if reset:
            await delete_demo(db)
        novel = NovelService(db, BlobStore(), products)
        await seed_demo(db, novel=novel, products=products, compiler=PromptCompiler(), force=True)
    finally:
        await db.dispose()


async def _seed_series(db: Database, cfg: SpecConfig | None, *, force: bool) -> bool:
    async with db.session() as session:
        if await session.get(Series, DEMO_SERIES_ID) is not None:
            return False
        if not force and (await session.exec(select(Series.id).limit(1))).first() is not None:
            return False
        session.add(
            Series(
                id=DEMO_SERIES_ID,
                slug="rain-stops",
                title="雨停之前",
                ui_lang="zh-CN",
                created_at=datetime(2026, 10, 14, 1, 20, tzinfo=UTC),  # 09:20 +08:00
            )
        )
        # Flush the series first: output_spec has a foreign key to it.
        await session.flush()
        spec = default_row(DEMO_SERIES_ID, cfg or get_config().spec)
        # Locked when the first keyframe (1-01 v2) was adopted, 11:02 +08:00.
        spec.locked_at = datetime(2026, 10, 14, 3, 2, tzinfo=UTC)
        session.add(spec)
        await session.commit()
    return True


async def _seed_novel(novel: NovelService) -> None:
    if (await novel.get(DEMO_SERIES_ID)).source is not None:
        return
    if not DEMO_NOVEL.is_file():
        logger.warning("demo novel missing: {}", DEMO_NOVEL)
        return
    data = await asyncio.to_thread(DEMO_NOVEL.read_bytes)
    await novel.import_novel(
        DEMO_SERIES_ID, DEMO_NOVEL.name, data, rights_confirmed=True, fixed=NOVEL_IDS
    )


def slicers() -> Invalidation:
    """The slices the demo's versions depend on (as ``api/state.py`` registers them)."""
    invalidation = Invalidation()
    invalidation.slicer(NOVEL_SLOT, novel_slicer)
    invalidation.slicer(BIBLE_SLOT, bible_slicer)
    invalidation.slicer(suggestions.SUGGESTIONS_SLOT, suggestions.suggestions_slicer)
    return invalidation


async def _series_product(
    products: ProductService, product_id: str, slot: str, component_id: str
) -> str:
    p = await products.ensure(
        series_id=DEMO_SERIES_ID,
        owner_type="series",
        owner_id=DEMO_SERIES_ID,
        slot=slot,
        component_id=component_id,
        product_id=product_id,
    )
    return p.id


async def _seed_enrich(
    db: Database, novel: NovelService, products: ProductService, compiler: PromptCompiler
) -> None:
    product_id = await _series_product(
        products, ENRICH_PRODUCT, suggestions.SUGGESTIONS_SLOT, "enrich"
    )
    async with db.session() as session:
        product = await session.get(Product, product_id)
        if product is None or product.current_version_id is not None:
            return
        book = await novel.book(session, DEMO_SERIES_ID)
        if book is None or book.product_id is None:
            return
        dep = await slicers().dependency(session, book.product_id, "chapters")
    payload = enrich.demo_payload(book)
    fixture = enrich.demo_fixture()
    if payload is None or fixture is None:
        logger.warning("demo enrichment fixture missing")
        return
    intent = compiler.default_intent("enrich", "zh-CN")
    parent = None
    for n, (version_id, model, where, origin, at) in enumerate(ENRICH_VERSIONS, 1):
        draft = VersionDraft(
            payload=payload,
            intent=intent,
            compiled=compiler.compile("enrich", intent, model),
            model_key=model,
            where=where,
            seed=1000 + n,
            params={"mode": origin, "calls": 1},
            dependencies=[dep],
            id=version_id,
            created_at=at.replace(tzinfo=UTC),
        )
        v = await products.append(product_id, draft, origin=origin, parent_version_id=parent)
        parent = v.id
    assert parent is not None
    await products.adopt(parent)
    async with db.session() as session:
        for suggestion_id in fixture.get("accepted", []):
            session.add(
                SuggestionDecision(
                    suggestion_id=suggestion_id,
                    series_id=DEMO_SERIES_ID,
                    status="accepted",
                    updated_at=ENRICH_VERSIONS[-1][4].replace(tzinfo=UTC),
                )
            )
        await session.commit()


async def _seed_bible(
    db: Database, novel: NovelService, products: ProductService, compiler: PromptCompiler
) -> None:
    product_id = await _series_product(products, BIBLE_PRODUCT, BIBLE_SLOT, "extract")
    invalidation = slicers()
    async with db.session() as session:
        product = await session.get(Product, product_id)
        if product is None or product.current_version_id is not None:
            return
        book = await novel.book(session, DEMO_SERIES_ID)
        if book is None or book.product_id is None:
            return
        deps = [await invalidation.dependency(session, book.product_id, "chapters")]
        enriched = await session.get(Product, ENRICH_PRODUCT)
        if enriched is not None and enriched.adopted_version_id is not None:
            deps.append(
                await invalidation.dependency(session, ENRICH_PRODUCT, suggestions.ADOPTED_SLICE)
            )
    payload = demo_payload(book)
    if payload is None:
        logger.warning("demo bible fixture missing")
        return
    intent = compiler.default_intent("extract", "zh-CN")
    draft = VersionDraft(
        payload=payload,
        intent=intent,
        compiled=compiler.compile("extract", intent, BIBLE_MODEL),
        model_key=BIBLE_MODEL,
        where="local",
        seed=1001,
        params={"mode": "run", "calls": 2},
        dependencies=deps,
        id=BIBLE_VERSION,
        created_at=BIBLE_AT,
    )
    await products.append(product_id, draft, origin="run")
