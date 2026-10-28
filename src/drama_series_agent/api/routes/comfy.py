"""The user's own ComfyUI (SPEC 6.4.1): ``/comfy/env`` and ``/comfy/snapshots``."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from drama_series_agent.api.errors import ApiError
from drama_series_agent.api.state import StudioState, get_state
from drama_series_agent.setup.schema import ComfySnapshot, ComfyView, Restored
from drama_series_agent.setup.service import NoComfy, SetupBusy, SnapshotFailed, SnapshotNotFound

router = APIRouter(tags=["comfy"])

State = Annotated[StudioState, Depends(get_state)]


@router.get("/comfy/env")
async def get_env(state: State) -> ComfyView:
    """Path, port, versions, node packs and model files, as of the last finished scan.

    Read-only: rescan (``POST /setup/scan``) to refresh it.
    """
    return await state.setup.comfy_env()


@router.get("/comfy/snapshots")
async def list_snapshots(state: State) -> list[ComfySnapshot]:
    """ComfyUI-Manager snapshots taken before changes (and on request), newest first."""
    return await state.setup.snapshots()


@router.post("/comfy/snapshots", status_code=201)
async def take_snapshot(state: State) -> ComfySnapshot:
    try:
        return await state.setup.take_snapshot()
    except NoComfy:
        raise ApiError(409, "comfy_not_found") from None
    except SnapshotFailed as exc:
        raise ApiError(409, "comfy_snapshot_failed", reason=exc.reason) from None


@router.post("/comfy/snapshots/{snapshot_id}/restore")
async def restore_snapshot(snapshot_id: str, state: State) -> Restored:
    """ComfyUI-Manager restores it the next time ComfyUI starts: we never restart the user's
    ComfyUI ourselves, the page says to (``restart_required``)."""
    try:
        restored = await state.setup.restore_snapshot(snapshot_id)
    except SnapshotNotFound:
        raise ApiError(404, "comfy_snapshot_not_found", id=snapshot_id) from None
    except SetupBusy:
        raise ApiError(409, "setup_busy") from None
    except SnapshotFailed as exc:
        raise ApiError(409, "comfy_snapshot_failed", reason=exc.reason) from None
    await state.workflows.restored(restored.snapshot.manager_name)
    return restored
