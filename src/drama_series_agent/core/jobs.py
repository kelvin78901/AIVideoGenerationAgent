"""Persistent asyncio job queue (SPEC 9).

Jobs live in the ``job`` table, so a restart picks up where it left off: jobs that were
``running`` when the process died go back to ``queued`` and run again.

Queues: ``gpu`` (concurrency 1), ``cpu`` (cores / 2) and ``api:<provider>`` (configurable,
default 2). Within a queue, higher ``priority`` runs first, then oldest first. A job whose
``depends_on`` jobs have not all succeeded waits; if one of them failed or was canceled the
job fails with ``dependency_failed``.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from loguru import logger
from sqlmodel import col, select

from drama_series_agent.core.db import Database
from drama_series_agent.core.events import EventBus, EventType
from drama_series_agent.core.models_db import Job, utcnow

QUEUED = "queued"
WAITING_CONFIRM = "waiting_confirm"
RUNNING = "running"
SUCCEEDED = "succeeded"
FAILED = "failed"
CANCELED = "canceled"
TERMINAL = frozenset({SUCCEEDED, FAILED, CANCELED})
STATES = frozenset({QUEUED, WAITING_CONFIRM, RUNNING, *TERMINAL})

DEFAULT_API_CONCURRENCY = 2


class JobError(Exception):
    """A handler failure with an i18n error code. ``retryable`` jobs go back to the queue."""

    def __init__(self, code: str, params: dict[str, Any] | None = None, *, retryable: bool = False):
        super().__init__(code)
        self.code = code
        self.params = params or {}
        self.retryable = retryable


class JobNeedsConfirm(Exception):
    """Raised by a handler that must ask the user before going on (e.g. a fallback with
    ``notify: ask``). The job goes back to ``waiting_confirm`` with ``params`` merged in and
    this attempt not counted; confirming queues it again."""

    def __init__(self, params: dict[str, Any], est_cost_usd: float | None = None) -> None:
        super().__init__("needs_confirm")
        self.params = params
        self.est_cost_usd = est_cost_usd


class JobStateError(Exception):
    def __init__(self, job_id: str, state: str, action: str):
        super().__init__(f"cannot {action} job {job_id} in state {state}")
        self.job_id = job_id
        self.state = state
        self.action = action


@dataclass
class JobContext:
    job: Job
    queue: JobQueue

    @property
    def params(self) -> dict[str, Any]:
        return self.job.params_json

    async def progress(self, data: dict[str, Any]) -> None:
        await self.queue.bus.publish(
            EventType.JOB_UPDATED, {**job_public(self.job), "progress": data}
        )


Handler = Callable[[JobContext], Awaitable[dict[str, Any] | None]]


def job_public(job: Job) -> dict[str, Any]:
    """The JSON shape used by the API and ``job.updated`` events."""

    def ts(value: Any) -> str | None:
        return value.isoformat() if value is not None else None

    return {
        "id": job.id,
        "series_id": job.series_id,
        "episode_id": job.episode_id,
        "product_id": job.product_id,
        "component_id": job.component_id,
        "kind": job.kind,
        "queue": job.queue,
        "state": job.state,
        "priority": job.priority,
        "attempt": job.attempt,
        "max_attempts": job.max_attempts,
        "params": job.params_json,
        "result": job.result_json,
        "error": job.error_json,
        "depends_on": job.depends_on_json,
        "est_cost_usd": job.est_cost_usd,
        "confirmed_usd": job.confirmed_usd,
        "fallback_from_job_id": job.fallback_from_job_id,
        "created_at": ts(job.created_at),
        "started_at": ts(job.started_at),
        "finished_at": ts(job.finished_at),
    }


@dataclass
class _QueueSlots:
    limit: int
    running: dict[str, asyncio.Task[None]] = field(default_factory=dict)

    @property
    def free(self) -> int:
        return self.limit - len(self.running)


class JobQueue:
    def __init__(
        self,
        db: Database,
        bus: EventBus,
        *,
        concurrency: dict[str, int] | None = None,
        poll_interval_s: float = 1.0,
    ) -> None:
        self.db = db
        self.bus = bus
        self._handlers: dict[str, Handler] = {}
        self._concurrency = {"gpu": 1, "cpu": max(1, (os.cpu_count() or 2) // 2)}
        self._concurrency.update(concurrency or {})
        self._slots: dict[str, _QueueSlots] = {}
        self._wake = asyncio.Event()
        self._poll_interval_s = poll_interval_s
        self._dispatcher: asyncio.Task[None] | None = None
        self._stopping = False
        self._finished: list[Callable[[Job], Awaitable[None]]] = []

    # ------------------------------------------------------------------ registration

    def register(self, kind: str, handler: Handler) -> None:
        self._handlers[kind] = handler

    def on_finished(self, hook: Callable[[Job], Awaitable[None]]) -> None:
        """Called after a job ends (succeeded, failed or canceled); a failing hook is logged."""
        self._finished.append(hook)

    def limit_for(self, queue: str) -> int:
        if queue in self._concurrency:
            return self._concurrency[queue]
        if queue.startswith("api:"):
            return self._concurrency.get("api", DEFAULT_API_CONCURRENCY)
        return 1

    # ------------------------------------------------------------------ commands

    async def enqueue(
        self,
        kind: str,
        queue: str,
        params: dict[str, Any] | None = None,
        *,
        series_id: str | None = None,
        episode_id: str | None = None,
        product_id: str | None = None,
        component_id: str | None = None,
        priority: int = 0,
        max_attempts: int = 3,
        depends_on: Iterable[str] = (),
        est_cost_usd: float | None = None,
        fallback_from_job_id: str | None = None,
        wait_for_confirm: bool = False,
    ) -> Job:
        job = Job(
            kind=kind,
            queue=queue,
            params_json=dict(params or {}),
            series_id=series_id,
            episode_id=episode_id,
            product_id=product_id,
            component_id=component_id,
            priority=priority,
            max_attempts=max_attempts,
            depends_on_json=list(depends_on),
            est_cost_usd=est_cost_usd,
            fallback_from_job_id=fallback_from_job_id,
            state=WAITING_CONFIRM if wait_for_confirm else QUEUED,
        )
        async with self.db.session() as session:
            session.add(job)
            await session.commit()
            await session.refresh(job)
        await self._announce(job)
        self._wake.set()
        return job

    async def get(self, job_id: str) -> Job | None:
        async with self.db.session() as session:
            return await session.get(Job, job_id)

    async def list(self, *, state: str | None = None, limit: int = 100) -> list[Job]:
        stmt = select(Job).order_by(col(Job.created_at).desc()).limit(limit)
        if state is not None:
            stmt = stmt.where(Job.state == state)
        async with self.db.session() as session:
            return list((await session.exec(stmt)).all())

    async def cancel(self, job_id: str) -> Job:
        job = await self._require(job_id)
        if job.state in TERMINAL:
            raise JobStateError(job_id, job.state, "cancel")
        task = self._slots.get(job.queue, _QueueSlots(0)).running.get(job_id)
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            refreshed = await self.get(job_id)
            assert refreshed is not None
            return refreshed
        return await self._finish(job_id, CANCELED)

    async def confirm(self, job_id: str) -> Job:
        job = await self._require(job_id)
        if job.state != WAITING_CONFIRM:
            raise JobStateError(job_id, job.state, "confirm")
        # The yes covers the estimate it was shown (the router's budget guard reads it).
        job = await self._update(job_id, state=QUEUED, confirmed_usd=job.est_cost_usd)
        self._wake.set()
        return job

    # ------------------------------------------------------------------ lifecycle

    async def recover(self) -> int:
        """Put jobs interrupted by a crash back in the queue. Returns how many."""
        async with self.db.session() as session:
            rows = (await session.exec(select(Job).where(Job.state == RUNNING))).all()
            ids = [r.id for r in rows]
        for row in rows:
            if row.attempt >= row.max_attempts:
                # It keeps dying mid-run (e.g. crashes the process); don't loop forever.
                await self._finish(row.id, FAILED, error_json={"code": "interrupted", "params": {}})
                continue
            await self._update(row.id, state=QUEUED, started_at=None)
            logger.info("job {} recovered after restart (attempt {})", row.id, row.attempt)
        return len(ids)

    async def start(self) -> None:
        self._stopping = False
        await self.recover()
        self._dispatcher = asyncio.create_task(self._dispatch_loop(), name="job-dispatcher")

    async def stop(self) -> None:
        """Stop dispatching. Running jobs are interrupted and re-queued for the next start."""
        self._stopping = True
        if self._dispatcher is not None:
            self._dispatcher.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._dispatcher
            self._dispatcher = None
        tasks = [t for slots in self._slots.values() for t in slots.running.values()]
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def wait_idle(self, timeout_s: float = 10.0) -> None:
        """Test helper: wait until nothing is queued or running."""
        async with asyncio.timeout(timeout_s):
            while True:
                async with self.db.session() as session:
                    busy = (
                        await session.exec(
                            select(Job).where(col(Job.state).in_([QUEUED, RUNNING])).limit(1)
                        )
                    ).first()
                if busy is None:
                    return
                await asyncio.sleep(0.02)

    # ------------------------------------------------------------------ internals

    async def _require(self, job_id: str) -> Job:
        job = await self.get(job_id)
        if job is None:
            raise KeyError(job_id)
        return job

    async def _announce(self, job: Job) -> None:
        await self.bus.publish(EventType.JOB_UPDATED, job_public(job))

    async def _update(self, job_id: str, **fields: Any) -> Job:
        async with self.db.session() as session:
            job = await session.get(Job, job_id)
            if job is None:
                raise KeyError(job_id)
            for key, value in fields.items():
                setattr(job, key, value)
            session.add(job)
            await session.commit()
            await session.refresh(job)
        await self._announce(job)
        return job

    async def _finish(self, job_id: str, state: str, **fields: Any) -> Job:
        job = await self._update(job_id, state=state, finished_at=utcnow(), **fields)
        for hook in self._finished:
            try:
                await hook(job)
            except Exception:
                logger.exception("job {} finished hook failed", job_id)
        return job

    async def _dispatch_loop(self) -> None:
        while not self._stopping:
            self._wake.clear()
            try:
                await self._dispatch_once()
            except Exception:
                logger.exception("job dispatcher iteration failed")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._wake.wait(), self._poll_interval_s)

    async def _dispatch_once(self) -> None:
        async with self.db.session() as session:
            stmt = (
                select(Job)
                .where(Job.state == QUEUED)
                .order_by(col(Job.priority).desc(), col(Job.created_at), col(Job.id))
            )
            candidates = list((await session.exec(stmt)).all())
            dep_ids = {d for job in candidates for d in job.depends_on_json}
            dep_states: dict[str, str] = {}
            if dep_ids:
                deps = await session.exec(select(Job).where(col(Job.id).in_(dep_ids)))
                dep_states = {d.id: d.state for d in deps}

        for job in candidates:
            slots = self._slots.setdefault(job.queue, _QueueSlots(self.limit_for(job.queue)))
            if job.id in slots.running:
                continue
            states = [dep_states.get(d, "missing") for d in job.depends_on_json]
            if any(s in (FAILED, CANCELED, "missing") for s in states):
                await self._finish(
                    job.id,
                    FAILED,
                    error_json={"code": "dependency_failed", "params": {"deps": states}},
                )
                continue
            if any(s != SUCCEEDED for s in states) or slots.free <= 0:
                continue
            handler = self._handlers.get(job.kind)
            if handler is None:
                await self._finish(
                    job.id, FAILED, error_json={"code": "no_handler", "params": {"kind": job.kind}}
                )
                continue
            slots.running[job.id] = asyncio.create_task(
                self._run(job.id, handler, slots), name=f"job-{job.id}"
            )

    async def _run(self, job_id: str, handler: Handler, slots: _QueueSlots) -> None:
        try:
            job = await self._require(job_id)
            job = await self._update(
                job_id, state=RUNNING, attempt=job.attempt + 1, started_at=utcnow()
            )
            try:
                result = await handler(JobContext(job=job, queue=self))
            except JobNeedsConfirm as exc:
                await self._update(
                    job_id,
                    state=WAITING_CONFIRM,
                    attempt=job.attempt - 1,
                    params_json={**job.params_json, **exc.params},
                    est_cost_usd=exc.est_cost_usd,
                    confirmed_usd=None,
                    started_at=None,
                )
            except JobError as exc:
                error = {"code": exc.code, "params": exc.params}
                if exc.retryable and job.attempt < job.max_attempts:
                    await self._update(job_id, state=QUEUED, error_json=error, started_at=None)
                else:
                    await self._finish(job_id, FAILED, error_json=error)
            except Exception as exc:
                logger.exception("job {} ({}) crashed", job_id, job.kind)
                await self._finish(
                    job_id,
                    FAILED,
                    error_json={"code": "internal", "params": {"message": str(exc)[:500]}},
                )
            else:
                await self._finish(job_id, SUCCEEDED, result_json=result, error_json=None)
        except asyncio.CancelledError:
            # Canceled at any point of the run: by the user, or by shutdown.
            current = await self.get(job_id)
            if current is not None and current.state not in TERMINAL:
                if self._stopping:
                    # Shutdown: leave it for the next start (same as a crash).
                    await self._update(job_id, state=QUEUED, started_at=None)
                else:
                    await self._finish(job_id, CANCELED)
            raise
        finally:
            slots.running.pop(job_id, None)
            self._wake.set()
