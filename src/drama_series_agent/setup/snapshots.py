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

A rollback is only scheduled, and Manager can stop halfway (it did on Kelvin's machine), so the
first scan after it compares the ComfyUI it finds with the one the snapshot was taken of
(``restore_check``).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol

import httpx

from drama_series_agent.setup.comfy import ComfyEnvInfo, NodePack
from drama_series_agent.setup.manifest import Message

# not_running: no ComfyUI answers; no_manager: it has no Manager 4 API (none, or an older one);
# forbidden: Manager's security level does not allow it; restart: Manager was just installed and
# only loads when ComfyUI restarts; failed: anything else.
SnapshotFailure = Literal["not_running", "no_manager", "forbidden", "restart", "failed"]


RestoreState = Literal["pending", "done", "incomplete", "unchecked"]


def _rev(commit: str | None, version: str | None) -> str:
    return commit[:7] if commit else version or "?"


def env_diff(now: ComfyEnvInfo, then: ComfyEnvInfo) -> list[Message]:
    """What a rollback to ``then`` restores and ``now`` does not match: ComfyUI's commit (else
    version) and each node pack's. Python and PyTorch are left out: Manager does not downgrade
    pip packages."""
    out: list[Message] = []
    a = _rev(now.comfyui_commit if then.comfyui_commit else None, now.comfyui_version)
    b = _rev(then.comfyui_commit, then.comfyui_version)
    if a != b:
        out.append(Message(code="comfyui", params={"now": a, "then": b}))

    def packs(env: ComfyEnvInfo) -> dict[str, NodePack]:
        return {p.name: p for p in env.node_packs}

    mine, theirs = packs(now), packs(then)
    for name in sorted(mine.keys() - theirs.keys()):
        out.append(Message(code="pack_extra", params={"name": name}))
    for name in sorted(theirs.keys() - mine.keys()):
        out.append(Message(code="pack_missing", params={"name": name}))
    for name in sorted(mine.keys() & theirs.keys()):
        x, y = mine[name], theirs[name]
        a, b = _rev(x.commit, x.version), _rev(y.commit, y.version)
        if a != b:
            out.append(Message(code="pack_version", params={"name": name, "now": a, "then": b}))
    return out


def restore_check(
    now_hash: str, now: ComfyEnvInfo, from_hash: str | None, then: ComfyEnvInfo
) -> tuple[RestoreState, list[Message]]:
    """A pending rollback, seen by a scan: back at the snapshot → done; unchanged since the
    request → still pending (ComfyUI not restarted yet); changed but not back → incomplete."""
    diff = env_diff(now, then)
    if not diff:
        return "done", []
    if from_hash is not None and now_hash == from_hash:
        return "pending", []
    return "incomplete", diff


def prepare_restore(comfy_root: str) -> None:
    """Create ``custom_nodes/.disabled`` before ComfyUI-Manager restores a snapshot.

    Manager disables node packs the snapshot does not have with ``shutil.move`` into that
    folder. When it does not exist yet, the rename fails and Python falls back to copy + delete,
    and on Windows the delete stops at git's read-only pack files: the restore aborts halfway,
    leaving a copy behind (comfyui_manager 4.2.2, seen on Kelvin's machine 2026-10-18). With the
    folder there, the move is a plain rename.
    """
    Path(comfy_root, "custom_nodes", ".disabled").mkdir(parents=True, exist_ok=True)


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
