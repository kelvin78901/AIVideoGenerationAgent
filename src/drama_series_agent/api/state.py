"""Process-wide services owned by the FastAPI app (created in the lifespan, not at import)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from fastapi import Request

from drama_series_agent.core.config import get_config
from drama_series_agent.core.db import Database, migrate
from drama_series_agent.core.events import EventBus
from drama_series_agent.core.jobs import JobQueue
from drama_series_agent.core.paths import database_path
from drama_series_agent.core.storage import BlobStore
from drama_series_agent.modelhub.registry import Registry
from drama_series_agent.modelhub.router import Router


@dataclass
class StudioState:
    db: Database
    bus: EventBus
    jobs: JobQueue
    store: BlobStore
    registry: Registry
    router: Router

    @classmethod
    async def start(cls, db_path: Path | None = None) -> StudioState:
        path = db_path or database_path()
        await asyncio.to_thread(migrate, path)
        db = Database(path)
        bus = EventBus(db)
        store = BlobStore()
        registry = Registry.from_config(get_config())
        state = cls(
            db=db,
            bus=bus,
            jobs=JobQueue(db, bus),
            store=store,
            registry=registry,
            router=Router(db, bus, registry, store=store),
        )
        from drama_series_agent.api.handlers import register_handlers

        register_handlers(state)
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
