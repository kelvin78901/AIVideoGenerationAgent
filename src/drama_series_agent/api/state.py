"""Process-wide services owned by the FastAPI app (created in the lifespan, not at import)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

import httpx
from fastapi import Request

from drama_series_agent.assets import service as assets_service
from drama_series_agent.assets.dub import DubService
from drama_series_agent.assets.service import AssetService
from drama_series_agent.bible.service import BIBLE_SLOT, BibleService, bible_slicer, materialize
from drama_series_agent.core import secrets
from drama_series_agent.core.config import get_config
from drama_series_agent.core.db import Database, migrate
from drama_series_agent.core.events import EventBus
from drama_series_agent.core.jobs import JobQueue
from drama_series_agent.core.models_db import Product
from drama_series_agent.core.paths import database_path
from drama_series_agent.core.storage import BlobStore
from drama_series_agent.episodes import service as episodes_service
from drama_series_agent.episodes.service import EPISODES_SLOT, EpisodeService
from drama_series_agent.modelhub.adapters.base import ModelSpec
from drama_series_agent.modelhub.adapters.openai_compat import OpenAICompatAdapter
from drama_series_agent.modelhub.budget import Budget, BudgetGuardImpl
from drama_series_agent.modelhub.registry import Registry
from drama_series_agent.modelhub.router import Router
from drama_series_agent.novel.service import NOVEL_SLOT, NovelService, novel_slicer
from drama_series_agent.pipeline.cascade import CascadeService
from drama_series_agent.pipeline.component import ComponentRegistry, Services
from drama_series_agent.pipeline.components.assets import ASSET_LIST_SLOT, AssetsComponent
from drama_series_agent.pipeline.components.dub import LINE_AUDIO_SLOT, DubComponent
from drama_series_agent.pipeline.components.enrich import EnrichComponent
from drama_series_agent.pipeline.components.extract import ExtractComponent
from drama_series_agent.pipeline.components.img import ImgComponent
from drama_series_agent.pipeline.components.script import ScriptComponent
from drama_series_agent.pipeline.components.split import SplitComponent
from drama_series_agent.pipeline.components.text import TextComponent
from drama_series_agent.pipeline.components.views import ViewsComponent
from drama_series_agent.pipeline.components.voice import VoiceComponent
from drama_series_agent.pipeline.gates import GateService
from drama_series_agent.pipeline.impact import ImpactService, register_kinds
from drama_series_agent.pipeline.invalidation import Invalidation
from drama_series_agent.pipeline.products import ProductService
from drama_series_agent.pipeline.runs import RunService
from drama_series_agent.prompts.compiler import PromptCompiler
from drama_series_agent.script import service as script_service
from drama_series_agent.script.service import ScriptService
from drama_series_agent.setup.service import SetupService
from drama_series_agent.suggestions import service as suggestions_service
from drama_series_agent.suggestions.service import SUGGESTIONS_SLOT, SuggestionService


@dataclass
class StudioState:
    db: Database
    bus: EventBus
    jobs: JobQueue
    store: BlobStore
    registry: Registry
    router: Router
    setup: SetupService
    products: ProductService
    components: ComponentRegistry
    runs: RunService
    budget: Budget
    novel: NovelService
    bible: BibleService
    suggestions: SuggestionService
    episodes: EpisodeService
    script: ScriptService
    assets: AssetService
    dub: DubService
    gates: GateService
    impact: ImpactService
    cascade: CascadeService
    # Tests inject an httpx mock transport here; None means real network.
    http_transport: httpx.AsyncBaseTransport | None = None

    @classmethod
    async def start(cls, db_path: Path | None = None) -> StudioState:
        path = db_path or database_path()
        await asyncio.to_thread(migrate, path)
        db = Database(path)
        bus = EventBus(db)
        store = BlobStore()
        registry = Registry.from_config(get_config())
        jobs = JobQueue(db, bus)
        setup = SetupService(db, bus, jobs)
        router = Router(
            db,
            bus,
            registry,
            store=store,
            capabilities=setup.capabilities,
            budget=BudgetGuardImpl(db),
        )
        budget = Budget(db)
        invalidation = Invalidation()
        invalidation.slicer(NOVEL_SLOT, novel_slicer)
        invalidation.slicer(BIBLE_SLOT, bible_slicer)
        invalidation.slicer(SUGGESTIONS_SLOT, suggestions_service.suggestions_slicer)
        invalidation.slicer(EPISODES_SLOT, episodes_service.episodes_slicer)
        invalidation.slicer(episodes_service.SCRIPT_SLOT, script_service.script_slicer)
        products = ProductService(db, bus, invalidation)
        products.on_adopt(BIBLE_SLOT, materialize)
        products.on_adopt(SUGGESTIONS_SLOT, suggestions_service.materialize)
        products.on_adopt(EPISODES_SLOT, episodes_service.materialize)
        products.on_adopt(episodes_service.SCRIPT_SLOT, script_service.materialize)
        products.on_adopt(ASSET_LIST_SLOT, assets_service.materialize)
        compiler = PromptCompiler()
        components = ComponentRegistry(
            Services(
                db=db,
                router=router,
                registry=registry,
                compiler=compiler,
                store=store,
                invalidation=invalidation,
            )
        )
        novel = NovelService(db, store, products)
        components.add(ExtractComponent(components.services, novel))
        enrich = EnrichComponent(components.services, novel)
        components.add(enrich)
        components.add(SplitComponent(components.services, novel))
        script = ScriptComponent(components.services, novel, budget)
        components.add(script)
        components.add(AssetsComponent(components.services))
        components.add(ImgComponent(components.services))
        components.add(ViewsComponent(components.services))
        text = TextComponent(components.services)
        components.add(text)
        components.add(VoiceComponent(components.services))
        dub = DubComponent(components.services)
        components.add(dub)
        # A line's audio is one of dozens: lists of them skip the per-product estimate.
        products.quiet_slots.add(LINE_AUDIO_SLOT)
        episodes = EpisodeService(db, products, invalidation)
        budget.episode_budget = episodes.budget
        runs = RunService(components, products, jobs, bus, budget)
        novel.after_import = runs.ensure_series_products

        async def estimate(product: Product) -> float | None:
            _, est = await runs.describe(product)
            return est.cost_usd if est is not None and est.where == "api" and est.cost_usd else None

        bible = BibleService(db, products, novel)
        suggestions = SuggestionService(db, products, novel, enrich)
        script_svc = ScriptService(db, products, script)
        assets = AssetService(
            db, products, runs, bus=bus, store=store, invalidation=invalidation, text=text
        )
        dub_service = DubService(db, products, runs, invalidation, dub)
        impact = ImpactService(db, products, invalidation, estimate)
        gates = GateService(db, bus, products, invalidation)
        cascade = CascadeService(db, bus, products, invalidation, runs, gates)
        impact.cascade = cascade
        register_kinds(
            impact,
            novel=novel,
            bible=bible,
            suggestions=suggestions,
            episodes=episodes,
            script=script_svc,
        )
        assets.register(impact, gates, episodes)
        state = cls(
            db=db,
            bus=bus,
            jobs=jobs,
            store=store,
            registry=registry,
            router=router,
            setup=setup,
            products=products,
            components=components,
            runs=runs,
            budget=budget,
            novel=novel,
            bible=bible,
            suggestions=suggestions,
            episodes=episodes,
            script=script_svc,
            assets=assets,
            dub=dub_service,
            gates=gates,
            impact=impact,
            cascade=cascade,
        )

        def openai_compat(spec: ModelSpec) -> OpenAICompatAdapter:
            return OpenAICompatAdapter(
                spec, get_key=secrets.get_secret, transport=state.http_transport
            )

        registry.add_factory(lambda spec: spec.kind == "llm" and bool(spec.base_url), openai_compat)

        from drama_series_agent.api.handlers import register_handlers

        register_handlers(state)
        if registry.mock:
            from drama_series_agent.studio.demo import seed_demo

            await seed_demo(db, novel=novel, products=products, compiler=compiler, gates=gates)
        await runs.ensure_all_series_products()
        return state

    async def run(self) -> None:
        """Start background work (the job dispatcher, which first re-queues interrupted jobs) and
        pick up a 确认并同步 a stop interrupted between two steps."""
        await self.jobs.start()
        await self.cascade.resume()

    async def stop(self) -> None:
        await self.jobs.stop()
        await self.db.dispose()


def get_state(request: Request) -> StudioState:
    state: StudioState = request.app.state.studio
    return state
