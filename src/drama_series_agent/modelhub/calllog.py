"""Writes and reads ``model_call`` rows — the dashboard's only data source (SPEC 10)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func
from sqlmodel import col, select

from drama_series_agent.core.db import Database
from drama_series_agent.core.models_db import ModelCall


async def record(db: Database, row: ModelCall) -> ModelCall:
    async with db.session() as session:
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return row


async def total_cost(
    db: Database,
    *,
    series_id: str | None = None,
    episode_id: str | None = None,
    job_id: str | None = None,
) -> float:
    stmt = select(func.coalesce(func.sum(ModelCall.cost_usd), 0.0)).where(
        col(ModelCall.billed).is_(True)
    )
    if series_id is not None:
        stmt = stmt.where(ModelCall.series_id == series_id)
    if episode_id is not None:
        stmt = stmt.where(ModelCall.episode_id == episode_id)
    if job_id is not None:
        stmt = stmt.where(ModelCall.job_id == job_id)
    async with db.session() as session:
        value = (await session.exec(stmt)).one()
    return float(value)


async def unpriced_calls(
    db: Database, *, series_id: str | None = None, episode_id: str | None = None
) -> int:
    """Billed calls to models without a known price: the spend shown leaves them out."""
    stmt = select(func.count()).where(
        col(ModelCall.billed).is_(True), col(ModelCall.unpriced).is_(True)
    )
    if series_id is not None:
        stmt = stmt.where(ModelCall.series_id == series_id)
    if episode_id is not None:
        stmt = stmt.where(ModelCall.episode_id == episode_id)
    async with db.session() as session:
        return int((await session.exec(stmt)).one())


async def recent(db: Database, limit: int = 50) -> list[ModelCall]:
    async with db.session() as session:
        stmt = select(ModelCall).order_by(col(ModelCall.id).desc()).limit(limit)
        return list((await session.exec(stmt)).all())


def call_public(row: ModelCall) -> dict[str, Any]:
    data = row.model_dump()
    for key in ("queued_at", "started_at", "finished_at"):
        value = data.get(key)
        data[key] = value.isoformat() if value is not None else None
    return data
