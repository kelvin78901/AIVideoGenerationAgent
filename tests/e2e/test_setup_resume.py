"""M1: kill the backend in the middle of a (simulated) install; after a restart it carries on."""

from __future__ import annotations

import sqlite3
import time
from collections import Counter
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import httpx
import pytest

if TYPE_CHECKING:
    from conftest import Backend  # tests/e2e/conftest.py

pytestmark = pytest.mark.e2e

HEADERS = {"X-Drama-Studio": "1"}


def _profile(backend: Backend) -> dict[str, Any]:
    p: dict[str, Any] = httpx.get(f"{backend.base}/setup/profile", timeout=5).json()
    return p


def _wait(backend: Backend, ok: Any, limit_s: float = 40) -> dict[str, Any]:
    deadline = time.monotonic() + limit_s
    while time.monotonic() < deadline:
        p = _profile(backend)
        if ok(p):
            return p
        time.sleep(0.1)
    raise AssertionError("setup never got there")


def _states(p: dict[str, Any]) -> dict[str, str]:
    return {x["id"]: x["install"]["state"] for x in p["items"] if x["install"]}


def test_install_resumes_after_backend_is_killed(backend: Backend) -> None:
    backend.start(DRAMA_SETUP_FAKE_DELAY_MS="0", DRAMA_SETUP_FAKE_TICK_MS="150")
    httpx.post(f"{backend.base}/setup/scan", headers=HEADERS, timeout=5)
    scanned = _wait(backend, lambda p: p["phase"] == "scanned")
    items = [x["id"] for x in scanned["items"] if x["installable"]]
    body = {"items": items, "mirror": "official", "dir": "D:\\DramaStudio"}
    resp = httpx.post(f"{backend.base}/setup/install", json=body, headers=HEADERS, timeout=5)
    assert resp.status_code == 202
    order = resp.json()["install"]["items"]
    assert resp.json()["install"]["confirm"]  # the change list for the PC's own ComfyUI
    resp = httpx.post(f"{backend.base}/setup/install/confirm", headers=HEADERS, timeout=5)
    assert resp.status_code == 200

    # Two items done, the third one half way.
    p = _wait(backend, lambda p: Counter(_states(p).values())["done"] >= 2)
    backend.kill()
    killed_at = datetime.now(UTC).replace(tzinfo=None)
    before = _states(p)
    finished = {i for i, s in before.items() if s == "done"}

    backend.start(DRAMA_SETUP_FAKE_DELAY_MS="0", DRAMA_SETUP_FAKE_TICK_MS="0")
    done = _wait(backend, lambda p: p["phase"] == "done")
    states = _states(done)
    assert Counter(states.values()) == {"done": len(items) - 1, "failed": 1}
    assert states["sage"] == "failed"
    assert set(order) == set(states)

    jobs = httpx.get(f"{backend.base}/jobs", timeout=5).json()
    install = [j for j in jobs if j["kind"] == "setup.install"]
    assert len(install) == 1 and install[0]["state"] == "succeeded"
    assert install[0]["attempt"] == 2  # interrupted once, then resumed
    # What was done before the kill was not installed again (that would move installed_at).
    with sqlite3.connect(backend.home / "studio.db") as conn:
        rows = conn.execute("select item_id, installed_at from installed_item").fetchall()
    installed_at = {r[0]: datetime.fromisoformat(r[1]).replace(tzinfo=None) for r in rows}
    assert finished and all(installed_at[i] < killed_at for i in finished)
    # The snapshot was taken once, before the first change; the resumed run reused it.
    with sqlite3.connect(backend.home / "studio.db") as conn:
        assert conn.execute("select count(*) from comfy_snapshot").fetchone() == (1,)
    rescan = httpx.post(f"{backend.base}/setup/scan", headers=HEADERS, timeout=5)
    assert rescan.status_code == 202
    after = _wait(backend, lambda p: p["phase"] == "scanned")
    assert {x["id"] for x in after["items"] if x["installable"]} == {"sage"}
