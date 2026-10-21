"""Episodes and beats (SPEC 9.1): ``GET /series/{id}/episodes``, ``PATCH /episodes/{id}``,
``PATCH /beats/{id}``, ``GET /episodes/{id}/progress`` (and ``GET /series/{id}/progress`` before
there are episodes). Edits of the plan append an ``edit``
version of 分集规划 and adopt it (``episodes/service.py``)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from drama_series_agent.api.state import StudioState, get_state
from drama_series_agent.episodes.schema import (
    BeatPatch,
    EpisodeOut,
    EpisodePatch,
    EpisodeProgressOut,
    SeriesProgressOut,
)

router = APIRouter(tags=["episodes"])

State = Annotated[StudioState, Depends(get_state)]


@router.get("/series/{series_id}/episodes")
async def list_episodes(series_id: str, state: State) -> list[EpisodeOut]:
    """The adopted plan, in order, each episode with its beats."""
    return await state.episodes.list_episodes(series_id)


@router.patch("/episodes/{episode_id}")
async def patch_episode(episode_id: str, body: EpisodePatch, state: State) -> EpisodeOut:
    """集名、钩子、卡点、预计时长 (a new version of the plan) and 本集 API 预算 (a setting)."""
    return await state.episodes.patch_episode(episode_id, body)


@router.patch("/beats/{beat_id}")
async def patch_beat(beat_id: str, body: BeatPatch, state: State) -> list[EpisodeOut]:
    """改节拍的文字、情绪, or drag it to another episode / place; returns the whole plan."""
    return await state.episodes.patch_beat(beat_id, body)


@router.get("/episodes/{episode_id}/progress")
async def episode_progress(episode_id: str, state: State) -> EpisodeProgressOut:
    """The nav badges of one episode's steps."""
    return await state.episodes.progress(episode_id)


@router.get("/series/{series_id}/progress")
async def series_progress(series_id: str, state: State) -> SeriesProgressOut:
    """The nav badges while the series has no episodes yet (小说 can be confirmed already)."""
    return await state.episodes.series_progress(series_id)
