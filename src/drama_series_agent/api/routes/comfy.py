"""The ComfyUI the setup scan found (SPEC 6.4.1): ``/comfy/env``."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from drama_series_agent.api.state import StudioState, get_state
from drama_series_agent.setup.schema import ComfyView

router = APIRouter(tags=["comfy"])

State = Annotated[StudioState, Depends(get_state)]


@router.get("/comfy/env")
async def get_env(state: State) -> ComfyView:
    """Path, port, versions, node packs and model files, as of the last finished scan.

    Read-only: rescan (``POST /setup/scan``) to refresh it.
    """
    return await state.setup.comfy_env()
