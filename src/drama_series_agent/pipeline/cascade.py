"""确认并同步 (M2 plan step 10; hard rule 5's one exception): after the user confirms a change
in the impact dialog, what it made stale reruns and is adopted, layer by layer, down to the
scripts.

A cascade is the reruns tagged ``{"cascade": {"id", "origin"}}`` in their job params (so a
restart picks it up again: nothing else is stored). Each step is worked out from the database
(``advance``): the jobs of the cascade so far, and the products downstream of the changed one
(``origin``) that are stale now.

- **Settle**: a rerun that succeeded is adopted (unlocking it first: its gate reopens, the user
  confirms the new content again), unless something newer is on screen by then.
- **Schedule**: a stale product downstream reruns when nothing upstream of it
  that comes earlier in the pipeline (``impact.PIPELINE_ORDER``) is still to rerun, running,
  waiting for a budget confirmation, failed or canceled. So the suggestions go first, the
  bible (built from the text and the accepted additions) after them, the plan after both, the
  scripts last; a branch that waits or fails holds up only what is below it (and is not tried
  again). The pipeline order breaks the bible ↔ suggestions loop (each reads a slice of the
  other): when the new bible changes names, the suggestions rerun a second time (their accepted
  ones are kept as they are, so the bible stays fresh). No product runs more than twice in one
  cascade, which bounds the cost.
- Every rerun goes through the usual budget check (``RunService.start``): over a cap it waits
  in 「等你确认」.
- **Stop set** (M3): a product whose takes wait for the user's pick (candidates: reference
  pictures, on-screen text, voices; ``Component.auto_adopt`` off) is never rerun by a cascade,
  since settling would adopt a take nobody picked and unlock what was locked. A script change
  never redraws or unlocks an asset; the dubbing still follows the lines. Nor is a product
  whose component says ``cascade_rerun = False`` (M4: 分镜规划, which a new run would overwrite
  the user's shots with): it is only marked 待更新.
- When nothing is left running, a toast says how many products were updated.
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Iterable

from loguru import logger
from sqlalchemy import func
from sqlmodel import col, select

from drama_series_agent.core.db import Database
from drama_series_agent.core.events import EventBus, EventType
from drama_series_agent.core.models_db import Job, Product, new_id
from drama_series_agent.pipeline.component import ComponentError, reruns_in_cascade
from drama_series_agent.pipeline.errors import PipelineError
from drama_series_agent.pipeline.gates import GateService
from drama_series_agent.pipeline.impact import Node, rank, series_graph
from drama_series_agent.pipeline.invalidation import Invalidation
from drama_series_agent.pipeline.products import ACTIVE_JOB_STATES, ProductService
from drama_series_agent.pipeline.runs import PRODUCT_RUN, RunService

_STOPPED = ("failed", "canceled")
_MAX_RUNS = 2  # per product and cascade


def cascade_of(job: Job) -> dict[str, str] | None:
    tag = job.params_json.get("cascade")
    return tag if isinstance(tag, dict) and "id" in tag and "origin" in tag else None


class CascadeService:
    def __init__(
        self,
        db: Database,
        bus: EventBus,
        products: ProductService,
        invalidation: Invalidation,
        runs: RunService,
        gates: GateService,
    ) -> None:
        self._db = db
        self._bus = bus
        self._products = products
        self._invalidation = invalidation
        self._runs = runs
        self._gates = gates
        self._lock = asyncio.Lock()
        self._announced: set[str] = set()
        runs.jobs.on_finished(self._finished)

    async def start(self, series_id: str, origin: str) -> list[str]:
        """Rerun what the change of ``origin`` made stale; returns the first layer's job ids
        (none: nothing downstream needs it)."""
        cascade_id = f"sync-{new_id()}"
        async with self._lock:
            return await self._schedule(cascade_id, origin, series_id, [])

    async def advance(self, cascade_id: str, *, announce: bool = True) -> None:
        async with self._lock:
            jobs = await self._jobs(cascade_id)
            if not jobs:
                return
            tag = cascade_of(jobs[0])
            assert tag is not None and jobs[0].series_id
            await self._settle(jobs)
            started = await self._schedule(cascade_id, tag["origin"], jobs[0].series_id, jobs)
            if started or any(j.state in ACTIVE_JOB_STATES for j in jobs):
                return
            if announce and cascade_id not in self._announced:
                self._announced.add(cascade_id)
                updated = len({j.product_id for j in jobs if j.state == "succeeded"})
                failed = len({j.product_id for j in jobs if j.state in _STOPPED})
                await self._bus.publish(
                    EventType.TOAST,
                    {
                        "level": "warning" if failed else "success",
                        "code": "cascade_done",
                        "params": {"count": updated, "failed": failed},
                    },
                )

    async def resume(self) -> None:
        """After a restart: settle and schedule what a cascade left (a job that ended just
        before the stop). Quiet: the toast comes from the jobs that finish from here on."""
        async with self._db.session() as session:
            tag = func.json_extract(Job.params_json, "$.cascade.id")
            rows = await session.exec(
                select(tag).where(Job.kind == PRODUCT_RUN, tag.is_not(None)).distinct()
            )
            ids = [str(r) for r in rows.all()]
        for cascade_id in ids:
            await self.advance(cascade_id, announce=False)

    # ------------------------------------------------------------------ internals

    async def _finished(self, job: Job) -> None:
        tag = cascade_of(job) if job.kind == PRODUCT_RUN else None
        if tag is not None:
            await self.advance(tag["id"])

    async def _jobs(self, cascade_id: str) -> list[Job]:
        async with self._db.session() as session:
            tag = func.json_extract(Job.params_json, "$.cascade.id")
            rows = await session.exec(
                select(Job)
                .where(Job.kind == PRODUCT_RUN, tag == cascade_id)
                .order_by(col(Job.created_at))
            )
            return list(rows.all())

    async def _settle(self, jobs: Iterable[Job]) -> None:
        """Adopt the reruns that succeeded (still the version on screen)."""
        for job in jobs:
            if job.state != "succeeded" or not job.product_id:
                continue
            version_id = (job.result_json or {}).get("version_id")
            if not version_id:
                continue
            async with self._db.session() as session:
                p = await session.get(Product, job.product_id)
            if p is None or p.adopted_version_id == version_id:
                continue
            if p.current_version_id != version_id:
                continue  # the user picked another one meanwhile
            if p.locked_hash:
                await self._gates.reopen_for(p)
                async with self._db.session() as session:
                    p = await session.get(Product, job.product_id)
                if p is not None and p.locked_hash:  # locked without a gate
                    await self._products.unlock(p.id)
            await self._products.adopt(str(version_id))

    async def _schedule(
        self, cascade_id: str, origin: str, series_id: str, jobs: list[Job]
    ) -> list[str]:
        async with self._db.session() as session:
            nodes, edges = await series_graph(session, series_id)
            products = list(
                (await session.exec(select(Product).where(Product.series_id == series_id))).all()
            )
            stale = await self._invalidation.stale_ids(session, products)
        products_by_id = {p.id: p for p in products}
        below: dict[str, set[str]] = {}
        above: dict[str, set[str]] = {}
        for down, up, _ in edges:
            below.setdefault(up, set()).add(down)
            above.setdefault(down, set()).add(up)
        runs: dict[str, int] = {}
        for j in jobs:
            if j.product_id:
                runs[j.product_id] = runs.get(j.product_id, 0) + 1
        done = {pid for pid, n in runs.items() if n >= _MAX_RUNS}
        holding = {
            j.product_id
            for j in jobs
            if j.product_id and (j.state in ACTIVE_JOB_STATES or j.state in _STOPPED)
        }
        todo = (_closure(origin, below) & stale) - done - holding - {origin}
        todo = {pid for pid in todo if self._cascades(products_by_id.get(pid))}
        waiting = todo | holding
        ready = [
            pid
            for pid in todo
            if not any(
                b in waiting and _before(nodes[b], nodes[pid])
                for b in _closure(pid, above)
                if b in nodes
            )
        ]
        started: list[str] = []
        for pid in sorted(ready, key=lambda i: rank(nodes[i])):
            try:
                job = await self._runs.start(
                    pid, "rerun", cascade={"id": cascade_id, "origin": origin}
                )
            except (PipelineError, ComponentError, LookupError) as exc:
                logger.warning("sync {}: {} not rerun ({})", cascade_id, pid, exc)
                continue
            started.append(job.id)
        return started

    def _cascades(self, p: Product | None) -> bool:
        """Not in the stop set: its reruns are adopted as they come."""
        comp = self._runs.components.get(p.component_id) if p is not None else None
        return comp is not None and reruns_in_cascade(comp)


def _closure(start: str, graph: dict[str, set[str]]) -> set[str]:
    seen: set[str] = set()
    queue = deque([start])
    while queue:
        for nxt in graph.get(queue.popleft(), ()):
            if nxt not in seen and nxt != start:
                seen.add(nxt)
                queue.append(nxt)
    return seen


def _before(a: Node, b: Node) -> bool:
    """``a`` comes earlier in the pipeline than ``b`` (episodes do not wait for each other)."""
    return rank(a)[0] < rank(b)[0]
