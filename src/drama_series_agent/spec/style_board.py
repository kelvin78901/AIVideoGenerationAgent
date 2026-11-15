"""剧的风格板 (M5.5 step 12; on the 成片规格 page, Kelvin 2026-11-10): pictures for the look of
the whole series, a picture set (``pipeline/pictures.py``, slot ``style_board``, owner the
series). Every keyframe sends them last, only for its colours, texture and light."""

from __future__ import annotations

from drama_series_agent.core.db import Database
from drama_series_agent.core.models_db import Series
from drama_series_agent.core.storage import BlobStore
from drama_series_agent.pipeline.errors import PipelineError
from drama_series_agent.pipeline.pictures import STYLE_BOARD, Owner, add_picture, remove_picture
from drama_series_agent.pipeline.products import ProductService


async def _owner(db: Database, series_id: str) -> Owner:
    async with db.session() as session:
        series = await session.get(Series, series_id)
    if series is None:
        raise PipelineError(404, "series_not_found", id=series_id)
    return Owner(series.id, series.id, series.title)


async def add_style(
    db: Database,
    products: ProductService,
    store: BlobStore,
    series_id: str,
    filename: str,
    data: bytes,
) -> str:
    owner = await _owner(db, series_id)
    return await add_picture(db, products, store, STYLE_BOARD, owner, "style", filename, data)


async def remove_style(db: Database, products: ProductService, series_id: str, idx: int) -> str:
    return await remove_picture(db, products, STYLE_BOARD, await _owner(db, series_id), idx)
