"""Database side of configuration: ``config_override`` rows, the global defaults, resolution."""

from __future__ import annotations

from typing import Any, cast, get_args

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel.sql.expression import SelectOfScalar

from drama_series_agent.core.capabilities import Capabilities
from drama_series_agent.core.config import (
    Defaults,
    Layer,
    Override,
    PresetId,
    Resolved,
    StudioConfig,
    resolve,
)
from drama_series_agent.core.models_db import AppSetting, ConfigOverride, utcnow

VALID_SCOPES: tuple[Layer, ...] = ("project", "component", "item")
DEFAULTS_KEY = "config.defaults"


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


def _where(
    scope: str, scope_id: str | None, component_id: str | None
) -> SelectOfScalar[ConfigOverride]:
    return select(ConfigOverride).where(
        ConfigOverride.scope == scope,
        ConfigOverride.scope_id == scope_id,
        ConfigOverride.component_id == component_id,
    )


async def put_override(
    session: AsyncSession,
    *,
    scope: str,
    data: dict[str, Any],
    scope_id: str | None = None,
    component_id: str | None = None,
    merge: bool = False,
) -> ConfigOverride:
    """Insert or replace the override for (scope, scope_id, component_id).

    ``merge``: keep the row's other top-level fields (the UI changes one field at a time).
    """
    if scope not in VALID_SCOPES:
        raise ValueError(f"invalid scope: {scope}")
    row = (await session.exec(_where(scope, scope_id, component_id))).first()
    if row is None:
        row = ConfigOverride(scope=scope, scope_id=scope_id, component_id=component_id)
    row.data_json = {**row.data_json, **data} if merge else data
    row.updated_at = utcnow()
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def delete_override(
    session: AsyncSession, *, scope: str, scope_id: str | None, component_id: str | None
) -> bool:
    row = (await session.exec(_where(scope, scope_id, component_id))).first()
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    return True


async def load_defaults(session: AsyncSession) -> Defaults:
    row = await session.get(AppSetting, DEFAULTS_KEY)
    data = row.value_json if row else {}
    preset = data.get("preset")
    notify = data.get("fallback_notify")
    return Defaults(
        preset=cast(PresetId, preset) if preset in get_args(PresetId) else "balanced",
        fallback_notify="ask" if notify == "ask" else "after",
    )


async def save_defaults(session: AsyncSession, defaults: Defaults) -> Defaults:
    row = await session.get(AppSetting, DEFAULTS_KEY) or AppSetting(key=DEFAULTS_KEY)
    row.value_json = {"preset": defaults.preset, "fallback_notify": defaults.fallback_notify}
    row.updated_at = utcnow()
    session.add(row)
    await session.commit()
    return defaults


async def resolve_component(
    session: AsyncSession,
    component_id: str,
    *,
    item: str | None = None,
    config: StudioConfig | None = None,
    caps: Capabilities | None = None,
) -> Resolved:
    overrides = await load_overrides(session)
    defaults = await load_defaults(session)
    return resolve(component_id, overrides, item=item, config=config, caps=caps, defaults=defaults)
