"""Assets (SPEC 9.1, M3): ``/series/{id}/assets``, ``/assets/{id}``, ``/episodes/{id}/assets/…``."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from drama_series_agent.api.state import StudioState, get_state
from drama_series_agent.assets.schema import AssetOut, AssetPatch, MatrixOut
from drama_series_agent.core.jobs import job_public

router = APIRouter(tags=["assets"])

State = Annotated[StudioState, Depends(get_state)]


@router.get("/series/{series_id}/assets")
async def list_assets(
    series_id: str,
    state: State,
    episode: Annotated[str | None, Query(max_length=64)] = None,
) -> list[AssetOut]:
    """The series' assets, characters first; ``scenes`` and ``source`` are about ``episode``."""
    return await state.assets.list_assets(series_id, episode)


@router.patch("/assets/{asset_id}")
async def patch_asset(asset_id: str, body: AssetPatch, state: State) -> AssetOut:
    """改描述 / 选这个 / 画面文字 / 音色来源 (409 ``product_locked`` once locked)."""
    return await state.assets.patch(asset_id, body)


@router.post("/episodes/{episode_id}/assets/analyze")
async def analyze(episode_id: str, state: State) -> dict[str, Any]:
    """「重新分析剧本」 → the queued 素材分析 job (its version is adopted when it succeeds)."""
    return job_public(await state.assets.analyze(episode_id))


@router.get("/episodes/{episode_id}/assets/matrix")
async def matrix(episode_id: str, state: State) -> MatrixOut:
    """出场矩阵: the episode's scenes × the assets it uses."""
    return await state.assets.matrix(episode_id)
