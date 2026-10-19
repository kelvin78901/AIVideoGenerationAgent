"""The demo series 《雨停之前》 (prototype/README.md「示例数据」).

Mock mode seeds it at startup when the database has no series yet, so pages whose MSW
handlers have been removed still have a series to show. Values match
``web/src/mocks/fixtures/demo/{series,spec}.ts``. M2's ``drama-studio demo`` builds on this.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import select

from drama_series_agent.core.config import SpecConfig, get_config
from drama_series_agent.core.db import Database
from drama_series_agent.core.models_db import Series
from drama_series_agent.spec.schema import default_row

DEMO_SERIES_ID = "demo"


async def seed_demo(db: Database, cfg: SpecConfig | None = None) -> bool:
    """Create the demo series and its spec if there is no series at all. Returns True if seeded."""
    async with db.session() as session:
        if (await session.exec(select(Series.id).limit(1))).first() is not None:
            return False
        session.add(
            Series(
                id=DEMO_SERIES_ID,
                slug="rain-stops",
                title="雨停之前",
                ui_lang="zh-CN",
                created_at=datetime(2026, 10, 14, 1, 20, tzinfo=UTC),  # 09:20 +08:00
            )
        )
        # Flush the series first: output_spec has a foreign key to it.
        await session.flush()
        spec = default_row(DEMO_SERIES_ID, cfg or get_config().spec)
        # Locked when the first keyframe (1-01 v2) was adopted, 11:02 +08:00.
        spec.locked_at = datetime(2026, 10, 14, 3, 2, tzinfo=UTC)
        session.add(spec)
        await session.commit()
    return True
