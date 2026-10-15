"""``/api/v1/jobs``: list, inspect, cancel and confirm jobs."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from drama_series_agent.api.errors import ApiError
from drama_series_agent.api.state import StudioState, get_state
from drama_series_agent.core.jobs import STATES, JobStateError, job_public

router = APIRouter(prefix="/jobs", tags=["jobs"])

State = Annotated[StudioState, Depends(get_state)]


@router.get("")
async def list_jobs(
    state: State,
    job_state: Annotated[str | None, Query(alias="state")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[dict[str, Any]]:
    if job_state is not None and job_state not in STATES:
        raise ApiError(422, "invalid_job_state", state=job_state)
    return [job_public(j) for j in await state.jobs.list(state=job_state, limit=limit)]


@router.get("/{job_id}")
async def get_job(job_id: str, state: State) -> dict[str, Any]:
    job = await state.jobs.get(job_id)
    if job is None:
        raise ApiError(404, "job_not_found", id=job_id)
    return job_public(job)


@router.post("/{job_id}/cancel")
async def cancel_job(job_id: str, state: State) -> dict[str, Any]:
    try:
        return job_public(await state.jobs.cancel(job_id))
    except KeyError:
        raise ApiError(404, "job_not_found", id=job_id) from None
    except JobStateError as exc:
        raise ApiError(409, "job_invalid_state", id=job_id, state=exc.state) from None


@router.post("/{job_id}/confirm")
async def confirm_job(job_id: str, state: State) -> dict[str, Any]:
    try:
        return job_public(await state.jobs.confirm(job_id))
    except KeyError:
        raise ApiError(404, "job_not_found", id=job_id) from None
    except JobStateError as exc:
        raise ApiError(409, "job_invalid_state", id=job_id, state=exc.state) from None
