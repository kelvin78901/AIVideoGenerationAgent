"""Snapshots of the user's own ComfyUI, taken with ComfyUI-Manager (SPEC 6.4.1).

``ManagerSnapshots`` talks to ComfyUI-Manager 4's HTTP API on the running ComfyUI, as found
in comfyui_manager 4.2.2 (``glob/manager_server.py``):

- ``GET  /v2/snapshot/getlist`` → ``{"items": [name, …]}``, newest first;
- ``POST /v2/snapshot/save`` (no body: form content types are refused) → 200, no name, so the
  new name is the one ``getlist`` gained;
- ``POST /v2/snapshot/restore?target=<name>`` → 200 once the restore is *scheduled*: Manager
  applies it the next time ComfyUI starts. 403 when Manager's security level forbids it.

The snapshot holds ComfyUI's commit, every node pack's commit or version and the pip packages.
``FakeSnapshots`` stands in on Mock's sample machines and in tests.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, Protocol

import httpx

# not_running: no ComfyUI answers; no_manager: it has no Manager 4 API (none, or an older one);
# forbidden: Manager's security level does not allow it; restart: Manager was just installed and
# only loads when ComfyUI restarts; failed: anything else.
SnapshotFailure = Literal["not_running", "no_manager", "forbidden", "restart", "failed"]


class SnapshotError(Exception):
    def __init__(self, reason: SnapshotFailure) -> None:
        super().__init__(reason)
        self.reason: SnapshotFailure = reason


class Snapshots(Protocol):
    async def save(self) -> str:
        """Take a snapshot now; returns its name in ComfyUI-Manager."""
        ...

    async def restore(self, name: str) -> None:
        """Schedule ``name`` to be restored the next time ComfyUI starts."""
        ...


class ManagerSnapshots:
    def __init__(self, url: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.url = url.rstrip("/")
        self._transport = transport

    async def _request(
        self, method: str, path: str, params: dict[str, str] | None = None
    ) -> httpx.Response:
        try:
            async with httpx.AsyncClient(
                timeout=30, trust_env=False, transport=self._transport
            ) as client:
                res = await client.request(method, f"{self.url}{path}", params=params)
        except httpx.HTTPError:
            raise SnapshotError("not_running") from None
        if res.status_code == 404:
            raise SnapshotError("no_manager")
        if res.status_code == 403:
            raise SnapshotError("forbidden")
        if res.status_code != 200:
            raise SnapshotError("failed")
        return res

    async def _names(self) -> list[str]:
        res = await self._request("GET", "/v2/snapshot/getlist")
        try:
            items = res.json().get("items")
        except ValueError:
            raise SnapshotError("failed") from None
        return [str(x) for x in items] if isinstance(items, list) else []

    async def save(self) -> str:
        before = set(await self._names())
        await self._request("POST", "/v2/snapshot/save")
        new = [n for n in await self._names() if n not in before]
        if not new:
            raise SnapshotError("failed")
        return max(new)  # names start with a timestamp

    async def restore(self, name: str) -> None:
        await self._request("POST", "/v2/snapshot/restore", params={"target": name})


class FakeSnapshots:
    """Remembers nothing; names look like Manager's. ``fail`` makes every call fail."""

    def __init__(self, fail: SnapshotFailure | None = None) -> None:
        self.fail = fail
        self.saved: list[str] = []
        self.restored: list[str] = []

    async def save(self) -> str:
        if self.fail:
            raise SnapshotError(self.fail)
        name = f"{datetime.now(UTC):%Y-%m-%d_%H-%M-%S}_snapshot"
        while name in self.saved:
            name += "_"
        self.saved.append(name)
        return name

    async def restore(self, name: str) -> None:
        if self.fail:
            raise SnapshotError(self.fail)
        self.restored.append(name)
