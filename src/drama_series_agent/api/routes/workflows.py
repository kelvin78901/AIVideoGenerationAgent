"""The workflow library (SPEC 6.4.6, 9.1 ``/workflows/*``) and ComfyUI's own workflow list."""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Annotated

from fastapi import APIRouter, Depends

from drama_series_agent.api.errors import ApiError
from drama_series_agent.api.state import StudioState, get_state
from drama_series_agent.setup.manifest import Message
from drama_series_agent.wflib.schema import (
    BindingOut,
    ComfyWorkflowFile,
    DepsInstalled,
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


@router.post("/workflows/check-all")
async def check_all(state: State) -> list[WorkflowOut]:
    """Every workflow against the running ComfyUI (after a node-pack install, SPEC 6.4.5)."""
    return await _call(state.workflows.check_all())


@router.post("/workflows/{workflow_id}/check")
async def check(workflow_id: str, state: State) -> WorkflowOut:
    """Missing node classes (and their packs), missing model files, broken bindings."""
    return await _call(state.workflows.check(workflow_id))


@router.post("/workflows/{workflow_id}/deps")
async def deps(workflow_id: str, state: State) -> dict[str, list[Message]]:
    """The change list installing what the last check found missing would make."""
    return {"changes": await _call(state.workflows.deps(workflow_id))}


@router.post("/workflows/{workflow_id}/deps/install")
async def install_deps(workflow_id: str, state: State) -> DepsInstalled:
    """Approved: a ComfyUI-Manager snapshot first, then the missing node packs."""
    return await _call(state.workflows.install_deps(workflow_id))


@router.post("/workflows/{workflow_id}/trial", status_code=202)
async def trial(workflow_id: str, state: State) -> WorkflowOut:
    """A trial run on the sample inputs (a GPU-queue job; ``job.updated`` reports it)."""
    return await _call(state.workflows.trial(workflow_id))
