"""Generate step (M5 step 8): ``/series/{id}/generate-rules`` and ``/episodes/{id}/generate-log``
(``pipeline/generate.py``); 按镜头选工作流 (step 12a): ``/series/{id}/workflow-rules``
(``pipeline/vselect.py``)."""

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
from drama_series_agent.pipeline.vselect import Rules, pickable
from drama_series_agent.pipeline.vselect import load_rules as load_select_rules
from drama_series_agent.pipeline.vselect import save_rules as save_select_rules

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


class WorkflowRulesOut(Rules):
    """The series' rules table; ``saved`` False: the config's. ``models``: the workflows a rule
    may name (平台推荐 and 我的工作流 of 视频生成, whether or not this machine runs them now)."""

    saved: bool
    models: list[str]


async def _workflow_rules(state: StudioState, series_id: str) -> WorkflowRulesOut:
    async with state.db.session() as session:
        if await session.get(Series, series_id) is None:
            raise ApiError(404, "series_not_found", id=series_id)
        rules, saved = await load_select_rules(session, series_id)
    return WorkflowRulesOut(**rules.model_dump(), saved=saved, models=pickable(state.registry))


@router.get("/series/{series_id}/workflow-rules", response_model_exclude_none=True)
async def get_workflow_rules(series_id: str, state: State) -> WorkflowRulesOut:
    return await _workflow_rules(state, series_id)


@router.put("/series/{series_id}/workflow-rules", response_model_exclude_none=True)
async def put_workflow_rules(series_id: str, body: Rules, state: State) -> WorkflowRulesOut:
    """Replace the table (order matters: the first rule a shot meets wins)."""
    models = pickable(state.registry)
    for rule in body.rules:
        if rule.model not in models:
            raise ApiError(422, "workflow_rule_model", model=rule.model)
    async with state.db.session() as session:
        if await session.get(Series, series_id) is None:
            raise ApiError(404, "series_not_found", id=series_id)
        await save_select_rules(session, series_id, body)
    return await _workflow_rules(state, series_id)


@router.delete("/series/{series_id}/workflow-rules", response_model_exclude_none=True)
async def reset_workflow_rules(series_id: str, state: State) -> WorkflowRulesOut:
    """Back to the config's table."""
    async with state.db.session() as session:
        if await session.get(Series, series_id) is None:
            raise ApiError(404, "series_not_found", id=series_id)
        await save_select_rules(session, series_id, None)
    return await _workflow_rules(state, series_id)
