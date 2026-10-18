"""First run (SPEC 12): scan, install and Mock's sample-machine switch under ``/setup``."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from drama_series_agent.api.errors import ApiError
from drama_series_agent.api.state import StudioState, get_state
from drama_series_agent.setup.schema import InstallRequest, MachineProfile
from drama_series_agent.setup.service import (
    DemoMachine,
    ItemNotFound,
    ItemState,
    NothingSelected,
    NothingToConfirm,
    NotSimulated,
    SetupBusy,
)

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


@router.post("/setup/install", status_code=202)
async def install(body: InstallRequest, state: State) -> MachineProfile:
    """Install the ticked items in dependency order; ``install.confirm`` lists what needs a yes."""
    try:
        return await state.setup.start_install(body)
    except SetupBusy:
        raise ApiError(409, "setup_busy") from None
    except NothingSelected:
        raise ApiError(422, "nothing_selected") from None


@router.post("/setup/install/confirm")
async def confirm_install(state: State) -> MachineProfile:
    try:
        return await state.setup.confirm_install()
    except NothingToConfirm:
        raise ApiError(409, "setup_no_confirm") from None


@router.post("/setup/install/cancel")
async def cancel_install(state: State) -> MachineProfile:
    """Decline the confirmation: the install does not start."""
    try:
        return await state.setup.cancel_install()
    except NothingToConfirm:
        raise ApiError(409, "setup_no_confirm") from None


@router.post("/setup/items/{item_id}/retry")
async def retry_item(item_id: str, state: State) -> MachineProfile:
    try:
        return await state.setup.retry(item_id)
    except ItemState:
        raise ApiError(409, "setup_item_state", id=item_id) from None
    except ItemNotFound:
        raise ApiError(404, "setup_item_not_found", id=item_id) from None


@router.post("/setup/items/{item_id}/skip")
async def skip_item(item_id: str, state: State) -> MachineProfile:
    try:
        return await state.setup.skip(item_id)
    except ItemState:
        raise ApiError(409, "setup_item_state", id=item_id) from None
    except ItemNotFound:
        raise ApiError(404, "setup_item_not_found", id=item_id) from None


@router.post("/dev/setup/machine")
async def switch_machine(body: MachineBody, state: State) -> MachineProfile:
    """Mock only: the prototype's 示例机器 switch (PC / Mac). Resets scan and installs."""
    try:
        return await state.setup.switch_machine(body.machine)
    except NotSimulated:
        raise ApiError(403, "setup_not_simulated") from None
