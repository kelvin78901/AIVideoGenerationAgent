from __future__ import annotations

from sqlmodel import func, select

from drama_series_agent.core.db import Database
from drama_series_agent.core.models_db import OutputSpecRow, Series
from drama_series_agent.studio.demo import DEMO_SERIES_ID, seed_demo


async def _count(db: Database) -> tuple[int, int]:
    async with db.session() as session:
        series = (await session.exec(select(func.count()).select_from(Series))).one()
        specs = (await session.exec(select(func.count()).select_from(OutputSpecRow))).one()
    return series, specs


async def test_seed_demo_is_idempotent(studio_db: Database) -> None:
    assert await seed_demo(studio_db) is True
    assert await seed_demo(studio_db) is False
    assert await _count(studio_db) == (1, 1)
    async with studio_db.session() as session:
        series = await session.get(Series, DEMO_SERIES_ID)
        spec = await session.get(OutputSpecRow, DEMO_SERIES_ID)
    assert series is not None and series.title == "雨停之前" and series.slug == "rain-stops"
    assert spec is not None
    assert (spec.platform, spec.aspect, spec.delivery, spec.fps) == ("cn", "9:16", "1080p", 24)
    assert spec.audio_json == {"sample_rate": 48000, "lufs": -14, "peak_dbtp": -1}
    assert spec.locked_at is not None and spec.locked_at.isoformat() == "2026-10-14T03:02:00+00:00"


async def test_seed_skips_when_any_series_exists(studio_db: Database) -> None:
    async with studio_db.session() as session:
        session.add(Series(id="mine", slug="mine", title="Mine"))
        await session.commit()
    assert await seed_demo(studio_db) is False
    assert await _count(studio_db) == (1, 0)
