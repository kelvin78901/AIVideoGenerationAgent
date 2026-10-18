"""Database side of configuration: read ``config_override`` rows and resolve against them."""

from __future__ import annotations

from typing import Any, cast

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from drama_series_agent.core.capabilities import Capabilities
from drama_series_agent.core.config import Layer, Override, Resolved, StudioConfig, resolve
from drama_series_agent.core.models_db import ConfigOverride, utcnow

VALID_SCOPES: tuple[Layer, ...] = ("project", "component", "item")


async def load_overrides(session: AsyncSession) -> list[Override]:
    rows = (await session.exec(select(ConfigOverride).order_by(col(ConfigOverride.id)))).all()
    return [
        Override(
            scope=cast(Layer, row.scope),
            scope_id=row.scope_id,
            component_id=row.component_id,
            data=row.data_json,
        )
        for row in rows
    ]


async def put_override(
    session: AsyncSession,
    *,
    scope: str,
    data: dict[str, Any],
    scope_id: str | None = None,
    component_id: str | None = None,
) -> ConfigOverride:
    """Insert or replace the override for (scope, scope_id, component_id)."""
    if scope not in VALID_SCOPES:
        raise ValueError(f"invalid scope: {scope}")
    stmt = select(ConfigOverride).where(
        ConfigOverride.scope == scope,
        ConfigOverride.scope_id == scope_id,
        ConfigOverride.component_id == component_id,
    )
    row = (await session.exec(stmt)).first()
    if row is None:
        row = ConfigOverride(scope=scope, scope_id=scope_id, component_id=component_id)
    row.data_json = data
    row.updated_at = utcnow()
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def resolve_component(
    session: AsyncSession,
    component_id: str,
    *,
    item: str | None = None,
    config: StudioConfig | None = None,
    caps: Capabilities | None = None,
) -> Resolved:
    overrides = await load_overrides(session)
    return resolve(component_id, overrides, item=item, config=config, caps=caps)
