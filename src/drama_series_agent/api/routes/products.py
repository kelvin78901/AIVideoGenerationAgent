"""Products and versions (SPEC 4.2, 9.1): ``/products``, ``/versions``."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field

from drama_series_agent.api.state import StudioState, get_state
from drama_series_agent.core.jobs import job_public
from drama_series_agent.pipeline.schema import ProductOut

router = APIRouter(tags=["products"])

State = Annotated[StudioState, Depends(get_state)]


class RunParams(BaseModel):
    """What a component reads besides the prompt (M3): a task such as ``views``, the draft
    (version + candidate) an API final starts from."""

    model_config = ConfigDict(extra="forbid")

    task: str | None = Field(default=None, max_length=32)
    source_version_id: str | None = Field(default=None, max_length=64)
    source_idx: int | None = Field(default=None, ge=0)


class RunBody(BaseModel):
    mode: Literal["run", "rerun", "switch"]
    model: str | None = None
    intent: str | None = None
    compiled: str | None = None  # a hand-edited compiled layer (「保存并重跑」)
    count: int | None = Field(default=None, ge=1, le=8)  # None: the component's (first takes)
    # ``api``: hybrid mode's 「用 API 出终版」 (SPEC 7.3).
    where: Literal["local", "api"] | None = None
    params: RunParams | None = None


class PickBody(BaseModel):
    version_id: str
    idx: int = Field(ge=0)


class VersionPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rating: int | None = Field(ge=1, le=5)


class PromptBody(BaseModel):
    intent: str
    compiled: str | None  # None = compile from the intent


class CompileBody(BaseModel):
    intent: str
    model: str | None = None


@router.get("/products")
async def list_products(
    state: State,
    owner: Annotated[str | None, Query(max_length=200)] = None,
    component: Annotated[str | None, Query(max_length=64)] = None,
) -> list[ProductOut]:
    """``?owner=<type>:<id>&component=<id>``, oldest product first."""
    return await state.products.find(owner=owner, component=component)


@router.get("/products/{product_id}")
async def get_product(product_id: str, state: State) -> ProductOut:
    return await state.products.get(product_id)


@router.post("/versions/{version_id}/set-current")
async def set_current(version_id: str, state: State) -> ProductOut:
    return await state.products.set_current(version_id)


@router.post("/versions/{version_id}/adopt")
async def adopt(version_id: str, state: State) -> ProductOut:
    """Adopt (and show) a version; 409 ``product_locked`` while a gate has it locked."""
    return await state.products.adopt(version_id)


@router.post("/products/{product_id}/unadopt")
async def unadopt(product_id: str, state: State) -> ProductOut:
    """「取消采纳」 a take; 409 ``product_locked`` while locked."""
    return await state.products.unadopt(product_id)


@router.patch("/versions/{version_id}")
async def patch_version(version_id: str, body: VersionPatch, state: State) -> ProductOut:
    """数字键打分 on the take wall."""
    return await state.products.rate(version_id, body.rating)


@router.post("/products/{product_id}/lock")
async def lock(product_id: str, state: State) -> ProductOut:
    """Lock the adopted version (409 ``nothing_adopted`` if there is none)."""
    return await state.products.lock(product_id)


@router.post("/products/{product_id}/unlock")
async def unlock(product_id: str, state: State) -> ProductOut:
    return await state.products.unlock(product_id)


@router.post("/products/{product_id}/run")
async def run_product(product_id: str, body: RunBody, state: State) -> dict[str, Any]:
    """重跑 / 不满意换一个 / 保存并重跑 (SPEC 7.4) → the queued ``product.run`` job."""
    job = await state.runs.start(
        product_id,
        body.mode,
        model=body.model,
        intent=body.intent,
        compiled=body.compiled,
        count=body.count,
        where=body.where,
        params=body.params.model_dump(exclude_none=True) if body.params else None,
    )
    return job_public(job)


@router.post("/products/{product_id}/pick")
async def pick(product_id: str, body: PickBody, state: State) -> ProductOut:
    """「选这个」: candidate ``idx`` of a version (409 ``product_locked`` while locked)."""
    return await state.products.set_pick(product_id, body.version_id, body.idx)


@router.put("/products/{product_id}/prompt")
async def save_prompt(product_id: str, body: PromptBody, state: State) -> ProductOut:
    """「只保存」: the next run uses this prompt."""
    return await state.runs.save_prompt(product_id, body.intent, body.compiled)


@router.post("/products/{product_id}/compile")
async def compile_prompt(product_id: str, body: CompileBody, state: State) -> dict[str, str]:
    """Preview of the compiled layer for an intent (PromptEditor, debounced)."""
    return await state.runs.compile_preview(product_id, body.intent, body.model)
