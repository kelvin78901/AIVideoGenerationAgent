"""Process-wide services owned by the FastAPI app (created in the lifespan, not at import)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from fastapi import Request

from drama_series_agent.core.db import Database, migrate
from drama_series_agent.core.events import EventBus
from drama_series_agent.core.paths import database_path


@dataclass
class StudioState:
    db: Database
    bus: EventBus

    @classmethod
    async def start(cls, db_path: Path | None = None) -> StudioState:
        path = db_path or database_path()
        await asyncio.to_thread(migrate, path)
        db = Database(path)
        return cls(db=db, bus=EventBus(db))

    async def stop(self) -> None:
        await self.db.dispose()


def get_state(request: Request) -> StudioState:
    state: StudioState = request.app.state.studio
    return state
