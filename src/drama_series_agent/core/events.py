"""Event bus: every event is persisted in the ``event`` table, then fanned out to subscribers.

Persisting first gives each event an increasing id, which SSE clients send back as
``Last-Event-ID`` to replay what they missed (SPEC 9).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import anyio
from sqlmodel import col, delete, select

from drama_series_agent.core.db import Database
from drama_series_agent.core.models_db import Event


class EventType(StrEnum):
    JOB_UPDATED = "job.updated"
    PRODUCT_UPDATED = "product.updated"
    VERSION_CREATED = "version.created"
    COST_UPDATED = "cost.updated"
    GATE_UPDATED = "gate.updated"
    SYNC_UPDATED = "sync.updated"
    SETUP_PROGRESS = "setup.progress"
    SETUP_LOG = "setup.log"
    TOAST = "toast"


@dataclass(frozen=True)
class BusEvent:
    id: int
    type: str
    data: dict[str, Any]


@dataclass(eq=False)  # identity hash: subscribers live in a set
class Subscriber:
    queue: asyncio.Queue[BusEvent] = field(default_factory=lambda: asyncio.Queue(maxsize=1000))
    # Set when the queue overflowed; the reader must replay from the database to catch up.
    lagged: bool = False


class EventBus:
    def __init__(self, db: Database, *, keep: int = 5000, prune_every: int = 200) -> None:
        self._db = db
        self._keep = keep
        self._prune_every = prune_every
        self._published = 0
        self._subscribers: set[Subscriber] = set()
        self._lock = asyncio.Lock()

    async def publish(self, type_: str, data: dict[str, Any] | None = None) -> BusEvent:
        payload = data or {}
        # The lock keeps id order == delivery order across concurrent publishers.
        async with self._lock:
            async with self._db.session() as session:
                row = Event(type=str(type_), data_json=payload)
                session.add(row)
                await session.commit()
                assert row.id is not None
                event = BusEvent(id=row.id, type=row.type, data=payload)
                self._published += 1
                if self._published % self._prune_every == 0:
                    await session.exec(delete(Event).where(col(Event.id) <= event.id - self._keep))
                    await session.commit()
            for sub in list(self._subscribers):
                try:
                    sub.queue.put_nowait(event)
                except asyncio.QueueFull:
                    sub.lagged = True
        return event

    # Both reads run inside SSE streams, which Starlette cancels (anyio cancel scope) when the
    # browser disconnects, e.g. on every page navigation. Cancelling an aiosqlite query midway
    # left a broken connection in the pool and the next request failed with "no active
    # connection" (HTTP 500), so the short reads are shielded and finish first.

    async def replay(self, after_id: int, limit: int = 1000) -> list[BusEvent]:
        with anyio.CancelScope(shield=True):
            async with self._db.session() as session:
                rows = (
                    await session.exec(
                        select(Event)
                        .where(col(Event.id) > after_id)
                        .order_by(col(Event.id))
                        .limit(limit)
                    )
                ).all()
        return [BusEvent(id=r.id or 0, type=r.type, data=r.data_json) for r in rows]

    async def last_id(self) -> int:
        with anyio.CancelScope(shield=True):
            async with self._db.session() as session:
                row = (
                    await session.exec(select(Event).order_by(col(Event.id).desc()).limit(1))
                ).first()
        return row.id if row and row.id else 0

    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[Subscriber]:
        sub = Subscriber()
        self._subscribers.add(sub)
        try:
            yield sub
        finally:
            self._subscribers.discard(sub)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    async def stream(self, after_id: int | None) -> AsyncGenerator[BusEvent]:
        """Yield events after ``after_id`` (replayed from the DB), then live ones, in id order.

        ``after_id=None`` means "only new events".
        """
        # Read the starting point before subscribing; the replay below covers the gap.
        last = await self.last_id() if after_id is None else after_id
        async with self.subscribe() as sub:
            sub.lagged = True  # first iteration replays everything after `last`
            while True:
                if sub.lagged:
                    sub.lagged = False
                    while True:
                        batch = await self.replay(last)
                        if not batch:
                            break
                        for ev in batch:
                            last = ev.id
                            yield ev
                ev = await sub.queue.get()
                if ev.id <= last:
                    continue  # already delivered by the replay
                last = ev.id
                yield ev
