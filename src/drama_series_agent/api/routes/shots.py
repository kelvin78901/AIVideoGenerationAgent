"""An episode's shots (M4, SPEC 9.1): ``GET /episodes/{id}/shots``, ``PATCH /shots/{id}``,
``POST /shots/{id}/split|merge``. Edits append an ``edit`` version of the episode's 分镜规划
and adopt it (``shots/service.py``)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from drama_series_agent.api.state import StudioState, get_state
from drama_series_agent.shots.schema import ShotOut, ShotPatch, ShotSplitIn

router = APIRouter(tags=["shots"])

State = Annotated[StudioState, Depends(get_state)]


@router.get("/episodes/{episode_id}/shots")
async def list_shots(episode_id: str, state: State) -> list[ShotOut]:
    """The plan's version on screen; empty before the first run."""
    return await state.shots.of_episode(episode_id)


@router.patch("/shots/{shot_id}")
async def patch_shot(shot_id: str, body: ShotPatch, state: State) -> ShotOut:
    """改镜头设定; 422 ``duration_below_audio {min_s}`` shorter than its lines' audio."""
    return await state.shots.patch(shot_id, body)


@router.post("/shots/{shot_id}/split")
async def split_shot(shot_id: str, body: ShotSplitIn, state: State) -> list[ShotOut]:
    """拆分: the episode's shots after it."""
    return await state.shots.split(shot_id, body)


@router.post("/shots/{shot_id}/merge")
async def merge_shot(shot_id: str, state: State) -> list[ShotOut]:
    """和同一场的下一个镜头合并; 422 ``no_next_shot``."""
    return await state.shots.merge(shot_id)
