"""What the library asks the user's ComfyUI: its workflow list, a workflow file, ``/object_info``
and ComfyUI-Manager's node map (which node pack provides which node class).

``HttpComfy`` talks to the running ComfyUI (the address of the last scan): the list and the
files come from its user-data API (``/api/userdata?dir=workflows``), which works for every kind
of install (folder, portable, Desktop). ``DemoComfy`` is Mock's sample machine: a few files
and the ``/object_info`` of the nodes they use, shipped in ``wflib/demo/``.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote

import httpx

DEMO_DIR = Path(__file__).parent / "demo"


class ComfyUnavailable(Exception):
    """ComfyUI is not running (or does not answer): nothing to list, read or ask."""


@dataclass(frozen=True)
class ComfyFile:
    path: str  # under ComfyUI's ``workflows`` folder, with ``/``
    modified_at: datetime


class ComfyAccess(Protocol):
    async def files(self) -> list[ComfyFile]: ...

    async def read(self, path: str) -> dict[str, Any]: ...

    async def object_info(self) -> dict[str, Any]: ...

    async def node_map(self) -> dict[str, Any]: ...

    @property
    def needs_restart(self) -> bool:
        """New node packs load only when ComfyUI restarts (the sample machine: at once)."""
        ...


class HttpComfy:
    needs_restart = True

    def __init__(
        self,
        url: Callable[[], Awaitable[str]],
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._url = url
        self._transport = transport

    async def _get(self, path: str, timeout_s: float = 15) -> Any:
        base = (await self._url()).rstrip("/")
        try:
            async with httpx.AsyncClient(transport=self._transport, timeout=timeout_s) as client:
                res = await client.get(f"{base}{path}")
        except httpx.HTTPError as exc:
            raise ComfyUnavailable(str(exc)) from None
        if res.status_code != 200:
            raise ComfyUnavailable(f"{path}: HTTP {res.status_code}")
        return res.json()

    async def files(self) -> list[ComfyFile]:
        rows = await self._get("/api/userdata?dir=workflows&recurse=true&full_info=true")
        out = []
        for row in rows if isinstance(rows, list) else []:
            if isinstance(row, dict) and str(row.get("path", "")).endswith(".json"):
                modified = float(row.get("modified") or 0)
                out.append(
                    ComfyFile(
                        path=str(row["path"]).replace("\\", "/"),
                        modified_at=datetime.fromtimestamp(modified, UTC),
                    )
                )
        return sorted(out, key=lambda f: f.modified_at, reverse=True)

    async def read(self, path: str) -> dict[str, Any]:
        data = await self._get("/api/userdata/" + quote(f"workflows/{path}", safe=""))
        if not isinstance(data, dict):
            raise ComfyUnavailable(f"{path}: not a workflow")
        return data

    async def object_info(self) -> dict[str, Any]:
        data = await self._get("/object_info", timeout_s=30)
        return data if isinstance(data, dict) else {}

    async def node_map(self) -> dict[str, Any]:
        """ComfyUI-Manager's ``extension-node-map`` (repository → [classes, info]); empty
        without Manager (version 4 serves it under ``/v2``, older ones without)."""
        for path in ("/v2/customnode/getmappings?mode=cache", "/customnode/getmappings?mode=cache"):
            try:
                data = await self._get(path, timeout_s=30)
            except ComfyUnavailable:
                continue
            if isinstance(data, dict):
                return data
        return {}


class DemoComfy:
    """Mock's sample machine: ``wflib/demo/workflows/``, ``object_info.json`` and
    ``node_map.json``. A node pack it "installs" adds its classes at once (no restart)."""

    needs_restart = False

    def __init__(self, root: Path = DEMO_DIR) -> None:
        self._root = root
        self._added: dict[str, Any] = {}

    def add_classes(self, classes: list[str]) -> None:
        for cls in classes:
            self._added[cls] = {"display_name": cls, "input": {"required": {}}}

    async def files(self) -> list[ComfyFile]:
        index = json.loads((self._root / "files.json").read_text(encoding="utf-8"))
        return [
            ComfyFile(path=row["path"], modified_at=datetime.fromisoformat(row["modified_at"]))
            for row in index
        ]

    async def read(self, path: str) -> dict[str, Any]:
        file = self._root / "workflows" / path
        if not file.is_file():
            raise ComfyUnavailable(f"{path}: not found")
        data = json.loads(file.read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        return data

    async def object_info(self) -> dict[str, Any]:
        data = json.loads((self._root / "object_info.json").read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        return {**data, **self._added}

    async def node_map(self) -> dict[str, Any]:
        data = json.loads((self._root / "node_map.json").read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        return data
