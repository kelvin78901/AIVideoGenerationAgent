"""The VRAM lease (hard rule 8): one lock for the whole process, whatever queue a job is on.

A local model that needs the GPU holds the lease for its call. Whoever used the GPU last stays
resident (a TTS worker keeps its model loaded, ComfyUI keeps its weights) until someone else
asks: then the previous owner is told to let go first (stop the worker, ComfyUI ``/free``).
MiniMax falling back to IndexTTS takes the lease like any GPU job, so two models never load
at once. Waiting has no timeout of its own: the router's local timeout covers the wait, and a
call that times out falls back to the API.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from loguru import logger

Release = Callable[[], Awaitable[None]]


class VramLease:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._resident: str | None = None
        self._release: dict[str, Release] = {}

    @property
    def resident(self) -> str | None:
        return self._resident

    def register(self, owner: str, release: Release) -> None:
        """How ``owner`` frees the GPU when someone else needs it."""
        self._release[owner] = release

    def forget(self, owner: str) -> None:
        """``owner`` let go on its own (its worker exited)."""
        if self._resident == owner:
            self._resident = None

    @asynccontextmanager
    async def hold(self, owner: str) -> AsyncIterator[None]:
        async with self._lock:
            previous = self._resident
            if previous is not None and previous != owner:
                release = self._release.get(previous)
                if release is not None:
                    try:
                        await release()
                    except Exception as exc:  # the next model may still fit; say so and go on
                        logger.warning("vram: {} did not let go: {}", previous, exc)
                self._resident = None
            self._resident = owner
            yield


_shared = VramLease()


def shared_lease() -> VramLease:
    return _shared
