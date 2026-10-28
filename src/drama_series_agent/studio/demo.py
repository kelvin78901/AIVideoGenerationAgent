"""The demo series 《雨停之前》 (prototype/README.md「示例数据」).

Mock mode seeds it at startup when the database has no series yet, so pages whose MSW
handlers have been removed still have a series to show. Then each block the demo series lacks
is added (only what is missing, so an existing database picks up new blocks on the next
start): the novel (``tests/fixtures/demo/雨停之前.txt``), its enrichment suggestions (小说补全
v1 local → v2 DeepSeek, adopted, the first suggestion accepted; ``enrich.json``) and its story
bible (设定提取 v1, read with that accepted addition; ``extract.json``) and its episode plan
(分集规划 v1 on DeepSeek, three episodes with a $15 budget each; ``split.json``) and episode 1's
script (剧本化 v1 local → v2 「不满意换一个」 on Kimi, adopted; ``script.json``) and its asset
list (素材分析 v1 on DeepSeek, the prototype's 13 assets with their ids; ``assets.json``) and
its shot plan (分镜规划 v1 on DeepSeek, the prototype's nine shots ``demo-shot-1-01`` …;
``plan.json``) and the keyframes of its seven shots that are not continuous (1-01–1-03 a local
draft then the Nano Banana Pro final, confirmed; 1-04–1-07 a draft), each assembled exactly as a
Mock run would. Ids and times match ``web/src/mocks/fixtures/demo/``. Then the novel gate,
episode 1's script gate and its storyboard gate (its other shots confirmed first) are
confirmed, once: a gate the user reopened stays open. Once the storyboard is confirmed, episode
1's video takes (``DEMO_TAKES``) are made like Mock runs too.
``drama-studio demo [--reset]`` runs the same seeding on demand; ``--reset`` deletes the demo
series first.
"""

from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime
from typing import Any

