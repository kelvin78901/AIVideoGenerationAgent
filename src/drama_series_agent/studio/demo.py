"""The demo series 《雨停之前》 (prototype/README.md「示例数据」).

Mock mode seeds it at startup when the database has no series yet, so pages whose MSW
handlers have been removed still have a series to show. Then each block the demo series lacks
is added (only what is missing, so an existing database picks up new blocks on the next
start): the novel (``tests/fixtures/demo/雨停之前.txt``), its enrichment suggestions (小说补全
v1 local → v2 DeepSeek, adopted, the first suggestion accepted; ``enrich.json``) and its story
bible (设定提取 v1, read with that accepted addition; ``extract.json``) and its episode plan
(分集规划 v1 on DeepSeek, three episodes with a $15 budget each; ``split.json``) and episode 1's
script (剧本化 v1 local → v2 「不满意换一个」 on Kimi, adopted; ``script.json``) and its asset
list (素材分析 v1 on DeepSeek, the prototype's 13 assets with their ids; ``assets.json``), each
assembled exactly as a Mock run would. Ids and times match ``web/src/mocks/fixtures/demo/``.
Then the novel gate and episode 1's script gate are confirmed, once: a gate the user reopened
stays open. ``drama-studio demo [--reset]`` runs the same seeding on demand; ``--reset``
deletes the demo series first.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from loguru import logger
from sqlmodel import select

from drama_series_agent.assets import ops as asset_ops
from drama_series_agent.bible.service import BIBLE_SLOT, bible_slicer, materialize
from drama_series_agent.core.config import SpecConfig, get_config
from drama_series_agent.core.db import Database, migrate
from drama_series_agent.core.events import EventBus
from drama_series_agent.core.models_db import Episode, Product, Series, SuggestionDecision
from drama_series_agent.core.paths import REPO_ROOT, database_path
from drama_series_agent.core.storage import BlobStore
from drama_series_agent.episodes import service as episodes
from drama_series_agent.episodes.service import latest_gate
from drama_series_agent.novel.service import NOVEL_SLOT, FixedIds, NovelService, novel_slicer
from drama_series_agent.pipeline.components import assets, enrich, script, split
from drama_series_agent.pipeline.components.extract import demo_payload
from drama_series_agent.pipeline.drafts import VersionDraft
from drama_series_agent.pipeline.errors import PipelineError
from drama_series_agent.pipeline.gates import GateService
from drama_series_agent.pipeline.invalidation import Invalidation
from drama_series_agent.pipeline.products import ProductService
from drama_series_agent.prompts.compiler import PromptCompiler
from drama_series_agent.script import service as script_service
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
SPLIT_PRODUCT = "demo-p-split"
SPLIT_VERSION = "demo-p-split-v1"
SPLIT_MODEL = "deepseek/v4.1-flash"
# 分集规划 v1 on DeepSeek, 10:08 +08:00; each episode's 本集 API 预算 is $15.
SPLIT_AT = datetime(2026, 10, 14, 2, 8, tzinfo=UTC)
EPISODE_BUDGET_USD = 15.0
# 剧本化 of episode 1: v1 on the local model 10:12 +08:00, v2 「不满意换一个」 on Kimi 10:20
# (adopted). Episodes 2 and 3 have an empty script product (「生成这一集的剧本」).
SCRIPT_VERSIONS = (
    ("v1", "local/qwen3.6-27b", "local", "run", datetime(2026, 10, 14, 2, 12, tzinfo=UTC)),
    ("v2", "moonshot/kimi-k2.6", "api", "switch", datetime(2026, 10, 14, 2, 20, tzinfo=UTC)),
)  # fmt: skip
# 素材分析 of episode 1 on DeepSeek, 10:25 +08:00.
ASSETS_MODEL = "deepseek/v4.1-flash"
ASSETS_AT = datetime(2026, 10, 14, 2, 25, tzinfo=UTC)
# The prototype's asset ids (MSW fixtures/demo/assets.ts), by analysis key.
DEMO_ASSET_IDS = {
    "character:c-linwan": "linwan",
    "character:c-zhouyu": "zhouyu",
    "scene:l-stairs:night": "hall",
    "scene:l-flat:night": "room",
    "scene:l-store:night": "store",
    "prop:p-umbrella": "umbrella",
    "prop:p-note": "note",
    "prop:p-hairtie": "band",
    "prop:p-phone": "phone",
    "text:name:便利贴手写": "txt1",
    "text:name:手机锁屏时间": "txt2",
    "voice:c-linwan": "vlinwan",
    "voice:c-zhouyu": "vzhouyu",
}
# Confirmed by the seed (the prototype's demo: 小说 and episode 1's 剧本 已确认).
CONFIRMED_GATES = (("novel", DEMO_SERIES_ID), ("script", "demo-e1"))


def script_product_id(episode_id: str) -> str:
    """``demo-e1`` → ``demo-p-script-e1`` (MSW ``scriptProductId``)."""
    return f"demo-p-script-{episode_id.removeprefix('demo-')}"


def assets_product_id(episode_id: str) -> str:
    """``demo-e1`` → ``demo-p-assets-e1``: the episode's 素材分析."""
    return f"demo-p-assets-{episode_id.removeprefix('demo-')}"


