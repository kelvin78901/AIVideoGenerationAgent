"""First run (SPEC 12): ``/setup/profile``, ``/setup/scan`` and Mock's sample-machine switch."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from drama_series_agent.api.errors import ApiError
from drama_series_agent.api.state import StudioState, get_state
from drama_series_agent.setup.schema import MachineProfile
from drama_series_agent.setup.service import DemoMachine, NotSimulated, SetupBusy

router = APIRouter(tags=["setup"])

State = Annotated[StudioState, Depends(get_state)]


class MachineBody(BaseModel):
    machine: DemoMachine


@router.get("/setup/profile")
async def get_profile(state: State) -> MachineProfile:
    return await state.setup.profile()


@router.post("/setup/scan", status_code=202)
async def scan(state: State) -> MachineProfile:
    """Read-only scan (SPEC 12.2-1); items arrive one by one as ``setup.progress``."""
    try:
        return await state.setup.start_scan()
    except SetupBusy:
        raise ApiError(409, "setup_busy") from None


@router.post("/dev/setup/machine")
async def switch_machine(body: MachineBody, state: State) -> MachineProfile:
    """Mock only: the prototype's 示例机器 switch (PC / Mac). Resets scan and installs."""
    try:
        return await state.setup.switch_machine(body.machine)
    except NotSimulated:
        raise ApiError(403, "setup_not_simulated") from None
