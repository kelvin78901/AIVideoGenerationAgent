"""M0 acceptance: kill the backend while jobs are queued, start it again, the jobs finish."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
import pytest

if TYPE_CHECKING:
    from conftest import Backend  # tests/e2e/conftest.py

pytestmark = pytest.mark.e2e


def _db_states(path: Path) -> dict[str, tuple[str, int]]:
    with sqlite3.connect(path) as conn:
        return {r[0]: (r[1], r[2]) for r in conn.execute("select id, state, attempt from job")}


def test_jobs_resume_after_backend_is_killed(backend: Backend) -> None:
    backend.start()
    ids = []
    for i in range(3):
        resp = httpx.post(
            f"{backend.base}/dev/llm-test",
            json={"prompt": f"镜头 {i}", "delay_s": 2, "where": "local"},
            headers={"X-Drama-Studio": "1"},
            timeout=5,
        )
        assert resp.status_code == 200
        assert resp.json()["queue"] == "gpu"
        ids.append(resp.json()["id"])

    # The gpu queue runs one job at a time: wait for the first to start.
    states: dict[str, str] = {}
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        states = {i: j["state"] for i, j in backend.jobs().items()}
        if states.get(ids[0]) == "running":
            break
        time.sleep(0.05)
    assert states == {ids[0]: "running", ids[1]: "queued", ids[2]: "queued"}

    backend.kill()
    assert _db_states(backend.home / "studio.db")[ids[0]] == ("running", 1)

    backend.start()
    jobs: dict[str, dict[str, Any]] = {}
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        jobs = backend.jobs()
        if all(jobs[i]["state"] == "succeeded" for i in ids):
            break
        time.sleep(0.2)
    assert [jobs[i]["state"] for i in ids] == ["succeeded"] * 3
    assert jobs[ids[0]]["attempt"] == 2  # interrupted once, then resumed
    assert [jobs[i]["attempt"] for i in ids[1:]] == [1, 1]

    calls = httpx.get(f"{backend.base}/dev/model-calls", timeout=5).json()
    ok = [c for c in calls if c["status"] == "success"]
    assert sorted(c["job_id"] for c in ok) == sorted(ids)
    assert {(c["where"], c["model_key"]) for c in ok} == {("local", "local/qwen3.6-27b")}
