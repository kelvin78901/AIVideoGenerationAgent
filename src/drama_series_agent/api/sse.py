"""``GET /api/v1/events``: server-sent events with ``Last-Event-ID`` replay."""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import StreamingResponse

from drama_series_agent.api.state import StudioState, get_state
from drama_series_agent.core.events import BusEvent, EventBus

HEARTBEAT_S = 15.0
RETRY_MS = 3000

router = APIRouter()


def format_event(ev: BusEvent) -> str:
    data = json.dumps(ev.data, ensure_ascii=False, separators=(",", ":"))
    return f"id: {ev.id}\nevent: {ev.type}\ndata: {data}\n\n"


async def event_stream(
    bus: EventBus,
    after_id: int | None,
    is_disconnected: Callable[[], Awaitable[bool]],
    heartbeat_s: float = HEARTBEAT_S,
) -> AsyncIterator[str]:
    yield f"retry: {RETRY_MS}\n\n"
    stream = bus.stream(after_id)
    pending: asyncio.Task[BusEvent] | None = None
    try:
        while not await is_disconnected():
            if pending is None:
                pending = asyncio.ensure_future(anext(stream))
            done, _ = await asyncio.wait({pending}, timeout=heartbeat_s)
            if not done:
                yield ": ping\n\n"
                continue
            ev = pending.result()
            pending = None
            yield format_event(ev)
    finally:
        if pending is not None:
            pending.cancel()
            # Let the cancelled anext() finish before closing the generator it is running.
            with contextlib.suppress(asyncio.CancelledError, StopAsyncIteration):
                await pending
        await stream.aclose()


def _parse_id(value: str | None) -> int | None:
    if value is None or value.strip() == "":
        return None
    try:
        return max(int(value), 0)
    except ValueError:
        return None


@router.get("/events")
async def events(
    request: Request,
    state: Annotated[StudioState, Depends(get_state)],
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
    after: Annotated[str | None, Query(description="Replay events after this id")] = None,
) -> StreamingResponse:
    after_id = _parse_id(last_event_id) if last_event_id is not None else _parse_id(after)
    return StreamingResponse(
        event_stream(state.bus, after_id, request.is_disconnected),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
