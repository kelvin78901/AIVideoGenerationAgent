from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest

from drama_series_agent.core.db import Database
from drama_series_agent.core.events import EventBus
from drama_series_agent.core.jobs import (
    CANCELED,
    FAILED,
    QUEUED,
    RUNNING,
    SUCCEEDED,
    WAITING_CONFIRM,
    JobContext,
    JobError,
    JobNeedsConfirm,
    JobQueue,
    JobStateError,
)
from drama_series_agent.core.models_db import Job


@pytest.fixture
async def queue(studio_db: Database) -> AsyncIterator[JobQueue]:
    q = JobQueue(studio_db, EventBus(studio_db), poll_interval_s=0.05)
    yield q
    await q.stop()


class Tracker:
    """Handler that records concurrency and can be held open."""

    def __init__(self, delay_s: float = 0.05) -> None:
        self.delay_s = delay_s
        self.active = 0
        self.max_active = 0
        self.order: list[str] = []
        self.release = asyncio.Event()
        self.release.set()

    async def __call__(self, ctx: JobContext) -> dict[str, Any]:
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        self.order.append(ctx.params.get("name", ctx.job.id))
        try:
            await asyncio.sleep(self.delay_s)
            await self.release.wait()
        finally:
            self.active -= 1
        return {"echo": ctx.params.get("name")}


async def _state(q: JobQueue, job_id: str) -> str:
    job = await q.get(job_id)
    assert job is not None
    return job.state


async def _until(q: JobQueue, job_id: str, state: str, limit_s: float = 5.0) -> None:
    async with asyncio.timeout(limit_s):
        while await _state(q, job_id) != state:  # noqa: ASYNC110 (polling the database)
            await asyncio.sleep(0.01)


async def test_runs_job_and_stores_result(queue: JobQueue) -> None:
    queue.register("echo", Tracker(0))
    await queue.start()
    job = await queue.enqueue("echo", "cpu", {"name": "a"})
    await queue.wait_idle()
    done = await queue.get(job.id)
    assert done is not None
    assert done.state == SUCCEEDED
    assert done.result_json == {"echo": "a"}
    assert done.attempt == 1
    assert done.started_at is not None and done.finished_at is not None


async def test_gpu_queue_runs_one_at_a_time(queue: JobQueue) -> None:
    tracker = Tracker(0.05)
    queue.register("render", tracker)
    await queue.start()
    for i in range(3):
        await queue.enqueue("render", "gpu", {"name": f"g{i}"})
    await queue.wait_idle()
    assert tracker.max_active == 1
    assert tracker.order == ["g0", "g1", "g2"]


async def test_api_queue_runs_in_parallel(queue: JobQueue) -> None:
    tracker = Tracker(0.1)
    queue.register("call", tracker)
    await queue.start()
    for i in range(4):
        await queue.enqueue("call", "api:deepseek", {"name": f"a{i}"})
    await queue.wait_idle()
    assert tracker.max_active == 2  # default api concurrency


async def test_priority_then_fifo(studio_db: Database) -> None:
    q = JobQueue(studio_db, EventBus(studio_db), poll_interval_s=0.05)
    tracker = Tracker(0)
    q.register("t", tracker)
    for name, prio in [("low1", 0), ("high", 5), ("low2", 0)]:
        await q.enqueue("t", "gpu", {"name": name}, priority=prio)
    await q.start()
    try:
        await q.wait_idle()
    finally:
        await q.stop()
    assert tracker.order == ["high", "low1", "low2"]


async def test_cancel_queued_and_running(queue: JobQueue) -> None:
    tracker = Tracker(0)
    tracker.release.clear()
    queue.register("t", tracker)
    await queue.start()
    running = await queue.enqueue("t", "gpu", {"name": "r"})
    waiting = await queue.enqueue("t", "gpu", {"name": "w"})
    await _until(queue, running.id, RUNNING)
    assert (await queue.cancel(waiting.id)).state == CANCELED
    assert (await queue.cancel(running.id)).state == CANCELED
    with pytest.raises(JobStateError):
        await queue.cancel(running.id)
    with pytest.raises(KeyError):
        await queue.cancel("missing")
    assert tracker.order == ["r"]


