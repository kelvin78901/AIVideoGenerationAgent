"""Products and versions (SPEC 4.2, 9.1): ``/products``, ``/versions``."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from drama_series_agent.api.state import StudioState, get_state
from drama_series_agent.pipeline.schema import ProductOut

router = APIRouter(tags=["products"])

State = Annotated[StudioState, Depends(get_state)]


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


@router.post("/products/{product_id}/lock")
async def lock(product_id: str, state: State) -> ProductOut:
    """Lock the adopted version (409 ``nothing_adopted`` if there is none)."""
    return await state.products.lock(product_id)


@router.post("/products/{product_id}/unlock")
async def unlock(product_id: str, state: State) -> ProductOut:
    return await state.products.unlock(product_id)
