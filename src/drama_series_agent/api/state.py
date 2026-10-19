"""Process-wide services owned by the FastAPI app (created in the lifespan, not at import)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

import httpx
from fastapi import Request

from drama_series_agent.core import secrets
from drama_series_agent.core.config import get_config
from drama_series_agent.core.db import Database, migrate
from drama_series_agent.core.events import EventBus
from drama_series_agent.core.jobs import JobQueue
from drama_series_agent.core.paths import database_path
from drama_series_agent.core.storage import BlobStore
from drama_series_agent.modelhub.adapters.base import ModelSpec
from drama_series_agent.modelhub.adapters.openai_compat import OpenAICompatAdapter
from drama_series_agent.modelhub.budget import Budget, BudgetGuardImpl
from drama_series_agent.modelhub.registry import Registry
from drama_series_agent.modelhub.router import Router
from drama_series_agent.novel.service import NOVEL_SLOT, NovelService, novel_slicer
from drama_series_agent.pipeline.component import ComponentRegistry, Services
from drama_series_agent.pipeline.invalidation import Invalidation
from drama_series_agent.pipeline.products import ProductService
from drama_series_agent.pipeline.runs import RunService
from drama_series_agent.prompts.compiler import PromptCompiler
from drama_series_agent.setup.service import SetupService


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
        products = ProductService(db, bus, invalidation)
        components = ComponentRegistry(
            Services(
                db=db,
                router=router,
                registry=registry,
                compiler=PromptCompiler(),
                store=store,
                invalidation=invalidation,
            )
        )
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
            runs=RunService(components, products, jobs, bus, budget),
            budget=budget,
            novel=NovelService(db, store, products),
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

            await seed_demo(db, novel=state.novel)
        return state

    async def run(self) -> None:
        """Start background work (the job dispatcher, which first re-queues interrupted jobs)."""
        await self.jobs.start()

    async def stop(self) -> None:
        await self.jobs.stop()
        await self.db.dispose()


def get_state(request: Request) -> StudioState:
    state: StudioState = request.app.state.studio
    return state
