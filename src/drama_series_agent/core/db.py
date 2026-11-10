"""SQLite engine (WAL), sessions and migrations."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import anyio
from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from drama_series_agent.core.paths import database_path

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def _set_sqlite_pragmas(dbapi_conn: Any, _record: Any) -> None:
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA busy_timeout=5000")
    cur.close()


def sync_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def alembic_config(path: Path) -> AlembicConfig:
    cfg = AlembicConfig()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", sync_url(path))
    return cfg


def migrate(path: Path, revision: str = "head") -> None:
    """Upgrade the database at ``path``. Blocking: run it in a thread from async code."""
    path.parent.mkdir(parents=True, exist_ok=True)
    command.upgrade(alembic_config(path), revision)


def downgrade(path: Path, revision: str) -> None:
    command.downgrade(alembic_config(path), revision)


class Database:
    """Owns the async engine and session factory for one SQLite file."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or database_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.engine: AsyncEngine = create_async_engine(
            f"sqlite+aiosqlite:///{self.path.as_posix()}",
            connect_args={"timeout": 30},
            # A connection broken by a cancelled request is replaced instead of handed out.
            pool_pre_ping=True,
        )
        event.listen(self.engine.sync_engine, "connect", _set_sqlite_pragmas)
        self._sessions = async_sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """A session whose work Starlette cannot cancel halfway.

        Starlette cancels a streaming response (SSE) through an anyio cancel scope when the
        browser leaves, and anyio cancels level-triggered: a query cancelled midway makes
        SQLAlchemy terminate the connection, that await is cancelled too, and the connection
        is left holding its transaction and SQLite's write lock, so every writer after it
        waits (CI's e2e hangs, M5 step 12c). Shielded, the block finishes (it is short) and
        the cancellation lands on the next await outside it. Native ``task.cancel()`` (job
        cancel, ``asyncio.timeout``) still goes through.
        """
        with anyio.CancelScope(shield=True):
            async with self._sessions() as session:
                yield session

    async def dispose(self) -> None:
        await self.engine.dispose()
