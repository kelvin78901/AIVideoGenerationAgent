"""Developer endpoints behind the front end's ``/dev/jobs`` panel. Mock mode only."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from drama_series_agent.api.errors import ApiError
from drama_series_agent.api.handlers import LLM_TEST
from drama_series_agent.api.state import StudioState, get_state
from drama_series_agent.core.jobs import job_public
from drama_series_agent.modelhub import calllog
from drama_series_agent.modelhub.adapters.base import ModelError

router = APIRouter(prefix="/dev", tags=["dev"])

State = Annotated[StudioState, Depends(get_state)]


class LlmTestBody(BaseModel):
    prompt: str = "林晚撑着红伞走进楼道。"
    component_id: str = "script"
    delay_s: float = Field(default=3.0, ge=0, le=60)


@router.post("/llm-test")
async def llm_test(state: State, body: LlmTestBody | None = None) -> dict[str, Any]:
    body = body or LlmTestBody()
    if not state.registry.mock:
        raise ApiError(403, "mock_only")
    try:
        settings = await state.router.settings(body.component_id)
        key = state.router.primary_model(settings, "api")
        spec = state.registry.spec(key)
    except KeyError:
        raise ApiError(404, "unknown_component", id=body.component_id) from None
    except ModelError as exc:
        raise ApiError(422, exc.code) from None
    job = await state.jobs.enqueue(
        LLM_TEST,
        f"api:{spec.provider_id or 'unknown'}",
        body.model_dump(),
        component_id=body.component_id,
        max_attempts=1,
    )
    return job_public(job)


@router.get("/model-calls")
async def model_calls(
    state: State, limit: Annotated[int, Query(ge=1, le=500)] = 50
) -> list[dict[str, Any]]:
    return [calllog.call_public(r) for r in await calllog.recent(state.db, limit)]
