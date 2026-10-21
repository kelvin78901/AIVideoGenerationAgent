"""The story bible (SPEC 9.1): ``GET /series/{id}/bible``, ``PATCH /bible/{id}``,
``POST /bible/merge``. Edits append an ``edit`` version and adopt it (``bible/service.py``)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from drama_series_agent.api.state import StudioState, get_state
from drama_series_agent.bible.schema import BibleEntityOut, BibleMergeIn, BibleOut, BiblePatch

router = APIRouter(tags=["bible"])

State = Annotated[StudioState, Depends(get_state)]


@router.get("/series/{series_id}/bible")
async def get_bible(series_id: str, state: State) -> BibleOut:
    """The version on screen; ``adopted`` is false while it is not the adopted one."""
    return await state.bible.get(series_id)


@router.patch("/bible/{entity_id}")
async def patch_entity(entity_id: str, body: BiblePatch, state: State) -> BibleEntityOut:
    """Rename, aliases, fields, 冻结 (frozen entries are kept as they are by a rerun)."""
    return await state.bible.patch(entity_id, body)


@router.post("/bible/merge")
async def merge_entities(body: BibleMergeIn, state: State) -> BibleOut:
    """「确认合并」/「不是同一个」/「拆分」."""
    return await state.bible.merge(body)
