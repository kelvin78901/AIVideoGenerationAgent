"""Step gates (SPEC 9.1 ``/gates/{gate}/confirm|reopen``): the novel, script and (M3) assets
gates. Their state is read from ``GET /episodes/{id}/progress``; the novel gate's also from
``GET /series/{id}/progress``, before there are episodes. The later gates arrive with their
milestones."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from drama_series_agent.api.state import StudioState, get_state
from drama_series_agent.pipeline.gates import GateDecisionOut, GateIn

router = APIRouter(tags=["gates"])

State = Annotated[StudioState, Depends(get_state)]


@router.post("/gates/{gate}/confirm")
async def confirm_gate(gate: str, body: GateIn, state: State) -> GateDecisionOut:
    """「确认……，进入下一步」: locks what the gate covers (``scope_id``: an episode; the novel
    gate is its series')."""
    return await state.gates.confirm(gate, body.scope_id)


@router.post("/gates/{gate}/reopen")
async def reopen_gate(gate: str, body: GateIn, state: State) -> GateDecisionOut:
    """「重新打开」: unlocks it."""
    return await state.gates.reopen(gate, body.scope_id)
