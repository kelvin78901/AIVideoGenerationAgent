"""End-to-end helpers: a real backend process on a free port, with its own DRAMA_HOME."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class Backend:
    def __init__(self, home: Path) -> None:
        self.home = home
        self.port = _free_port()
        self.base = f"http://127.0.0.1:{self.port}/api/v1"
        self.proc: subprocess.Popen[bytes] | None = None

    def start(self, **extra_env: str) -> None:
        env = {**os.environ, "DRAMA_HOME": str(self.home), "DRAMA_MOCK": "1", **extra_env}
        cmd = [sys.executable, "-m", "drama_series_agent.studio_cli", "dev", "--port"]
        self.proc = subprocess.Popen(
            [*cmd, str(self.port)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                if httpx.get(f"{self.base}/health", timeout=1).status_code == 200:
                    return
            except httpx.HTTPError:
                time.sleep(0.2)
        raise AssertionError("backend did not start")

    def kill(self) -> None:
        """Hard kill, no graceful shutdown: what a crash or a closed terminal looks like."""
        assert self.proc is not None
        self.proc.kill()
        self.proc.wait(timeout=10)
        self.proc = None

    def jobs(self) -> dict[str, dict[str, Any]]:
        rows: list[dict[str, Any]] = httpx.get(f"{self.base}/jobs", timeout=5).json()
        return {r["id"]: r for r in rows}


@pytest.fixture
def backend(tmp_path: Path) -> Iterator[Backend]:
    b = Backend(tmp_path / "home")
    yield b
    if b.proc is not None:
        b.kill()
