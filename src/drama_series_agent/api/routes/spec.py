"""Output spec (SPEC 13): ``/series/{id}/spec`` and ``/spec/presets``."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from drama_series_agent.api.errors import ApiError
from drama_series_agent.api.state import StudioState, get_state
from drama_series_agent.core.config import get_config
from drama_series_agent.core.models_db import OutputSpecRow
from drama_series_agent.spec.schema import OutputSpec, SpecPatch, apply_patch, presets, to_public

router = APIRouter(tags=["spec"])

State = Annotated[StudioState, Depends(get_state)]


@router.get("/spec/presets")
async def get_presets() -> dict[str, Any]:
    return presets(get_config().spec)


@router.get("/series/{series_id}/spec")
async def get_spec(series_id: str, state: State) -> OutputSpec:
    async with state.db.session() as session:
        row = await session.get(OutputSpecRow, series_id)
    if row is None:
        raise ApiError(404, "series_not_found", id=series_id)
    return to_public(row)


@router.put("/series/{series_id}/spec")
async def put_spec(
    series_id: str,
    body: SpecPatch,
    state: State,
    confirmed_impact: Annotated[str | None, Query(max_length=128)] = None,
) -> OutputSpec:
    """Partial update. Once locked, a new aspect needs a confirmed impact preview (SPEC 13.3).

    ``confirmed_impact`` is the id of the impact preview the user applied. M1 only checks that
    it is present; the id is validated once invalidation is real (M2).
    """
    async with state.db.session() as session:
        row = await session.get(OutputSpecRow, series_id)
        if row is None:
            raise ApiError(404, "series_not_found", id=series_id)
        new_aspect = body.aspect is not None and body.aspect != row.aspect
        if row.locked_at is not None and new_aspect and not confirmed_impact:
            raise ApiError(409, "spec_locked", aspect=row.aspect)
        apply_patch(row, body)
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return to_public(row)