async def test_waiting_confirm_runs_only_after_confirm(queue: JobQueue) -> None:
    tracker = Tracker(0)
    queue.register("t", tracker)
    await queue.start()
    job = await queue.enqueue("t", "api:x", {"name": "c"}, wait_for_confirm=True)
    await asyncio.sleep(0.15)
    assert await _state(queue, job.id) == WAITING_CONFIRM
    await queue.confirm(job.id)
    await _until(queue, job.id, SUCCEEDED)
    with pytest.raises(JobStateError):
        await queue.confirm(job.id)


async def test_dependencies(queue: JobQueue) -> None:
    tracker = Tracker(0.02)
    queue.register("t", tracker)

    async def boom(_ctx: JobContext) -> None:
        raise JobError("mock_failure")

    queue.register("boom", boom)
    await queue.start()
    first = await queue.enqueue("t", "cpu", {"name": "first"})
    second = await queue.enqueue("t", "cpu", {"name": "second"}, depends_on=[first.id], priority=9)
    bad = await queue.enqueue("boom", "cpu")
    blocked = await queue.enqueue("t", "cpu", {"name": "never"}, depends_on=[bad.id])
    await queue.wait_idle()
    assert tracker.order == ["first", "second"]
    assert await _state(queue, second.id) == SUCCEEDED
    blocked_job = await queue.get(blocked.id)
    assert blocked_job is not None and blocked_job.state == FAILED
    assert blocked_job.error_json is not None
    assert blocked_job.error_json["code"] == "dependency_failed"


async def test_errors_and_retries(queue: JobQueue) -> None:
    calls = {"flaky": 0}

    async def flaky(_ctx: JobContext) -> dict[str, Any]:
        calls["flaky"] += 1
        if calls["flaky"] < 3:
            raise JobError("rate_limited", {"status": 429}, retryable=True)
        return {"ok": True}

    async def crash(_ctx: JobContext) -> None:
        raise RuntimeError("bug")

    queue.register("flaky", flaky)
    queue.register("crash", crash)
    await queue.start()
    ok = await queue.enqueue("flaky", "api:x", max_attempts=3)
    bad = await queue.enqueue("crash", "cpu")
    unknown = await queue.enqueue("nope", "cpu")
    await queue.wait_idle()
    ok_job, bad_job, unknown_job = [await queue.get(j.id) for j in (ok, bad, unknown)]
    assert ok_job is not None and ok_job.state == SUCCEEDED and ok_job.attempt == 3
    assert bad_job is not None and bad_job.state == FAILED and bad_job.attempt == 1
    assert bad_job.error_json == {"code": "internal", "params": {"message": "bug"}}
    assert unknown_job is not None and unknown_job.error_json is not None
    assert unknown_job.error_json["code"] == "no_handler"


async def test_restart_resumes_interrupted_job(studio_db: Database) -> None:
    bus = EventBus(studio_db)
    # Simulate a crash: a job left in "running" by a dead process.
    async with studio_db.session() as s:
        s.add(Job(id="crashed", kind="t", queue="gpu", state=RUNNING, attempt=1))
        s.add(Job(id="dead", kind="t", queue="gpu", state=RUNNING, attempt=3, max_attempts=3))
        await s.commit()
    q = JobQueue(studio_db, bus, poll_interval_s=0.05)
    tracker = Tracker(0)
    q.register("t", tracker)
    await q.start()
    try:
        await q.wait_idle()
    finally:
        await q.stop()
    crashed, dead = await q.get("crashed"), await q.get("dead")
    assert crashed is not None and crashed.state == SUCCEEDED and crashed.attempt == 2
    assert dead is not None and dead.state == FAILED
    assert dead.error_json == {"code": "interrupted", "params": {}}


