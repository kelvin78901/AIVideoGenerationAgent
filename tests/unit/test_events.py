from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from drama_series_agent.api.sse import event_stream, format_event
from drama_series_agent.core.db import Database
from drama_series_agent.core.events import BusEvent, EventBus, EventType


async def _take(it: AsyncIterator[BusEvent], n: int, limit_s: float = 2.0) -> list[BusEvent]:
    out: list[BusEvent] = []

    async def run() -> None:
        while len(out) < n:
            out.append(await anext(it))

    await asyncio.wait_for(run(), limit_s)
    return out


async def test_publish_persists_with_increasing_ids(studio_db: Database) -> None:
    bus = EventBus(studio_db)
    a = await bus.publish(EventType.JOB_UPDATED, {"id": "j1", "state": "queued"})
    b = await bus.publish(EventType.TOAST, {"code": "ok"})
    assert b.id > a.id
    replayed = await bus.replay(0)
    assert [e.type for e in replayed] == ["job.updated", "toast"]
    assert replayed[0].data == {"id": "j1", "state": "queued"}
    assert await bus.last_id() == b.id


async def test_stream_replays_then_goes_live(studio_db: Database) -> None:
    bus = EventBus(studio_db)
    first = await bus.publish("toast", {"n": 1})
    await bus.publish("toast", {"n": 2})
    stream = bus.stream(after_id=first.id)
    reader = asyncio.ensure_future(_take(stream, 2))
    await asyncio.sleep(0.05)
    await bus.publish("toast", {"n": 3})
    got = await reader
    assert [e.data["n"] for e in got] == [2, 3]
    await stream.aclose()
    assert bus.subscriber_count == 0


async def test_stream_without_id_only_gets_new_events(studio_db: Database) -> None:
    bus = EventBus(studio_db)
    await bus.publish("toast", {"n": "old"})
    stream = bus.stream(after_id=None)
    reader = asyncio.ensure_future(_take(stream, 1))
    await asyncio.sleep(0.05)
    await bus.publish("toast", {"n": "new"})
    assert [e.data["n"] for e in await reader] == ["new"]
    await stream.aclose()


async def test_multiple_subscribers_each_get_everything(studio_db: Database) -> None:
    bus = EventBus(studio_db)
    s1, s2 = bus.stream(None), bus.stream(None)
    r1 = asyncio.ensure_future(_take(s1, 3))
    r2 = asyncio.ensure_future(_take(s2, 3))
    await asyncio.sleep(0.05)
    for i in range(3):
        await bus.publish("toast", {"n": i})
    assert [e.data["n"] for e in await r1] == [0, 1, 2]
    assert [e.data["n"] for e in await r2] == [0, 1, 2]
    await s1.aclose()
    await s2.aclose()


async def test_lagging_subscriber_catches_up_from_db(studio_db: Database) -> None:
    bus = EventBus(studio_db)
    stream = bus.stream(None)
    reader = asyncio.ensure_future(_take(stream, 1))
    await asyncio.sleep(0.05)
    await bus.publish("toast", {"n": 0})
    await reader
    # Fill the live queue while nobody reads, then publish more: they overflow.
    sub = next(iter(bus._subscribers))
    for _ in range(sub.queue.maxsize):
        sub.queue.put_nowait(BusEvent(id=0, type="noise", data={}))
    for i in range(1, 4):
        await bus.publish("toast", {"n": i})
    assert sub.lagged
    got = await _take(stream, 3)
    assert [e.data["n"] for e in got] == [1, 2, 3]
    await stream.aclose()


async def test_pruning_keeps_recent_events(studio_db: Database) -> None:
    bus = EventBus(studio_db, keep=5, prune_every=10)
    for i in range(10):
        await bus.publish("toast", {"n": i})
    rows = await bus.replay(0)
    assert [e.data["n"] for e in rows] == [5, 6, 7, 8, 9]


async def test_event_stream_formats_and_heartbeats(studio_db: Database) -> None:
    bus = EventBus(studio_db)
    ev = await bus.publish("job.updated", {"state": "运行中"})
    disconnected = False

    async def is_disconnected() -> bool:
        return disconnected

    gen = event_stream(bus, ev.id - 1, is_disconnected, heartbeat_s=0.05)
    assert (await anext(gen)).startswith("retry:")
    assert await anext(gen) == format_event(ev)
    assert "运行中" in format_event(ev)
    assert await anext(gen) == ": ping\n\n"
    disconnected = True
    rest = [chunk async for chunk in gen]
    assert rest in ([], [": ping\n\n"])
    assert bus.subscriber_count == 0
