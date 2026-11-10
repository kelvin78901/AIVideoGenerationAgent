"""Process-wide services owned by the FastAPI app (created in the lifespan, not at import)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

import httpx
from fastapi import Request
from sqlmodel import select

from drama_series_agent.assets import service as assets_service
from drama_series_agent.assets.dub import DubService
from drama_series_agent.assets.service import AssetService
from drama_series_agent.bible.service import BIBLE_SLOT, BibleService, bible_slicer, materialize
from drama_series_agent.core import secrets
from drama_series_agent.core.config import (
    Accounts,
    AccountState,
    Library,
    get_config,
    resolve,
    set_accounts,
    set_library,
)
from drama_series_agent.core.config import ModelSetting as ModelSetting_
from drama_series_agent.core.db import Database, migrate
from drama_series_agent.core.events import EventBus
from drama_series_agent.core.jobs import JobQueue
from drama_series_agent.core.models_db import ModelSetting, Product, ProviderAccount
from drama_series_agent.core.overrides import load_defaults, load_overrides
from drama_series_agent.core.paths import database_path
from drama_series_agent.core.storage import BlobStore
from drama_series_agent.episodes import service as episodes_service
from drama_series_agent.episodes.service import EPISODES_SLOT, EpisodeService
from drama_series_agent.modelhub.adapters.base import ModelAdapter, ModelSpec
from drama_series_agent.modelhub.adapters.comfyui import ComfyUIAdapter
from drama_series_agent.modelhub.adapters.local_python import LocalPythonAdapter
from drama_series_agent.modelhub.adapters.openai_compat import OpenAICompatAdapter
from drama_series_agent.modelhub.budget import Budget, BudgetGuardImpl
from drama_series_agent.modelhub.media_adapters import has_media_adapter, media_adapter
from drama_series_agent.modelhub.registry import Registry
from drama_series_agent.modelhub.router import Router
from drama_series_agent.modelhub.workflows import has_workflow, spec_workflows_dir
from drama_series_agent.novel.service import NOVEL_SLOT, NovelService, novel_slicer
from drama_series_agent.pipeline.cascade import CascadeService
from drama_series_agent.pipeline.component import (
    ComponentRegistry,
    Services,
    reruns_in_cascade,
)
from drama_series_agent.pipeline.components.assets import ASSET_LIST_SLOT, AssetsComponent
from drama_series_agent.pipeline.components.dub import LINE_AUDIO_SLOT, DubComponent
from drama_series_agent.pipeline.components.enrich import EnrichComponent
from drama_series_agent.pipeline.components.extract import ExtractComponent
from drama_series_agent.pipeline.components.img import ImgComponent
from drama_series_agent.pipeline.components.kf import KfComponent, stale_aspect
from drama_series_agent.pipeline.components.plan import (
    SHOT_PLAN_SLOT,
    PlanComponent,
    asset_list_slicer,
    shot_plan_slicer,
)
from drama_series_agent.pipeline.components.script import ScriptComponent
from drama_series_agent.pipeline.components.split import SplitComponent
from drama_series_agent.pipeline.components.text import TextComponent
from drama_series_agent.pipeline.components.vid import VidComponent
from drama_series_agent.pipeline.components.views import ViewsComponent
from drama_series_agent.pipeline.components.voice import VoiceComponent
from drama_series_agent.pipeline.gates import GateService
from drama_series_agent.pipeline.impact import ImpactService, register_kinds
from drama_series_agent.pipeline.invalidation import Invalidation
from drama_series_agent.pipeline.products import ProductService
from drama_series_agent.pipeline.runs import RunService
from drama_series_agent.pipeline.timing import longest_take_s
from drama_series_agent.prompts.compiler import PromptCompiler
from drama_series_agent.script import service as script_service
from drama_series_agent.script.service import ScriptService
from drama_series_agent.setup.service import PROFILE_DEMO, SetupService
from drama_series_agent.shots import service as shots_service
from drama_series_agent.shots.service import KEYFRAME_SLOT, ShotService
from drama_series_agent.spec.compat import model_caps
from drama_series_agent.suggestions import service as suggestions_service
from drama_series_agent.suggestions.service import SUGGESTIONS_SLOT, SuggestionService
from drama_series_agent.wflib.comfy import ComfyAccess, DemoComfy, HttpComfy
from drama_series_agent.wflib.service import WorkflowLibrary


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
    shots: ShotService
    gates: GateService
    impact: ImpactService
    cascade: CascadeService
    workflows: WorkflowLibrary
    # Tests inject an httpx mock transport here; None means real network.
    http_transport: httpx.AsyncBaseTransport | None = None

    async def refresh_accounts(self) -> None:
        """A provider account or model setting changed: lay it over the config again and
        rebuild the API models (their address, key, prices; the writing models picked)."""
        set_accounts(await load_accounts(self.db))
        self.registry.reload(get_config())

    @classmethod
    async def start(cls, db_path: Path | None = None) -> StudioState:
        path = db_path or database_path()
        await asyncio.to_thread(migrate, path)
        db = Database(path)
        bus = EventBus(db)
        store = BlobStore()
        set_library(Library())  # a library left over from another app in this process (tests)
        set_accounts(await load_accounts(db))
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
        invalidation.slicer(ASSET_LIST_SLOT, asset_list_slicer)
        invalidation.slicer(SHOT_PLAN_SLOT, shot_plan_slicer)
        invalidation.check(KEYFRAME_SLOT, stale_aspect)
        products = ProductService(db, bus, invalidation)
        products.on_adopt(BIBLE_SLOT, materialize)
        products.on_adopt(SUGGESTIONS_SLOT, suggestions_service.materialize)
        products.on_adopt(EPISODES_SLOT, episodes_service.materialize)
        products.on_adopt(episodes_service.SCRIPT_SLOT, script_service.materialize)
        products.on_adopt(episodes_service.SCRIPT_SLOT, shots_service.ensure_plan)
        products.on_adopt(ASSET_LIST_SLOT, assets_service.materialize)
        products.on_adopt(SHOT_PLAN_SLOT, shots_service.materialize)
        products.on_adopt(KEYFRAME_SLOT, shots_service.lock_spec)
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
        components.add(PlanComponent(components.services))
        components.add(KfComponent(components.services))
        components.add(VidComponent(components.services))
        # A line's audio is one of dozens: lists of them skip the per-product estimate.
        products.quiet_slots.add(LINE_AUDIO_SLOT)
        episodes = EpisodeService(db, products, invalidation)
        budget.episode_budget = episodes.budget
        runs = RunService(components, products, jobs, bus, budget)
        novel.after_import = runs.ensure_series_products

        async def estimate(product: Product) -> float | None:
            """What 确认并同步 would pay for it: nothing for what a sync never reruns."""
            comp = components.get(product.component_id)
            if comp is None or not reruns_in_cascade(comp):
                return None
            _, est = await runs.describe(product)
            return est.cost_usd if est is not None and est.where == "api" and est.cost_usd else None

        bible = BibleService(db, products, novel)
        suggestions = SuggestionService(db, products, novel, enrich)
        script_svc = ScriptService(db, products, script)
        assets = AssetService(
            db, products, runs, bus=bus, store=store, invalidation=invalidation, text=text
        )
        dub_service = DubService(db, products, runs, invalidation, dub)

        async def longest_take() -> float | None:
            """The longest take on the video route this machine will take (SPEC 7.3)."""
            async with db.session() as session:
                overrides = await load_overrides(session)
                defaults = await load_defaults(session)
            cfg = get_config()
            route = resolve(
                "vid", overrides, config=cfg, caps=await setup.capabilities(), defaults=defaults
            )
            return longest_take_s(route.values, lambda key: model_caps(cfg, key))

        shots = ShotService(db, products, runs, invalidation, longest=longest_take)
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
        shots.register(gates, episodes, impact)

        demo_comfy = DemoComfy()  # one, so what it "installs" stays

        def comfy_access() -> ComfyAccess:
            if setup.profile_id == PROFILE_DEMO:
                return demo_comfy

            async def url() -> str:
                return (await setup.comfy_target()).url

            return HttpComfy(url, transport=state.http_transport)

        workflows = WorkflowLibrary(
            db, registry, comfy_access, setup=setup, jobs=jobs, router=router
        )
        await workflows.sync()
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
            shots=shots,
            gates=gates,
            impact=impact,
            cascade=cascade,
            workflows=workflows,
        )

        def openai_compat(spec: ModelSpec) -> OpenAICompatAdapter:
            return OpenAICompatAdapter(
                spec, get_key=secrets.get_secret, transport=state.http_transport
            )

        registry.add_factory(lambda spec: spec.kind == "llm" and bool(spec.base_url), openai_compat)

        def media(spec: ModelSpec) -> ModelAdapter:
            return media_adapter(
                spec, get_key=secrets.get_secret, store=state.store, transport=state.http_transport
            )

        registry.add_factory(has_media_adapter, media)

        def local_python(spec: ModelSpec) -> ModelAdapter:
            return LocalPythonAdapter(spec, paths=setup.runtime_paths)

        registry.add_factory(
            lambda spec: spec.where == "local" and spec.runtime == "python" and bool(spec.worker),
            local_python,
        )

        def comfyui(spec: ModelSpec) -> ModelAdapter:
            return ComfyUIAdapter(
                spec,
                target=setup.comfy_target,
                store=state.store,
                transport=state.http_transport,
                workflows_dir=spec_workflows_dir(spec),
            )

        registry.add_factory(
            lambda spec: (
                spec.where == "local"
                and spec.runtime == "comfyui"
                and has_workflow(spec.workflow, spec_workflows_dir(spec))
            ),
            comfyui,
        )

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
        await self.registry.aclose()  # local model workers exit with the app
        await self.db.dispose()
        set_library(Library())  # the config goes back to the factory files


def get_state(request: Request) -> StudioState:
    state: StudioState = request.app.state.studio
    return state


async def load_accounts(db: Database) -> Accounts:
    """The provider accounts and model settings as ``get_config()`` lays them over the factory
    config (``core/config.py:with_accounts``)."""
    async with db.session() as session:
        rows = (await session.exec(select(ProviderAccount))).all()
        settings = (await session.exec(select(ModelSetting))).all()
    providers = {
        r.provider_id: AccountState(
            site=r.site,
            base_url=r.base_url_override,
            listed=tuple((r.models_json or {}).get("ids") or ()) if r.models_json else None,
            enabled=tuple(r.enabled_json) if r.enabled_json is not None else None,
        )
        for r in rows
    }
    return Accounts(
        providers=providers,
        settings={
            m.model_key: ModelSetting_(model_id=m.model_id, price=m.price_json) for m in settings
        },
    )
