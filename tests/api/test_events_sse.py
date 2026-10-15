"""SSE over a real uvicorn server (TestClient buffers streaming bodies)."""

from __future__ import annotations

import asyncio
import socket
from collections.abc import AsyncIterator

import httpx
import pytest
import uvicorn

from drama_series_agent.api.app import create_app
from drama_series_agent.api.state import StudioState


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture
async def server() -> AsyncIterator[tuple[str, StudioState]]:
    app = create_app()
    port = _free_port()
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    task = asyncio.create_task(srv.serve())
    for _ in range(250):
        if srv.started:
            break
        await asyncio.sleep(0.02)
    assert srv.started
    yield f"http://127.0.0.1:{port}", app.state.studio
    srv.should_exit = True
    await asyncio.wait_for(task, 10)


async def _read_events(resp: httpx.Response, n: int) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []
    current: dict[str, str] = {}
    async for line in resp.aiter_lines():
        if line == "":
            if "event" in current:
                events.append(current)
                if len(events) == n:
                    return events
            current = {}
        elif not line.startswith(":"):
            key, _, value = line.partition(": ")
            current[key] = value
    return events


async def test_sse_live_and_last_event_id_replay(server: tuple[str, StudioState]) -> None:
    base, state = server
    first = await state.bus.publish("toast", {"n": 1})
    await state.bus.publish("toast", {"n": 2})
    headers = {"Last-Event-ID": str(first.id)}
    async with (
        httpx.AsyncClient(timeout=5) as client,
        client.stream("GET", f"{base}/api/v1/events", headers=headers) as resp,
    ):
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        reader = asyncio.ensure_future(_read_events(resp, 2))
        await asyncio.sleep(0.1)
        await state.bus.publish("job.updated", {"n": 3})
        got = await asyncio.wait_for(reader, 5)
    assert [e["event"] for e in got] == ["toast", "job.updated"]
    assert got[0]["data"] == '{"n":2}'
    assert int(got[1]["id"]) > int(got[0]["id"])


async def test_sse_bad_last_event_id_means_live_only(server: tuple[str, StudioState]) -> None:
    base, state = server
    await state.bus.publish("toast", {"n": "old"})
    headers = {"Last-Event-ID": "abc"}
    async with (
        httpx.AsyncClient(timeout=5) as client,
        client.stream("GET", f"{base}/api/v1/events", headers=headers) as resp,
    ):
        reader = asyncio.ensure_future(_read_events(resp, 1))
        await asyncio.sleep(0.1)
        await state.bus.publish("toast", {"n": "new"})
        got = await asyncio.wait_for(reader, 5)
    assert got[0]["data"] == '{"n":"new"}'
