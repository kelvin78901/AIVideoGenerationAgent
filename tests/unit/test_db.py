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
M1_TABLES = {
    "series", "output_spec", "machine_profile", "installed_item", "comfy_env", "comfy_snapshot"
}  # fmt: skip
M2_TABLES = {"product", "product_version", "dependency", "gate_decision"}
ALL_TABLES = M0_TABLES | M1_TABLES | M2_TABLES


def _tables(path: Path) -> set[str]:
    with sqlite3.connect(path) as conn:
        rows = conn.execute("select name from sqlite_master where type='table'").fetchall()
    return {r[0] for r in rows} - {"alembic_version"}


def test_migrate_up_and_down(tmp_path: Path) -> None:
    db = tmp_path / "t.db"
    migrate(db)
    assert _tables(db) == ALL_TABLES
    downgrade(db, "0006")
    assert _tables(db) == M0_TABLES | M1_TABLES
    downgrade(db, "0001")
    assert _tables(db) == M0_TABLES
    downgrade(db, "base")
    assert _tables(db) == set()
    migrate(db)
    assert _tables(db) == ALL_TABLES


def test_rollbacks_from_before_the_check_are_unchecked(tmp_path: Path) -> None:
    """0006: a rollback requested before step 8c was never checked; it is not called done."""
    db = tmp_path / "t.db"
    migrate(db, "0005")
    with sqlite3.connect(db) as conn:
        conn.execute(
            "insert into comfy_snapshot (id, profile_id, manager_name, reason, changes_json,"
            " created_at, restored_at) values ('s1', 'local', 'snap', 'install', '[]',"
            " '2026-10-18 09:30:00', '2026-10-18 10:00:00'), ('s2', 'local', 'snap2', 'manual',"
            " '[]', '2026-10-18 11:00:00', null)"
        )
    migrate(db)
    with sqlite3.connect(db) as conn:
        rows = conn.execute(
            "select id, restore_state, restore_requested_at, restored_at from comfy_snapshot"
            " order by id"
        ).fetchall()
    assert rows == [
        ("s1", "unchecked", "2026-10-18 10:00:00", None),
        ("s2", None, None, None),
    ]
    downgrade(db, "0005")
    with sqlite3.connect(db) as conn:
        assert conn.execute(
            "select restored_at from comfy_snapshot where id = 's1'"
        ).fetchone() == ("2026-10-18 10:00:00",)


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