from loguru import logger
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from drama_series_agent.assets import ops as asset_ops
from drama_series_agent.assets import service as assets_service
from drama_series_agent.assets.service import record_asset_gate
from drama_series_agent.bible.service import BIBLE_SLOT, bible_slicer, materialize
from drama_series_agent.core.config import SpecConfig, get_config
from drama_series_agent.core.db import Database, migrate
from drama_series_agent.core.events import EventBus
from drama_series_agent.core.models_db import (
    Asset,
    Episode,
    Product,
    ProductVersion,
    Series,
    Shot,
    SuggestionDecision,
)
from drama_series_agent.core.paths import REPO_ROOT, database_path
from drama_series_agent.core.storage import BlobStore
from drama_series_agent.episodes import service as episodes
from drama_series_agent.episodes.service import gate_confirmed, latest_gate
from drama_series_agent.modelhub.adapters.mock import (
    MOCK_TEXT_KEY,
    mock_picture,
    sine_wav,
    solid_mp4,
)
from drama_series_agent.modelhub.pricing import to_usd
from drama_series_agent.novel.service import NOVEL_SLOT, FixedIds, NovelService, novel_slicer
from drama_series_agent.pipeline.components import assets, enrich, kf, plan, script, split, vid
from drama_series_agent.pipeline.components.extract import demo_payload
from drama_series_agent.pipeline.components.img import asset_aspect
from drama_series_agent.pipeline.components.media import frame_size, prompt_text
from drama_series_agent.pipeline.components.text import text_settings
from drama_series_agent.pipeline.components.views import (
    REF_VIEWS_SLOT,
    VIEWS,
    ViewsComponent,
    negative_for,
)
from drama_series_agent.pipeline.drafts import DependencyDraft, VersionDraft, file_entry
from drama_series_agent.pipeline.errors import PipelineError
from drama_series_agent.pipeline.gates import GateService
from drama_series_agent.pipeline.invalidation import Invalidation
from drama_series_agent.pipeline.products import ProductService
from drama_series_agent.pipeline.vselect import default_rules
from drama_series_agent.prompts.compiler import PromptCompiler
from drama_series_agent.qa import ocr
from drama_series_agent.script import service as script_service
from drama_series_agent.shots import service as shots_service
from drama_series_agent.spec.compat import model_caps
from drama_series_agent.spec.dims import dims
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
# The prototype's candidates (MSW fixtures/demo/assets.ts): each asset's versions (model, time
# +08:00 on the demo day, stage) and the candidate it is locked to (None: still to choose).
# 林晚 is hybrid: a local draft, then the API final from its first picture (SPEC 7.7).
DEMO_ASSET_VERSIONS: dict[str, tuple[tuple[tuple[str, str, str | None], ...], int | None]] = {
    "linwan": (
        (("comfy/qwen-image", "10:31", "draft"), ("google/nano-banana-pro", "10:36", "final")),
        0,
    ),
    "hall": ((("comfy/qwen-image", "10:33", "draft"),), 0),
    "room": ((("comfy/qwen-image", "10:33", "draft"),), None),
    "umbrella": ((("comfy/qwen-image", "10:33", "draft"),), 0),
    "note": ((("comfy/qwen-image", "10:33", "draft"),), 0),
    "band": ((("comfy/qwen-image", "10:33", "draft"),), None),
    "phone": ((("comfy/qwen-image", "10:33", "draft"),), 0),
    "txt1": ((("openai/gpt-image-2", "10:44", None),), None),
    "txt2": ((("openai/gpt-image-2", "10:44", None),), 0),
    # Free local auditions, then the MiniMax final from A (design + five emotions), locked whole.
    "vlinwan": (
        (("local/qwen3-tts", "10:38", "draft"), ("minimax/speech-2.8-hd", "10:40", "final")),
        0,
    ),
}
# What each run cost (the API's price × pictures; a voice final is its $3 design + characters).
DEMO_ASSET_COST = {
    "google/nano-banana-pro": 0.14,
    "openai/gpt-image-2": 1.12,
    "minimax/speech-2.8-hd": 3.004,  # 40 characters: the trial clip and the five emotions
}
# 林晚's first two lines (the script's), which her auditions read.
VOICE_LINES = ("……周屿？", "三年了。他凭什么。")
VOICE_WAVES = (
    (10, 18, 26, 14, 22, 30, 12, 20, 16, 28, 10, 18, 24, 12, 20, 14),
    (14, 22, 12, 28, 18, 10, 24, 30, 16, 12, 22, 18, 10, 26, 14, 20),
    (8, 16, 22, 30, 12, 18, 26, 10, 20, 28, 14, 10, 24, 16, 22, 12),
)
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
# 分镜规划 of episode 1 on DeepSeek, 10:48 +08:00.
PLAN_MODEL = "deepseek/v4-pro"
# 关键帧 of episode 1 (MSW fixtures/demo/shots.ts): the local draft (three pictures) and, for the
# confirmed shots, the Nano Banana 2.1 final from its first picture (+08:00 on the demo day).
KF_DRAFT_MODEL = "comfy/flux3-klein"
KF_FINAL_MODEL = "google/nano-banana-2.1"
KF_FINAL_COST = 0.06  # what 2.1 cost in the bake-off (thinking on: a little over the estimate)
DEMO_KEYFRAMES: dict[str, tuple[str, bool]] = {  # label → (draft time, confirmed at 11:02)
    "1-01": ("10:55", True),
    "1-02": ("10:55", True),
    "1-03": ("10:55", True),
    "1-04": ("11:06", False),
    "1-05": ("11:06", False),
    "1-06": ("11:06", False),
    "1-07": ("11:06", False),
}
KF_FINAL_AT = "11:02"
# The other shots are confirmed with 分镜确认 (Kelvin 2026-10-27: the demo's storyboard is
# confirmed so that 生成 can run), each on its picked first draft.
SHOTS_CONFIRMED_AT = "11:24"
# Confirmed by the seed (the prototype's demo: 小说, episode 1's 剧本 and 分镜 已确认).
CONFIRMED_GATES = (("novel", DEMO_SERIES_ID), ("script", "demo-e1"), ("storyboard", "demo-e1"))
# Episode 1's takes (prototype Generate.dc.html), each (model, time, origin, fallback reason):
# 1-01–1-03 a local H3 draft, then 「用 API 出终版」 from it (Regenerate-2K), adopted; 1-04 the
# first run's two drafts, a third that timed out locally and was made on the H3 API, a fourth
# 「不满意换一个」 on Seedance 2.5, still to pick. 1-05–1-07 have not run; 1-08 and 1-09 wait for
# the shot they continue.
TAKE_LOCAL = "comfy/h3"
# 1-04 is 原生同步 with 林晚's locked voice: local takes go to the workflow that takes it.
TAKE_VOICED = "comfy/h3-r2v"
TAKE_FINAL = "minimax/h3-regenerate-2k"
DEMO_TAKES: dict[str, tuple[tuple[str, str, str, str | None], ...]] = {
    "1-01": ((TAKE_LOCAL, "11:02", "run", None), (TAKE_FINAL, "11:06", "final", None)),
    "1-02": ((TAKE_LOCAL, "11:09", "run", None), (TAKE_FINAL, "11:13", "final", None)),
    "1-03": ((TAKE_LOCAL, "11:15", "run", None), (TAKE_FINAL, "11:19", "final", None)),
    "1-04": (
        (TAKE_VOICED, "11:31", "run", None),
        (TAKE_VOICED, "11:31", "run", None),
        ("minimax/h3-api", "11:41", "fallback", "timeout"),
        ("volc/seedance-2.5", "11:52", "switch", None),
    ),
}
# What a second of each cost (元, the China-site prices in providers.yaml: H3 at the delivery
# tier, Seedance at 1080p, a final its output and input video).
TAKE_PRICE_CNY = {
    TAKE_FINAL: 0.60,
    "minimax/h3-api": 0.80,
    "volc/seedance-2.5": 3.742,
}


