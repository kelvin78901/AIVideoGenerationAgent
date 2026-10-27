"""Generate step (M5 step 8): ``/series/{id}/generate-rules`` and ``/episodes/{id}/generate-log``
(``pipeline/generate.py``)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from drama_series_agent.api.errors import ApiError
from drama_series_agent.api.state import StudioState, get_state
from drama_series_agent.core.config import get_config
from drama_series_agent.core.models_db import Episode, Series
from drama_series_agent.pipeline.generate import (
    VIDEO_COMPONENT,
    GenerateLogEntry,
    GenerateRules,
    GenerateRulesPatch,
    generate_log,
    load_rules,
    save_rules,
)

router = APIRouter(tags=["generate"])

State = Annotated[StudioState, Depends(get_state)]


@router.get("/series/{series_id}/generate-rules")
async def get_generate_rules(series_id: str, state: State) -> GenerateRules:
    async with state.db.session() as session:
        if await session.get(Series, series_id) is None:
            raise ApiError(404, "series_not_found", id=series_id)
        return await load_rules(session, series_id)


@router.put("/series/{series_id}/generate-rules")
async def put_generate_rules(
    series_id: str, body: GenerateRulesPatch, state: State
) -> GenerateRules:
    """Change one or more rules; the QA thresholds are read-only (components.yaml)."""
    async with state.db.session() as session:
        if await session.get(Series, series_id) is None:
            raise ApiError(404, "series_not_found", id=series_id)
        return await save_rules(session, series_id, body)


@router.get("/episodes/{episode_id}/generate-log")
async def get_generate_log(episode_id: str, state: State) -> list[GenerateLogEntry]:
    """运行记录, oldest first."""
    settings = await state.router.settings(VIDEO_COMPONENT)
    fallback = settings.values.get("fallback")
    timeout_s = fallback.get("timeout_s") if isinstance(fallback, dict) else None
    if not isinstance(timeout_s, int | float):
        timeout_s = get_config().components.fallback_defaults.local_timeout_s
    async with state.db.session() as session:
        episode = await session.get(Episode, episode_id)
        if episode is None or episode.retired:
            raise ApiError(404, "episode_not_found", id=episode_id)
        return await generate_log(session, episode_id, timeout_minutes=round(timeout_s / 60))
