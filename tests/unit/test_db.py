from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine
from sqlmodel import SQLModel, select

from drama_series_agent.core import models_db
from drama_series_agent.core.db import Database, downgrade, migrate, sync_url
from drama_series_agent.core.models_db import Job, ModelCall
from drama_series_agent.core.overrides import put_override, resolve_component
from drama_series_agent.core.paths import database_path

M0_TABLES = {"job", "model_call", "config_override", "provider_account", "custom_model", "event"}
M1_TABLES = {"series", "output_spec", "machine_profile", "installed_item"}
ALL_TABLES = M0_TABLES | M1_TABLES


def _tables(path: Path) -> set[str]:
    with sqlite3.connect(path) as conn:
        rows = conn.execute("select name from sqlite_master where type='table'").fetchall()
    return {r[0] for r in rows} - {"alembic_version"}


def test_migrate_up_and_down(tmp_path: Path) -> None:
    db = tmp_path / "t.db"
    migrate(db)
    assert _tables(db) == ALL_TABLES
    downgrade(db, "0001")
    assert _tables(db) == M0_TABLES
    downgrade(db, "base")
    assert _tables(db) == set()
    migrate(db)
    assert _tables(db) == ALL_TABLES


def test_models_match_migrations(tmp_path: Path) -> None:
    db = tmp_path / "t.db"
    migrate(db)
    assert models_db  # tables registered on SQLModel.metadata
    engine = create_engine(sync_url(db))
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn, opts={"compare_type": True})
        diff = compare_metadata(ctx, SQLModel.metadata)
    engine.dispose()
    assert diff == []


async def test_wal_and_timezone_roundtrip() -> None:
    path = database_path()
    await asyncio.to_thread(migrate, path)
    db = Database(path)
    try:
        async with db.session() as s:
            mode = (await s.exec(select(1))).one()  # opens a connection → pragmas applied
            assert mode == 1
            job = Job(kind="mock", queue="cpu")
            s.add(job)
            s.add(ModelCall(model_key="mock/llm", where="api", status="success", job_id=job.id))
            await s.commit()
        async with db.session() as s:
            loaded = (await s.exec(select(Job))).one()
            assert loaded.created_at.tzinfo is not None
            assert loaded.params_json == {}
        with sqlite3.connect(path) as conn:
            assert conn.execute("pragma journal_mode").fetchone()[0] == "wal"
    finally:
        await db.dispose()


async def test_override_roundtrip() -> None:
    path = database_path()
    await asyncio.to_thread(migrate, path)
    db = Database(path)
    try:
        async with db.session() as s:
            await put_override(s, scope="component", component_id="script", data={"mode": "local"})
            # upsert on the same key replaces data
            await put_override(
                s, scope="component", component_id="script", data={"api_model": "x/y"}
            )
            res = await resolve_component(s, "script")
            assert res.values["api_model"] == "x/y"
            assert res.values["mode"] == "api"
            with pytest.raises(ValueError):
                await put_override(s, scope="global", data={})
    finally:
        await db.dispose()