def script_product_id(episode_id: str) -> str:
    """``demo-e1`` → ``demo-p-script-e1`` (MSW ``scriptProductId``)."""
    return f"demo-p-script-{episode_id.removeprefix('demo-')}"


def plan_product_id(episode_id: str) -> str:
    """``demo-p-plan-e1`` (the MSW fixture's)."""
    return f"demo-p-plan-{episode_id.removeprefix('demo-')}"


def keyframe_product_id(label: str) -> str:
    """``1-04`` → ``demo-p-kf-1-04`` (MSW ``kfProductId``)."""
    return f"demo-p-kf-{label}"


# Episode 1's shots (1-08 and 1-09 continue the shot before; no keyframe of their own).
DEMO_SHOTS = (*DEMO_KEYFRAMES, "1-08", "1-09")


def video_product_id(label: str) -> str:
    """``1-04`` → ``demo-p-vid-1-04`` (MSW ``videoProductId``)."""
    return f"demo-p-vid-{label}"


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
                await products.ensure(
                    series_id=DEMO_SERIES_ID,
                    owner_type="episode",
                    owner_id=e["id"],
                    slot=plan.SHOT_PLAN_SLOT,
                    component_id=plan.PlanComponent.id,
                    product_id=plan_product_id(e["id"]),
                )
            for label in DEMO_KEYFRAMES:
                await products.ensure(
                    series_id=DEMO_SERIES_ID,
                    owner_type="shot",
                    owner_id=f"demo-shot-{label}",
                    slot=shots_service.KEYFRAME_SLOT,
                    component_id=kf.KfComponent.id,
                    product_id=keyframe_product_id(label),
                )
            for label in DEMO_SHOTS:
                await products.ensure(
                    series_id=DEMO_SERIES_ID,
                    owner_type="shot",
                    owner_id=f"demo-shot-{label}",
                    slot=shots_service.VIDEO_SLOT,
                    component_id=shots_service.VID_COMPONENT,
                    product_id=video_product_id(label),
                )
        await _seed_novel(novel)
        if products is not None and compiler is not None:
            await _seed_enrich(db, novel, products, compiler)
            await _seed_bible(db, novel, products, compiler)
            await _seed_split(db, novel, products, compiler)
            await _seed_script(db, novel, products, compiler)
            await _seed_assets(db, products, compiler)
            await _seed_asset_versions(db, products, compiler)
            await _seed_plan(db, products, compiler)
            await _seed_keyframes(db, products, compiler)
        if gates is not None:
            await _seed_gates(db, gates, products)
        if products is not None and compiler is not None:
            await _seed_takes(db, products, compiler)
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
        products.on_adopt(episodes.SCRIPT_SLOT, shots_service.ensure_plan)
        products.on_adopt(assets.ASSET_LIST_SLOT, assets_service.materialize)
        products.on_adopt(plan.SHOT_PLAN_SLOT, shots_service.materialize)
        products.on_adopt(shots_service.KEYFRAME_SLOT, shots_service.lock_spec)
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
    invalidation.slicer(assets.ASSET_LIST_SLOT, plan.asset_list_slicer)
    invalidation.slicer(plan.SHOT_PLAN_SLOT, plan.shot_plan_slicer)
    invalidation.check(shots_service.KEYFRAME_SLOT, kf.stale_aspect)
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


