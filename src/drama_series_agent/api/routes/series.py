"""``/api/v1/series``: a series' own record. Creating one comes with novel import (M2)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from drama_series_agent.api.errors import ApiError
from drama_series_agent.api.state import StudioState, get_state
from drama_series_agent.core.models_db import Series

router = APIRouter(prefix="/series", tags=["series"])

State = Annotated[StudioState, Depends(get_state)]


def series_public(row: Series) -> dict[str, Any]:
    return row.model_dump(include={"id", "slug", "title", "ui_lang", "created_at"})


@router.get("/{series_id}")
async def get_series(series_id: str, state: State) -> dict[str, Any]:
    async with state.db.session() as session:
        row = await session.get(Series, series_id)
    if row is None:
        raise ApiError(404, "series_not_found", id=series_id)
    return series_public(row)
