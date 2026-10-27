"""Spending limits (SPEC 7.6, hard rule 6: price before spending).

Two checks:

- **Before a job is queued** (``before_enqueue``): its whole estimate against the component's
  单次上限 (``per_call_cap_usd``) and against what is left of the episode budget. Either one
  over → the job waits for a yes (``waiting_confirm``). Work that belongs to no episode (bible,
  enrichment, episode planning) only meets the per-call cap. A model without a known price
  (a listed model nobody priced, M5 step 7a) always waits: what it costs is not known.
- **Before each model call** (``BudgetGuardImpl``, the router's guard): a confirmed job may
  spend up to what was confirmed plus a margin (``confirm_margin``: the larger of 10% and
  $0.05, so a job of several calls does not stop on its last one because the estimate was a
  little low); anything else must stay under the per-call cap, and an unconfirmed call to a
  model without a price stops (scope ``unpriced``). A fallback that would cost more fails with
  ``budget_exceeded`` instead of spending silently.

Left of the episode budget = budget − spent − the estimates of its queued / waiting jobs − what
its running jobs are still expected to spend (estimate − spent so far, at least 0).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from sqlmodel import col, select

from drama_series_agent.core.config import ConfirmMargin, Resolved, get_config
from drama_series_agent.core.db import Database
from drama_series_agent.core.models_db import Job
from drama_series_agent.modelhub import calllog
from drama_series_agent.modelhub.adapters.base import CallContext, Estimate, ModelSpec
from drama_series_agent.modelhub.router import BudgetExceeded

EPSILON = 1e-6
# episode id → its budget in USD (None = no budget set)
EpisodeBudget = Callable[[str], Awaitable[float | None]]


@dataclass(frozen=True)
class Verdict:
    ok: bool
    estimate_usd: float
    reason: str | None = None  # per_call / episode / unpriced
    limit_usd: float | None = None

    def params(self) -> dict[str, Any]:
        """What the confirm dialog shows (stored in the job's params as ``confirm``)."""
        return {
            "reason": self.reason,
            "estimate_usd": round(self.estimate_usd, 4),
            "limit_usd": None if self.limit_usd is None else round(self.limit_usd, 4),
        }


def cap_of(settings: Resolved) -> float | None:
    cap = settings.values.get("per_call_cap_usd")
    return float(cap) if isinstance(cap, int | float) else None


class Budget:
    def __init__(self, db: Database, episode_budget: EpisodeBudget | None = None) -> None:
        self.db = db
        # Episodes arrive with the episode table (M2 step 8); until then nothing is set.
        self.episode_budget = episode_budget

    async def left(self, episode_id: str, *, exclude_job_id: str | None = None) -> float | None:
        """What is left of an episode's budget after spending and reservations."""
        if self.episode_budget is None:
            return None
        budget = await self.episode_budget(episode_id)
        if budget is None:
            return None
        spent = await calllog.total_cost(self.db, episode_id=episode_id)
        async with self.db.session() as session:
            jobs = (
                await session.exec(
                    select(Job).where(
                        Job.episode_id == episode_id,
                        col(Job.state).in_(["queued", "waiting_confirm", "running"]),
                    )
                )
            ).all()
        reserved = 0.0
        for job in jobs:
            if job.id == exclude_job_id or not job.est_cost_usd:
                continue
            if job.state == "running":
                done = await calllog.total_cost(self.db, job_id=job.id)
                reserved += max(0.0, job.est_cost_usd - done)
            else:
                reserved += job.est_cost_usd
        return budget - spent - reserved

    async def before_enqueue(
        self,
        estimate_usd: float,
        *,
        cap: float | None,
        episode_id: str | None,
        priced: bool = True,
    ) -> Verdict:
        if not priced:
            return Verdict(False, estimate_usd, "unpriced")
        if cap is not None and estimate_usd > cap + EPSILON:
            return Verdict(False, estimate_usd, "per_call", cap)
        if episode_id is not None:
            left = await self.left(episode_id)
            if left is not None and estimate_usd > left + EPSILON:
                return Verdict(False, estimate_usd, "episode", max(0.0, left))
        return Verdict(True, estimate_usd)


class BudgetGuardImpl:
    """The router's guard: runs before every model call, after the estimate."""

    def __init__(self, db: Database, margin: ConfirmMargin | None = None) -> None:
        self.db = db
        self.margin = margin or get_config().components.confirm_margin

    async def check(
        self, spec: ModelSpec, estimate: Estimate, settings: Resolved, ctx: CallContext
    ) -> None:
        cost = estimate.cost_usd
        confirmed = ctx.confirmed_usd
        spent = 0.0
        if confirmed is None and ctx.job_id is not None:
            async with self.db.session() as session:
                job = await session.get(Job, ctx.job_id)
            if job is not None and job.confirmed_usd is not None:
                confirmed = job.confirmed_usd
                spent = await calllog.total_cost(self.db, job_id=ctx.job_id)
        if confirmed is not None:
            allowed = self.margin.allowance(confirmed)
            if spent + cost > allowed + EPSILON:
                raise BudgetExceeded(cost, max(0.0, allowed - spent), "confirmed")
            return
        if not estimate.priced:
            raise BudgetExceeded(cost, 0.0, "unpriced")
        cap = cap_of(settings)
        if cap is not None and cost > cap + EPSILON:
            raise BudgetExceeded(cost, cap, "per_call")
