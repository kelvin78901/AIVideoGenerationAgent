"""Long provider jobs (video): submit once, then ask how it is going with exponential backoff
(SPEC 6.3: "长任务用厂商的异步任务接口轮询，轮询间隔指数退避").

``poll`` calls ``check`` until it answers something other than ``None``. The waits grow from
``first_s`` by ``factor`` up to ``max_s``; the router's timeout bounds the whole call.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

import httpx

from drama_series_agent.media.video import VideoError, probe
from drama_series_agent.modelhub.adapters.base import ModelError, OutputFile
from drama_series_agent.modelhub.adapters.http import send

# A take may be this much shorter than asked.
SHORT_BY_S = 0.5


def backoff(first_s: float, factor: float, max_s: float) -> Callable[[int], float]:
    def wait(attempt: int) -> float:
        return float(min(max_s, first_s * factor**attempt))

    return wait


async def poll[T](
    check: Callable[[], Awaitable[T | None]],
    *,
    first_s: float,
    factor: float = 1.5,
    max_s: float = 30.0,
) -> T:
    wait = backoff(first_s, factor, max_s)
    attempt = 0
    while True:
        await asyncio.sleep(wait(attempt))
        answer = await check()
        if answer is not None:
            return answer
        attempt += 1


async def download(
    url: str,
    *,
    transport: httpx.AsyncBaseTransport | None,
    timeout_s: float,
    max_retries: int,
    backoff_s: float,
) -> bytes:
    """A finished file from the provider's (signed, short-lived) URL; no key goes with it."""
    async with httpx.AsyncClient(
        timeout=timeout_s, transport=transport, follow_redirects=True
    ) as client:
        resp = await send(client, "GET", url, max_retries=max_retries, backoff_s=backoff_s)
    if not resp.content:
        raise ModelError("no_video", "empty download")
    return resp.content


async def video_file(data: bytes, asked_s: float, who: str) -> OutputFile:
    """A finished (paid for) video, probed: unreadable is ``invalid_response``, much shorter
    than asked ``video_too_short``; both billed."""
    try:
        info = await probe(data)
    except VideoError as exc:
        raise ModelError("invalid_response", f"{who}: {exc}", billed=True) from exc
    if info.duration_s < asked_s - SHORT_BY_S:
        raise ModelError(
            "video_too_short", f"{who}: {info.duration_s:.2f}s, asked {asked_s}s", billed=True
        )
    return OutputFile(
        role="video",
        mime="video/mp4",
        data=data,
        w=info.w,
        h=info.h,
        duration_s=round(info.duration_s, 3),
    )