async def _seed_plan(db: Database, products: ProductService, compiler: PromptCompiler) -> None:
    """Episode 1's shot plan from the fixture, with the prototype's shot ids, adopted (its
    mirror gives each shot that is not continuous its keyframe product)."""
    product_id = plan_product_id("demo-e1")
    async with db.session() as session:
        product = await session.get(Product, product_id)
        if product is None or product.current_version_id is not None:
            return
        try:
            inputs = await plan.gather(session, slicers(), DEMO_SERIES_ID, "demo-e1")
        except PipelineError:
            return  # the script is not there yet
    payload = plan.build(plan.demo_fixture()["answer"], inputs.context)
    ids = {s["id"]: f"demo-shot-1-{n:02d}" for n, s in enumerate(payload["shots"], 1)}
    for s in payload["shots"]:
        s["id"] = ids[s["id"]]
        if s.get("tail_from"):
            s["tail_from"] = ids[s["tail_from"]]
    intent = compiler.default_intent("plan", "zh-CN")
    draft = VersionDraft(
        payload=payload,
        intent=intent,
        compiled=compiler.compile("plan", intent, PLAN_MODEL),
        model_key=PLAN_MODEL,
        where="api",
        seed=1301,
        params={"mode": "run", "calls": 1},
        dependencies=list(inputs.deps),
        id=f"{product_id}-v1",
        created_at=_demo_time("10:48"),
    )
    await products.append(product_id, draft, origin="run")


async def _seed_keyframes(db: Database, products: ProductService, compiler: PromptCompiler) -> None:
    """Episode 1's keyframes, each built from what a run reads (``kf.gather``): a local draft,
    then for 1-01–1-03 the API final from its first picture, locked with the shot's decision
    (确认这个镜头)."""
    store = BlobStore()
    invalidation = slicers()
    plan_id = plan_product_id("demo-e1")
    async with db.session() as session:
        found = await shots_service.keyframe_products(
            session, [f"demo-shot-{label}" for label in DEMO_KEYFRAMES]
        )
        plan_row = await session.get(Product, plan_id)
    if plan_row is None or plan_row.adopted_version_id is None:
        return  # the plan is not there yet
    for n, (label, (at, confirmed)) in enumerate(DEMO_KEYFRAMES.items(), 1):
        shot_id = f"demo-shot-{label}"
        product = found.get(shot_id)
        if product is None or product.current_version_id is not None:
            continue
        async with db.session() as session:
            shot = await session.get(Shot, shot_id)
            try:
                inputs = await kf.gather(session, invalidation, product)
            except PipelineError as exc:
                logger.warning("demo keyframe {} not seeded: {}", label, exc.code)
                continue
        intent = shot.intent if shot is not None else ""
        draft = await products.append(
            product.id,
            _keyframe_draft(store, compiler, product, inputs, intent, None, n, at),
            origin="run",
            adopt=False,
        )
        if not confirmed:
            continue
        first = next(f for f in draft.files_json if f.get("role") == "candidate")
        final = _keyframe_draft(store, compiler, product, inputs, intent, first, n, KF_FINAL_AT)
        final.params["source"] = {"version_id": draft.id, "idx": 0}
        v = await products.append(
            product.id, final, origin="run", parent_version_id=draft.id, adopt=False
        )

        async def record(
            session: AsyncSession, p: Product, _: ProductVersion, shot_id: str = shot_id
        ) -> None:
            at = _demo_time(KF_FINAL_AT)
            await shots_service.record_shot_gate(
                session, invalidation, DEMO_SERIES_ID, shot_id, plan_row, p, "confirm", at
            )

        await products.lock_pick(product.id, v.id, None, record=record)


