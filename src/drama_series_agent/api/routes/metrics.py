"""Metrics (SPEC 11). M5 step 8 has only ``/metrics/summary``, the top bar's spend; the rest of
the dashboard arrives in M8.

- spent = Σ billed ``model_call.cost_usd`` in the scope;
- budget = the episode's, or for the series the sum of its episodes' (None when none is set);
- projected = spent + what the active jobs are still expected to spend + the shots whose video
  never ran × that run's estimate (``takes_per_shot`` takes). A shot whose upstream is not
  ready has no estimate yet and adds nothing; the other components join in M8.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlmodel import col, select

from drama_series_agent.api.errors import ApiError
from drama_series_agent.api.state import StudioState, get_state
from drama_series_agent.core.models_db import Episode, Job, Product, Series, Shot, utcnow
from drama_series_agent.modelhub import calllog
from drama_series_agent.modelhub.budget import ACTIVE
from drama_series_agent.pipeline.generate import VIDEO_COMPONENT, load_rules

router = APIRouter(tags=["metrics"])

State = Annotated[StudioState, Depends(get_state)]
Scope = Literal["episode", "series"]


class MetricsSummary(BaseModel):
    scope: Scope
    spent_usd: float
    budget_usd: float | None
    projected_usd: float
    insights: list[dict[str, Any]]
    updated_at: str


@router.get("/metrics/summary")
async def get_summary(
    state: State,
    scope: Scope = "episode",
    episode: Annotated[str | None, Query(max_length=64)] = None,
    series: Annotated[str | None, Query(max_length=64)] = None,
) -> MetricsSummary:
    async with state.db.session() as session:
        if scope == "episode":
            ep = await session.get(Episode, episode) if episode else None
            if ep is None or ep.retired:
                raise ApiError(404, "episode_not_found", id=episode)
            series_id = ep.series_id
            episodes = [ep]
        else:
            if not series or await session.get(Series, series) is None:
                raise ApiError(404, "series_not_found", id=series)
            series_id = series
            episodes = list(
                (
                    await session.exec(
                        select(Episode).where(
                            Episode.series_id == series, col(Episode.retired).is_(False)
                        )
                    )
                ).all()
            )
        rules = await load_rules(session, series_id)
        ids = [e.id for e in episodes]
        jobs = (
            await session.exec(
                select(Job).where(col(Job.episode_id).in_(ids), col(Job.state).in_(ACTIVE))
            )
        ).all()
        shot_ids = (
            await session.exec(
                select(Shot.id).where(col(Shot.episode_id).in_(ids), col(Shot.retired).is_(False))
            )
        ).all()
        never_ran = (
            await session.exec(
                select(Product).where(
                    Product.owner_type == "shot",
                    col(Product.owner_id).in_(list(shot_ids)),
                    Product.component_id == VIDEO_COMPONENT,
                    col(Product.current_version_id).is_(None),
                    col(Product.running_job_id).is_(None),
                )
            )
        ).all()

    if scope == "episode":
        spent = await calllog.total_cost(state.db, episode_id=episodes[0].id)
        budget = episodes[0].budget_usd
    else:
        spent = await calllog.total_cost(state.db, series_id=series_id)
        set_ = [e.budget_usd for e in episodes if e.budget_usd is not None]
        budget = sum(set_) if set_ else None
    ahead = await state.budget.reserved(jobs)
    for p in never_ran:
        _, est = await state.runs.describe(p)
        if est is not None and est.cost_usd:
            ahead += est.cost_usd * rules.takes_per_shot
    return MetricsSummary(
        scope=scope,
        spent_usd=round(spent, 4),
        budget_usd=budget,
        projected_usd=round(spent + ahead, 4),
        insights=[],
        updated_at=utcnow().isoformat(),
    )
