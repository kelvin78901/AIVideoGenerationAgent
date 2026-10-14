"""Alembic environment. Migrations run on a plain (sync) SQLite connection."""

from __future__ import annotations

from typing import Any, Literal

from alembic import context
from alembic.autogenerate.api import AutogenContext
from sqlalchemy import create_engine, pool
from sqlmodel import SQLModel
from sqlmodel.sql.sqltypes import AutoString

from drama_series_agent.core import models_db  # noqa: F401  (registers tables on the metadata)
from drama_series_agent.core.db import sync_url
from drama_series_agent.core.models_db import UtcDateTime
from drama_series_agent.core.paths import database_path

config = context.config
target_metadata = SQLModel.metadata
if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", sync_url(database_path()))


def render_item(type_: str, obj: Any, autogen_context: AutogenContext) -> str | Literal[False]:
    """Keep generated migrations free of imports from our own code and SQLModel."""
    if type_ == "type" and isinstance(obj, AutoString):
        return "sa.String()"
    if type_ == "type" and isinstance(obj, UtcDateTime):
        return "sa.DateTime(timezone=True)"
    return False


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
        render_item=render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = config.get_main_option("sqlalchemy.url")
    assert url is not None
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # SQLite needs batch mode for ALTER
            render_item=render_item,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