def _keyframe_draft(
    store: BlobStore,
    compiler: PromptCompiler,
    product: Product,
    inputs: Any,
    intent: str,
    source: dict[str, Any] | None,
    n: int,
    at: str,
) -> VersionDraft:
    """A keyframe version as ``KfComponent.run`` makes it: the local draft (three pictures at
    the draft tier) or the API final from ``source`` (one at the delivery tier)."""
    final = source is not None
    model = KF_FINAL_MODEL if final else KF_DRAFT_MODEL
    cfg = get_config()
    local = next((m for m in cfg.providers.local_models if m.key == model), None)
    limit = kf.ref_limit(
        model_caps(cfg, model).get("max_refs"),
        "local" if local is not None else "api",
        local.workflow if local is not None else None,
    )
    refs, deps, blocks = kf.pick_refs(inputs, source["sha256"] if source else None, limit)
    frame = inputs.context["frame"]
    size = dims(frame["aspect"], frame["delivery"] if final else "draft")
    stage = "final" if final else "draft"
    files = [
        file_entry(
            "candidate",
            store.put_bytes(mock_picture(size.w, size.h, model, product.id, stage, i)),
            "image/png",
            w=size.w,
            h=size.h,
            idx=i,
        )
        for i in range(1 if final else 3)
    ]
    compiled = compiler.compile(kf.KfComponent.id, intent, model)
    prompt = store.put_bytes(prompt_text(compiled, blocks).encode("utf-8"))
    files.append(file_entry("prompt", prompt, "text/plain; charset=utf-8"))
    return VersionDraft(
        payload={
            "candidates": [{} for _ in range(len(files) - 1)],
            "aspect": frame["aspect"],
            "refs": [r["name"] for r in refs if r["kind"] != "draft"],
        },
        files=files,
        intent=intent,
        compiled=compiled,
        model_key=model,
        where="api" if final else "local",
        seed=1400 + n,
        params={"mode": "run", "calls": 1},
        cost_usd=KF_FINAL_COST if final else 0.0,
        stage=stage,
        dependencies=[*inputs.deps, *deps],
        id=f"{product.id}-v{2 if final else 1}",
        created_at=_demo_time(at),
    )


def _demo_time(hhmm: str) -> datetime:
    """``10:31`` on the demo day, +08:00."""
    h, m = (int(x) for x in hhmm.split(":"))
    return datetime(2026, 10, 14, h - 8, m, tzinfo=UTC)


def _text_reads(exact: str, method: str) -> list[str]:
    """What OCR reads on each of the four text pictures (the prototype's): drawn by the model,
    B misreads 点 as 占 and D drops the character before the last (the prototype drops the
    last, the 。, which passes since 2026-10-21); a base for compositing has none."""
    if method == "composite":
        return [""] * 4
    return [exact, exact.replace("点", "占"), exact, exact[:-2] + exact[-1:]]


def _demo_wave(i: int) -> list[float]:
    """The prototype's 16-bar waveform of candidate ``i``, as the 64 bars a clip has."""
    return [h / 30 for h in VOICE_WAVES[i % len(VOICE_WAVES)] for _ in range(4)]


def _tone(store: BlobStore, text: str, freq: float, **extra: Any) -> dict[str, Any]:
    """A clip (a tone as long as the line would take) as a ``files[]`` entry."""
    seconds = round(max(0.5, len(text) * 0.25), 3)
    sha = store.put_bytes(sine_wav(seconds, freq_hz=freq))
    return file_entry(extra.pop("role"), sha, "audio/wav", duration_s=seconds, **extra)