def asset_product_id(asset_id: str) -> str:
    """``linwan`` → ``demo-p-asset-linwan`` (MSW ``assetProductId``)."""
    return f"demo-p-asset-{asset_id}"


async def seed_demo(
    db: Database,
    *,
    novel: NovelService | None = None,
    products: ProductService | None = None,
    compiler: PromptCompiler | None = None,
    gates: GateService | None = None,
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
            await _series_product(products, SPLIT_PRODUCT, episodes.EPISODES_SLOT, "split")
            # Before the plan is adopted: its mirror would create them with random ids.
            for e in (split.demo_fixture() or {}).get("episodes", []):
                await products.ensure(
                    series_id=DEMO_SERIES_ID,
                    owner_type="episode",
                    owner_id=e["id"],
                    slot=episodes.SCRIPT_SLOT,
                    component_id=episodes.SCRIPT_COMPONENT,
                    product_id=script_product_id(e["id"]),
                )
                await products.ensure(
                    series_id=DEMO_SERIES_ID,
                    owner_type="episode",
                    owner_id=e["id"],
                    slot=assets.ASSET_LIST_SLOT,
                    component_id=assets.AssetsComponent.id,
                    product_id=assets_product_id(e["id"]),
                )
        await _seed_novel(novel)
        if products is not None and compiler is not None:
            await _seed_enrich(db, novel, products, compiler)
            await _seed_bible(db, novel, products, compiler)
            await _seed_split(db, novel, products, compiler)
            await _seed_script(db, novel, products, compiler)
            await _seed_assets(db, products, compiler)
        if gates is not None:
            await _seed_gates(db, gates)
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
        products.on_adopt(episodes.EPISODES_SLOT, episodes.materialize)
        products.on_adopt(episodes.SCRIPT_SLOT, script_service.materialize)
        if reset:
            await delete_demo(db)
        novel = NovelService(db, BlobStore(), products)
        gates = GateService(db, EventBus(db), products, slicers())
        await seed_demo(
            db, novel=novel, products=products, compiler=PromptCompiler(), gates=gates, force=True
        )
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
    invalidation.slicer(episodes.EPISODES_SLOT, episodes.episodes_slicer)
    invalidation.slicer(episodes.SCRIPT_SLOT, script_service.script_slicer)
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


async def _seed_split(
    db: Database, novel: NovelService, products: ProductService, compiler: PromptCompiler
) -> None:
    product_id = await _series_product(products, SPLIT_PRODUCT, episodes.EPISODES_SLOT, "split")
    invalidation = slicers()
    async with db.session() as session:
        product = await session.get(Product, product_id)
        bible = await session.get(Product, BIBLE_PRODUCT)
        if product is None or product.current_version_id is not None:
            return
        if bible is None or bible.adopted_version_id is None:
            return
        book = await novel.book(session, DEMO_SERIES_ID)
        if book is None or book.product_id is None:
            return
        deps = [
            await invalidation.dependency(session, book.product_id, "chapters"),
            await invalidation.dependency(session, BIBLE_PRODUCT, "chapters"),
            await invalidation.dependency(session, BIBLE_PRODUCT, "names"),
        ]
        enriched = await session.get(Product, ENRICH_PRODUCT)
        if enriched is not None and enriched.adopted_version_id is not None:
            deps.append(
                await invalidation.dependency(session, ENRICH_PRODUCT, suggestions.ADOPTED_SLICE)
            )
    payload = split.demo_payload(book)
    if payload is None:
        logger.warning("demo episode plan fixture missing")
        return
    intent = compiler.default_intent("split", "zh-CN")
    draft = VersionDraft(
        payload=payload,
        intent=intent,
        compiled=compiler.compile("split", intent, SPLIT_MODEL),
        model_key=SPLIT_MODEL,
        where="api",
        seed=1001,
        params={"mode": "run", "calls": 1},
        dependencies=deps,
        id=SPLIT_VERSION,
        created_at=SPLIT_AT,
    )
    await products.append(product_id, draft, origin="run")
    async with db.session() as session:
        for e in payload["episodes"]:
            row = await session.get(Episode, e["id"])
            if row is not None:
                row.budget_usd = EPISODE_BUDGET_USD
                session.add(row)
        await session.commit()


async def _seed_script(
    db: Database, novel: NovelService, products: ProductService, compiler: PromptCompiler
) -> None:
    invalidation = slicers()
    for entry in (script.demo_fixture() or {}).get("episodes", []):
        product_id = script_product_id(entry["episode"])
        async with db.session() as session:
            product = await session.get(Product, product_id)
            if product is None or product.current_version_id is not None:
                continue
            try:
                inputs = await script.gather(
                    session, invalidation, novel, DEMO_SERIES_ID, entry["episode"]
                )
            except PipelineError:
                return  # the plan is not there yet
        payload = script.demo_payload(inputs)
        if payload is None:
            logger.warning("demo script fixture does not match episode {}", entry["episode"])
            continue
        intent = compiler.default_intent("script", "zh-CN")
        parent = None
        for n, (suffix, model, where, origin, at) in enumerate(SCRIPT_VERSIONS, 1):
            draft = VersionDraft(
                payload=payload,
                intent=intent,
                compiled=compiler.compile("script", intent, model),
                model_key=model,
                where=where,
                seed=1000 + n,
                params={"mode": origin, "calls": 1},
                dependencies=list(inputs.deps),
                id=f"{product_id}-{suffix}",
                created_at=at,
            )
            v = await products.append(product_id, draft, origin=origin, parent_version_id=parent)
            parent = v.id
        assert parent is not None
        await products.adopt(parent)


async def _seed_assets(db: Database, products: ProductService, compiler: PromptCompiler) -> None:
    """Episode 1's asset list, with the prototype's ids; each asset's product first, so the
    list's mirror finds them instead of making ones with random ids."""
    product_id = assets_product_id("demo-e1")
    async with db.session() as session:
        product = await session.get(Product, product_id)
        if product is None or product.current_version_id is not None:
            return
        try:
            inputs = await assets.gather(session, slicers(), DEMO_SERIES_ID, "demo-e1")
        except PipelineError:
            return  # the script is not there yet
    inputs.context["known"] = [
        {"id": asset_id, "key": key, "kind": key.split(":")[0], "name": ""}
        for key, asset_id in DEMO_ASSET_IDS.items()
    ]
    payload = assets.build(assets.demo_fixture()["answer"], inputs.context)
    for a in asset_ops.assets_of(payload):
        await products.ensure(
            series_id=DEMO_SERIES_ID,
            owner_type="asset",
            owner_id=a["id"],
            slot=asset_ops.slot_of(a["kind"]),
            component_id=asset_ops.component_of(a["kind"]),
            product_id=asset_product_id(a["id"]),
        )
    intent = compiler.default_intent("assets", "zh-CN")
    draft = VersionDraft(
        payload=payload,
        intent=intent,
        compiled=compiler.compile("assets", intent, ASSETS_MODEL),
        model_key=ASSETS_MODEL,
        where="api",
        seed=1101,
        params={"mode": "run", "calls": 1},
        dependencies=list(inputs.deps),
        id=f"{product_id}-v1",
        created_at=ASSETS_AT,
    )
    await products.append(product_id, draft, origin="run")


async def _seed_gates(db: Database, gates: GateService) -> None:
    """Confirm the demo's gates that were never decided (a reopened one stays open)."""
    for gate, scope in CONFIRMED_GATES:
        async with db.session() as session:
            if await latest_gate(session, gate, scope) is not None:
                continue
        try:
            await gates.confirm(gate, scope)
        except PipelineError as exc:  # nothing adopted yet, or a run still going
            logger.warning("demo gate {} {} not confirmed: {}", gate, scope, exc.code)