async def test_stop_requeues_running_job(studio_db: Database) -> None:
    bus = EventBus(studio_db)
    q = JobQueue(studio_db, bus, poll_interval_s=0.05)
    tracker = Tracker(0)
    tracker.release.clear()
    q.register("t", tracker)
    await q.start()
    job = await q.enqueue("t", "gpu")
    await _until(q, job.id, RUNNING)
    await q.stop()
    assert await _state(q, job.id) == QUEUED
    # a new queue (e.g. after restart) finishes it
    q2 = JobQueue(studio_db, bus, poll_interval_s=0.05)
    tracker.release.set()
    q2.register("t", tracker)
    await q2.start()
    try:
        await _until(q2, job.id, SUCCEEDED)
    finally:
        await q2.stop()


async def test_state_changes_are_published(queue: JobQueue) -> None:
    queue.register("t", Tracker(0))
    await queue.start()
    job = await queue.enqueue("t", "cpu")
    states: list[str] = []
    async with asyncio.timeout(5):
        # The row turns "succeeded" just before its event is published, so poll the events.
        while states[-1:] != [SUCCEEDED]:
            await asyncio.sleep(0.01)
            states = [e.data["state"] for e in await queue.bus.replay(0) if e.data["id"] == job.id]
    assert states == [QUEUED, RUNNING, SUCCEEDED]


async def test_confirm_records_the_amount(queue: JobQueue) -> None:
    queue.register("t", Tracker(0))
    await queue.start()
    job = await queue.enqueue("t", "api:x", {}, est_cost_usd=0.62, wait_for_confirm=True)
    assert (await queue.confirm(job.id)).confirmed_usd == 0.62
    await _until(queue, job.id, SUCCEEDED)


async def test_handler_can_ask_before_going_on(queue: JobQueue) -> None:
    """JobNeedsConfirm: back to waiting_confirm with new params, the attempt not counted."""
    seen: list[dict[str, Any]] = []

    async def handler(ctx: JobContext) -> dict[str, Any]:
        seen.append(dict(ctx.params))
        if "model" not in ctx.params:
            raise JobNeedsConfirm({"model": "b", "confirm": {"reason": "fallback"}}, 0.3)
        return {"model": ctx.params["model"]}

    queue.register("ask", handler)
    await queue.start()
    job = await queue.enqueue("ask", "api:x", {"name": "q"}, max_attempts=1)
    await _until(queue, job.id, WAITING_CONFIRM)
    waiting = await queue.get(job.id)
    assert waiting is not None
    assert waiting.params_json["model"] == "b" and waiting.est_cost_usd == 0.3
    assert waiting.attempt == 0  # max_attempts=1 still allows the confirmed run
    await queue.confirm(job.id)
    await _until(queue, job.id, SUCCEEDED)
    done = await queue.get(job.id)
    assert done is not None and done.result_json == {"model": "b"} and done.confirmed_usd == 0.3
    assert [s.get("model") for s in seen] == [None, "b"]


async def test_gpu_keeps_the_loaded_model_busy_before_switching(studio_db: Database) -> None:
    """Hard rule 8: queued GPU jobs for the model the last job used go first, so pictures and
    voices queued in turn do not swap models in and out of VRAM job by job. Priority still
    comes first."""
    q = JobQueue(studio_db, EventBus(studio_db), poll_interval_s=0.05)
    tracker = Tracker(0)
    q.register("t", tracker)
    jobs = [
        ("img1", "comfy/qwen-image", 0),
        ("tts1", "local/indextts2", 0),
        ("img2", "comfy/qwen-image", 0),
        ("tts2", "local/indextts2", 0),
        ("urgent", "local/indextts2", 5),
        ("img3", "comfy/qwen-image", 0),
    ]
    for name, model, prio in jobs:
        await q.enqueue("t", "gpu", {"name": name, "model_key": model}, priority=prio)
    await q.start()
    try:
        await q.wait_idle()
    finally:
        await q.stop()
    # urgent first (priority), on IndexTTS: the other IndexTTS lines follow, then the pictures
    assert tracker.order == ["urgent", "tts1", "tts2", "img1", "img2", "img3"]