def _voice_files(
    store: BlobStore, asset: Asset, stage: str | None
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """林晚's auditions (three drafts reading her two lines) or her final (the design's trial
    clip and the five emotions)."""
    cfg = get_config().voice
    lines = VOICE_LINES
    if stage == "draft":
        files, candidates = [], []
        for i, draft in enumerate(cfg.drafts[:3]):
            wave = _demo_wave(i)
            for j, text in enumerate(lines):
                freq = 180 + 40 * i + 7 * j
                files.append(
                    _tone(store, text, freq, role="candidate", idx=i, line=j, waveform=wave)
                )
            design = f"{(asset.seed_json or {}).get('description', '')}；{draft.hint}"
            candidates.append({"label": draft.label, "design": design, "waveform": wave})
        return {"candidates": candidates}, files
    trial = "\n".join(lines)
    files = [_tone(store, trial, 185, role="anchor", idx=None, line=None, waveform=_demo_wave(0))]
    for k, emotion in enumerate(cfg.emotions):
        files.append(
            _tone(
                store,
                lines[0],
                200 + 30 * k,
                role="variant",
                idx=k,
                line=0,
                emotion=emotion.id,
                waveform=_demo_wave(k),
            )
        )
    payload = {
        "provider": "minimax",
        "voice_id": f"demo-voice-{asset.id}",
        "emotions": [e.id for e in cfg.emotions],
        "label": cfg.drafts[0].label,
    }
    return payload, files


def _asset_files(
    store: BlobStore, asset: Asset, product_id: str, model: str, stage: str | None
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """A demo version's payload and candidate files (Mock pictures, or tones for a voice)."""
    if asset.kind == "voice":
        return _voice_files(store, asset, stage)
    aspect = asset_aspect(asset.kind, "9:16")  # the demo's spec; scenes are drawn 16:9
    size = dims(aspect, "draft" if stage == "draft" else "1080p")  # type: ignore[arg-type]
    text = text_settings(asset, None)
    reads: list[str | None] = [None] * (1 if stage == "final" else 4)
    if asset.kind == "text":
        reads = list(_text_reads(text["exact"], text["method"]))
    files = []
    for i, read in enumerate(reads):
        texts = {MOCK_TEXT_KEY: read} if read else None
        png = mock_picture(size.w, size.h, model, product_id, stage, i, texts=texts)
        sha = store.put_bytes(png)
        files.append(file_entry("candidate", sha, "image/png", w=size.w, h=size.h, idx=i))
    if asset.kind == "text":
        checks = [ocr.check(text["exact"], r, text["method"]) for r in reads]
        return {"candidates": checks, "aspect": aspect, "refs": [], "text": text}, files
    return {"candidates": [{} for _ in reads], "aspect": aspect, "refs": []}, files


async def _seed_asset_versions(
    db: Database, products: ProductService, compiler: PromptCompiler
) -> None:
    """The prototype's candidates for the assets that have them, 7 of 13 locked (each with its
    gate decision), and the views drawn from 林晚's locked picture."""
    store = BlobStore()
    invalidation = slicers()

    async def record(session: AsyncSession, p: Product, v: ProductVersion) -> None:
        await record_asset_gate(session, invalidation, p, "confirm")

    for asset_id, (runs, locked) in DEMO_ASSET_VERSIONS.items():
        product_id = asset_product_id(asset_id)
        async with db.session() as session:
            asset = await session.get(Asset, asset_id)
            product = await session.get(Product, product_id)
        if asset is None or product is None or product.current_version_id is not None:
            continue
        intent = str((asset.seed_json or {}).get("description") or "")
        parent = None
        for n, (model, at, stage) in enumerate(runs, 1):
            payload, files = _asset_files(store, asset, product_id, model, stage)
            draft = VersionDraft(
                payload=payload,
                files=files,
                intent=intent,
                compiled=compiler.compile(product.component_id, intent, model),
                model_key=model,
                where="local" if model.startswith("comfy/") else "api",
                seed=1200 + n,
                params={"mode": "run", "calls": 1},
                cost_usd=DEMO_ASSET_COST.get(model, 0.0),
                stage=stage,
                id=f"{product_id}-v{n}",
                created_at=_demo_time(at),
            )
            v = await products.append(
                product_id, draft, origin="run", parent_version_id=parent, adopt=False
            )
            parent = v.id
        if locked is None or parent is None:
            continue
        # A voice's final has no candidates: it is locked whole.
        await products.lock_pick(
            product_id, parent, None if asset.kind == "voice" else locked, record=record
        )
        if asset.kind == "character":
            await _seed_views(db, products, compiler, asset, store, invalidation)


async def _seed_views(
    db: Database,
    products: ProductService,
    compiler: PromptCompiler,
    asset: Asset,
    store: BlobStore,
    invalidation: Invalidation,
) -> None:
    """补视图 of a locked character: side, back and four expressions, adopted."""
    ref_id = asset_product_id(asset.id)
    views_id = f"demo-p-views-{asset.id}"
    p = await products.ensure(
        series_id=DEMO_SERIES_ID,
        owner_type="asset",
        owner_id=asset.id,
        slot=REF_VIEWS_SLOT,
        component_id=ViewsComponent.id,
        product_id=views_id,
    )
    if p.current_version_id is not None:
        return
    async with db.session() as session:
        dep = await invalidation.dependency(session, ref_id, "")
    model = "comfy/qwen-image-edit-hq"
    size = dims("9:16", "draft")
    files = [
        file_entry(
            "view",
            store.put_bytes(mock_picture(size.w, size.h, model, views_id, view)),
            "image/png",
            w=size.w,
            h=size.h,
            idx=i,
            view=view,
        )
        for i, view in enumerate(VIEWS)
    ]
    intent = compiler.default_intent(ViewsComponent.id, "zh-CN")
    draft = VersionDraft(
        payload={
            "views": list(VIEWS),
            "from": dep.upstream_hash,
            "negative": {view: negative_for(view) for view in VIEWS},
        },
        files=files,
        intent=intent,
        compiled=compiler.compile(ViewsComponent.id, intent, model),
        model_key=model,
        where="local",
        seed=1301,
        params={"mode": "run", "calls": len(VIEWS)},
        dependencies=[dep],
        id=f"{views_id}-v1",
        created_at=_demo_time("10:37"),
    )
    await products.append(views_id, draft, origin="run")


async def _seed_gates(
    db: Database, gates: GateService, products: ProductService | None = None
) -> None:
    """Confirm the demo's gates that were never decided (a reopened one stays open); 分镜确认
    first confirms the shots that are not."""
    for gate, scope in CONFIRMED_GATES:
        async with db.session() as session:
            if await latest_gate(session, gate, scope) is not None:
                continue
        if gate == shots_service.STORYBOARD_GATE and products is not None:
            await _confirm_shots(db, products, scope)
        try:
            await gates.confirm(gate, scope)
        except PipelineError as exc:  # nothing adopted yet, or a run still going
            logger.warning("demo gate {} {} not confirmed: {}", gate, scope, exc.code)


async def _confirm_shots(db: Database, products: ProductService, episode_id: str) -> None:
    """「确认这个镜头」 for each shot never decided: the keyframe's current version locked on its
    picked picture (the first unless one was picked), a continuous shot only the decision."""
    invalidation = slicers()
    at = _demo_time(SHOTS_CONFIRMED_AT)
    async with db.session() as session:
        plan_row = await session.get(Product, plan_product_id(episode_id))
        rows = (
            await session.exec(
                select(Shot).where(Shot.episode_id == episode_id, col(Shot.retired).is_(False))
            )
        ).all()
        found = await shots_service.keyframe_products(session, [r.id for r in rows])
        undecided = [
            r.id for r in rows if await latest_gate(session, shots_service.SHOT_GATE, r.id) is None
        ]
    if plan_row is None:
        return
    for shot_id in undecided:
        keyframe = found.get(shot_id)
        if keyframe is None:  # continuous: it starts from the shot before
            async with db.session() as session:
                await shots_service.record_shot_gate(
                    session, invalidation, DEMO_SERIES_ID, shot_id, plan_row, None, "confirm", at
                )
                await session.commit()
            continue
        current = keyframe.current_version_id
        if current is None or keyframe.locked_hash:
            continue
        pick = keyframe.pick_json or {}
        idx = int(pick.get("idx") or 0) if pick.get("version_id") == current else 0

        async def record(
            session: AsyncSession, p: Product, _: ProductVersion, shot_id: str = shot_id
        ) -> None:
            await shots_service.record_shot_gate(
                session, invalidation, DEMO_SERIES_ID, shot_id, plan_row, p, "confirm", at
            )

        await products.lock_pick(
            keyframe.id, current, idx, record=record, pick_id=f"{keyframe.id}-v2", at=at
        )


async def _seed_takes(db: Database, products: ProductService, compiler: PromptCompiler) -> None:
    """Episode 1's video takes (``DEMO_TAKES``), each made from what a run reads
    (``vid.gather``) and stored as a Mock run stores it; once 分镜 is confirmed, for a shot with
    no take yet."""
    store = BlobStore()
    invalidation = slicers()
    async with db.session() as session:
        if not await gate_confirmed(session, shots_service.STORYBOARD_GATE, "demo-e1"):
            return
    for label, seeds in DEMO_TAKES.items():
        async with db.session() as session:
            product = await session.get(Product, video_product_id(label))
            if product is None or product.current_version_id is not None:
                continue
            try:
                inputs = await vid.gather(session, invalidation, product)
            except PipelineError as exc:
                logger.warning("demo takes of {} not seeded: {}", label, exc.code)
                continue
            shot = await session.get(Shot, product.owner_id)
        intent = shot.intent if shot is not None else ""
        first: ProductVersion | None = None
        last: ProductVersion | None = None
        for n, (model, at, origin, fallback) in enumerate(seeds, 1):
            source = first if origin == "final" else None
            take = await _take_draft(
                store, compiler, product, inputs, intent, (model, n, at, origin, fallback), source
            )
            last = await products.append(
                product.id,
                take,
                origin="run" if origin == "final" else origin,
                parent_version_id=source.id if source is not None else None,
                adopt=False,
            )
            first = first or last
        if last is not None and seeds[-1][2] == "final":
            await products.adopt(last.id)


def _take_select(model: str) -> dict[str, Any]:
    """Why a seeded local take went to its workflow, as ``vselect.choose`` says it: the
    config's rule for 原生同步 with a voice, else the route's default."""
    for i, rule in enumerate(default_rules().rules):
        if rule.model == model:
            return {"by": "rule", "rule": i, "when": rule.when.model_dump(exclude_none=True)}
    return {"by": "default"}


async def _take_draft(
    store: BlobStore,
    compiler: PromptCompiler,
    product: Product,
    inputs: Any,
    intent: str,
    seed_row: tuple[str, int, str, str, str | None],
    source: ProductVersion | None,
) -> VersionDraft:
    """A take as ``VidComponent.run`` stores it (a Mock clip with the head cut off, its poster
    and last frame; a local draft keeps the raw clip and the request a final resends), or the
    API final of ``source`` at 2K, made from its raw clip and with its prompt."""
    model, n, at, origin, fallback = seed_row
    cfg = get_config()
    context = inputs.context
    frame = context["frame"]
    where = "local" if model.startswith("comfy/") else "api"
    seconds = float(context["seconds"])
    if source is not None:
        raw = next(f for f in source.files_json if f["role"] == "raw")
        seconds = float(raw["duration_s"])
        size = dims(frame["aspect"], "2k")
    else:
        size = frame_size(frame, where)
    local = next((m for m in cfg.providers.local_models if m.key == model), None)
    limit = kf.ref_limit(
        model_caps(cfg, model).get("max_refs"), where, local.workflow if local else None
    )
    refs, deps, _ = kf.pick_refs(inputs, None, 0 if source is not None else limit)
    voices = list(context["voices"]) if model == TAKE_VOICED and source is None else []
    deps += [DependencyDraft(v["product_id"], v["hash"], "") for v in voices if v.get("hash")]
    color = hashlib.sha256(f"{product.id}:{n}".encode()).hexdigest()[:6]
    hz = 220.0 + n * 40 if context["audio_mode"] != "none" else None
    clip = await solid_mp4(size.w, size.h, seconds, int(frame["fps"]), color, audio_hz=hz)
    files, info = await vid.clip_files(store, store.put_bytes(clip), raw=where == "local")
    params: dict[str, Any] = {"mode": "run" if origin == "final" else origin, "calls": 1}
    if source is not None:
        prompt_sha = next(f for f in source.files_json if f["role"] == "prompt")["sha256"]
        compiled = source.compiled or ""
        params["source"] = {"version_id": source.id}
        payload = {
            **source.payload_json,
            "duration_s": round(info.duration_s, 3),
            "resolution": "2k",
        }
    else:
        compiled = compiler.compile(vid.VidComponent.id, intent, model)
        prompt_sha = store.put_bytes(prompt_text(compiled, inputs.blocks).encode("utf-8"))
        request: dict[str, Any] = {
            "aspect": frame["aspect"],
            "duration_s": seconds,
            "fps": int(frame["fps"]),
            "first_frame": context["first_frame"],
            "with_audio": context["audio_mode"] != "none",
        }
        if refs:
            request["refs"] = [r["sha256"] for r in refs]
        if voices:
            request["ref_audio"] = [v["sha256"] for v in voices]
        if where == "local":
            params["request"] = request
            params["select"] = _take_select(model)
        payload = {
            "duration_s": round(info.duration_s, 3),
            "asked_s": context["seconds"],
            "resolution": "768p" if where == "local" else frame["delivery"],
            "aspect": frame["aspect"],
            "audio_mode": context["audio_mode"],
            "refs": [r["name"] for r in refs],
            "voices": [v["who"] for v in voices],
        }
    files.append(file_entry("prompt", prompt_sha, "text/plain; charset=utf-8"))
    cost = to_usd(TAKE_PRICE_CNY.get(model, 0.0) * seconds, "CNY")
    return VersionDraft(
        payload=payload,
        files=files,
        intent=intent,
        compiled=compiled,
        model_key=model,
        where=where,
        seed=2100 + n,
        params=params,
        cost_usd=round(cost, 6),
        fallback_reason=fallback,
        stage="draft" if where == "local" else ("final" if source is not None else None),
        dependencies=[*inputs.deps, *deps],
        id=f"{product.id}-v{n}",
        created_at=_demo_time(at),
    )
