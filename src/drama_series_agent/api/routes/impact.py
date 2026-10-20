"""Change impact (SPEC 9.1 ``/impact/preview|apply``): editing confirmed work is previewed
first, then marked, synced or undone (``pipeline/impact.py``)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from drama_series_agent.api.state import StudioState, get_state
from drama_series_agent.pipeline.impact import (
    ImpactApplyIn,
    ImpactApplyOut,
    ImpactChangeIn,
    ImpactOut,
)

router = APIRouter(tags=["impact"])

State = Annotated[StudioState, Depends(get_state)]


@router.post("/impact/preview")
async def preview_impact(body: ImpactChangeIn, state: State) -> ImpactOut:
    """What the change would make 待更新 and what redoing it costs; nothing is written."""
    return await state.impact.preview(body)


@router.post("/impact/apply")
async def apply_impact(body: ImpactApplyIn, state: State) -> ImpactApplyOut:
    """``mark`` writes the change, ``undo`` drops it (``rerun``: M2 step 10b)."""
    return await state.impact.apply(body)
