"""Run settings (SPEC 7.1–7.3): ``/config/components|resolve|override|defaults``.

Shapes follow ``web/src/api/schemas/config.ts``: the base layer is called ``preset`` and
``sources`` gives one layer per top-level field (the most specific layer that set any part of
it).
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from drama_series_agent.api.errors import ApiError
from drama_series_agent.api.state import StudioState, get_state
from drama_series_agent.core.config import (
    CONFIG_FIELDS,
    LAYERS,
    Defaults,
    Layer,
    PresetId,
    Resolved,
    get_config,
)
from drama_series_agent.core.overrides import (
    delete_override,
    load_defaults,
    put_override,
    resolve_component,
    save_defaults,
)
from drama_series_agent.modelhub.catalog import Catalog, catalog, model_options

router = APIRouter(prefix="/config", tags=["config"])

State = Annotated[StudioState, Depends(get_state)]
Scope = Literal["project", "component", "item"]


class FallbackIn(BaseModel):
    enabled: bool
    on: list[Literal["error", "timeout", "qa_fail"]]
    qa_fail_n: int = Field(ge=1)
    timeout_s: int = Field(ge=1)
    to: str | None
    notify: Literal["after", "ask"]


class ConfigPatch(BaseModel):
    """Fields left out keep their value; ``null`` clears a model."""

    mode: Literal["local", "api", "hybrid", "off"] | None = None
    api_model: str | None = None
    local_model: str | None = None
    fallback: FallbackIn | None = None
    alt_order: list[str] | None = None
    per_call_cap_usd: float | None = Field(default=None, ge=0)
    # Workflow branches on / off by id (SPEC 6.4.8); ``null`` goes back to the default.
    branches: dict[str, bool | None] | None = None


class OverrideBody(BaseModel):
    scope: Scope
    scope_id: str | None = None  # the item for scope=item, e.g. ``shot:1-05``
    component_id: str
    data: ConfigPatch


class ResolvedOut(BaseModel):
    component_id: str
    item: str | None
    values: dict[str, Any]
    sources: dict[str, Layer]


class DefaultsOut(BaseModel):
    preset: PresetId
    fallback_notify: Literal["after", "ask"]


class DefaultsPatch(BaseModel):
    preset: PresetId | None = None
    fallback_notify: Literal["after", "ask"] | None = None


def _top_level(resolved: Resolved) -> dict[str, Layer]:
    """One source per field: the most specific layer that set the field or any part of it."""
    out: dict[str, Layer] = {}
    for name in CONFIG_FIELDS:
        layers = [
            layer
            for path, layer in resolved.sources.items()
            if path == name or path.startswith(f"{name}.")
        ]
        out[name] = max(layers, key=LAYERS.index) if layers else "preset"
    return out


def _known_component(component_id: str) -> None:
    try:
        get_config().components.component(component_id)
    except KeyError:
        raise ApiError(404, "unknown_component", id=component_id) from None


def _check_models(data: dict[str, Any]) -> None:
    known = {m.key for m in model_options(get_config())}
    keys = [data.get("api_model"), data.get("local_model"), *(data.get("alt_order") or [])]
    if isinstance(data.get("fallback"), dict):
        keys.append(data["fallback"].get("to"))
    for key in keys:
        if key is not None and key not in known:
            raise ApiError(422, "unknown_model", key=key)


async def _resolved(state: StudioState, component_id: str, item: str | None) -> ResolvedOut:
    caps = await state.setup.capabilities()
    async with state.db.session() as session:
        resolved = await resolve_component(
            session, component_id, item=item, config=get_config(), caps=caps
        )
    return ResolvedOut(
        component_id=component_id, item=item, values=resolved.values, sources=_top_level(resolved)
    )


@router.get("/components")
async def get_components(state: State) -> Catalog:
    return catalog(get_config(), await state.setup.capabilities())


@router.get("/resolve")
async def get_resolve(
    state: State,
    component: Annotated[str, Query(max_length=64)],
    item: Annotated[str | None, Query(max_length=200)] = None,
) -> ResolvedOut:
    _known_component(component)
    return await _resolved(state, component, item)


@router.put("/override")
async def put_config_override(body: OverrideBody, state: State) -> ResolvedOut:
    """Merge ``data`` into the override at that level; returns the re-resolved settings.

    A project-level override applies to every component, so it is stored without one.
    """
    _known_component(body.component_id)
    if body.scope == "item" and not body.scope_id:
        raise ApiError(422, "scope_id_required")
    data = body.data.model_dump(exclude_unset=True)
    _check_models(data)
    async with state.db.session() as session:
        await put_override(
            session,
            scope=body.scope,
            scope_id=body.scope_id if body.scope == "item" else None,
            component_id=None if body.scope == "project" else body.component_id,
            data=data,
            merge=True,
        )
    item = body.scope_id if body.scope == "item" else None
    return await _resolved(state, body.component_id, item)


@router.delete("/override")
async def delete_config_override(
    state: State,
    scope: Scope,
    component_id: Annotated[str, Query(max_length=64)],
    scope_id: Annotated[str | None, Query(max_length=200)] = None,
) -> ResolvedOut:
    """「恢复成预设」: drop the override at that level (a missing one is not an error)."""
    _known_component(component_id)
    async with state.db.session() as session:
        await delete_override(
            session,
            scope=scope,
            scope_id=scope_id if scope == "item" else None,
            component_id=None if scope == "project" else component_id,
        )
    return await _resolved(state, component_id, scope_id if scope == "item" else None)


@router.get("/defaults")
async def get_defaults(state: State) -> DefaultsOut:
    async with state.db.session() as session:
        d = await load_defaults(session)
    return DefaultsOut(preset=d.preset, fallback_notify=d.fallback_notify)


@router.put("/defaults")
async def put_defaults(body: DefaultsPatch, state: State) -> DefaultsOut:
    """Switch the preset or the fallback behaviour. Components changed by hand keep their
    overrides (SPEC 7.2: the preset is only the base layer)."""
    async with state.db.session() as session:
        current = await load_defaults(session)
        d = await save_defaults(
            session,
            Defaults(
                preset=body.preset or current.preset,
                fallback_notify=body.fallback_notify or current.fallback_notify,
            ),
        )
    return DefaultsOut(preset=d.preset, fallback_notify=d.fallback_notify)
