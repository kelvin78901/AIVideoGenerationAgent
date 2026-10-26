"""The workflow library (SPEC 6.4.6, 9.1 ``/workflows/*``) and ComfyUI's own workflow list.

Health check, dependencies and trial runs come in M5 step 3.
"""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Annotated

from fastapi import APIRouter, Depends

from drama_series_agent.api.errors import ApiError
from drama_series_agent.api.state import StudioState, get_state
from drama_series_agent.wflib.schema import (
    BindingOut,
    ComfyWorkflowFile,
    ImportIn,
    TierIn,
    WorkflowOut,
)
from drama_series_agent.wflib.service import LibraryError

router = APIRouter(tags=["workflows"])

State = Annotated[StudioState, Depends(get_state)]


async def _call[T](work: Awaitable[T]) -> T:
    try:
        return await work
    except LibraryError as exc:
        raise ApiError(exc.status, exc.code, **exc.params) from None


@router.get("/workflows")
async def list_workflows(state: State) -> list[WorkflowOut]:
    """Platform recommended first, then 我的工作流, then unverified."""
    return await state.workflows.all()


@router.get("/workflows/{workflow_id}")
async def get_workflow(workflow_id: str, state: State) -> WorkflowOut:
    return await _call(state.workflows.get(workflow_id))


@router.patch("/workflows/{workflow_id}")
async def set_tier(workflow_id: str, body: TierIn, state: State) -> WorkflowOut:
    """409 ``workflow_tier_repo`` / ``workflow_bindings_pending`` / ``workflow_needs_trial``."""
    return await _call(state.workflows.set_tier(workflow_id, body.tier))


@router.put("/workflows/{workflow_id}/bindings")
async def put_bindings(workflow_id: str, body: list[BindingOut], state: State) -> WorkflowOut:
    """Confirms every binding sent; 409 for DramaStudio nodes, 422 for an unknown node title."""
    return await _call(state.workflows.put_bindings(workflow_id, body))


@router.post("/workflows/import", status_code=201)
async def import_workflow(body: ImportIn, state: State) -> WorkflowOut:
    """A dropped JSON (API or UI format) or a path from ComfyUI's list; bindings guessed."""
    return await _call(state.workflows.import_(body))


@router.get("/comfy/workflows")
async def comfy_workflows(state: State) -> list[ComfyWorkflowFile]:
    """ComfyUI's own workflow list (its user-data folder), newest first."""
    return await _call(state.workflows.comfy_files())
