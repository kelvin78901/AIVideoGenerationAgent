"""``/api/v1/series``: the series list, a new series (with its output spec) and renaming."""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlmodel import col, select

from drama_series_agent.api.errors import ApiError
from drama_series_agent.api.state import StudioState, get_state
from drama_series_agent.core.config import get_config
from drama_series_agent.core.models_db import Series, new_id
from drama_series_agent.spec.schema import default_row

router = APIRouter(prefix="/series", tags=["series"])

State = Annotated[StudioState, Depends(get_state)]
UiLang = Literal["zh-CN", "en"]
_SLUG_CHARS = re.compile(r"[^a-z0-9]+")


def _title(value: str | None) -> str | None:
    if value is None:
        return None
    value = " ".join(value.split())
    if not value:
        raise ValueError("title is empty")
    return value


class SeriesCreate(BaseModel):
    title: str = Field(max_length=80)
    ui_lang: UiLang = "zh-CN"

    _strip = field_validator("title")(_title)


class SeriesPatch(BaseModel):
    title: str | None = Field(default=None, max_length=80)
    ui_lang: UiLang | None = None

    _strip = field_validator("title")(_title)


def series_public(row: Series) -> dict[str, Any]:
    return row.model_dump(include={"id", "slug", "title", "ui_lang", "created_at"})


def slug_base(title: str) -> str:
    """ASCII words of the title (``Rain Stops`` → ``rain-stops``), else ``series``."""
    return _SLUG_CHARS.sub("-", title.lower()).strip("-")[:40].strip("-") or "series"


@router.get("")
async def list_series(state: State) -> list[dict[str, Any]]:
    """Newest first (the top bar's series menu)."""
    async with state.db.session() as session:
        rows = await session.exec(select(Series).order_by(col(Series.created_at).desc()))
        return [series_public(r) for r in rows.all()]


@router.post("", status_code=201)
async def create_series(body: SeriesCreate, state: State) -> dict[str, Any]:
    """A new series with the default output spec (the spec page comes next, SPEC 16.1)."""
    async with state.db.session() as session:
        base = slug_base(body.title)
        taken = set(
            (await session.exec(select(Series.slug).where(col(Series.slug).startswith(base)))).all()
        )
        slug, n = base, 2
        while slug in taken:
            slug, n = f"{base}-{n}", n + 1
        row = Series(id=new_id(), slug=slug, title=body.title, ui_lang=body.ui_lang)
        session.add(row)
        # The spec has a foreign key to the series.
        await session.flush()
        session.add(default_row(row.id, get_config().spec))
        await session.commit()
        await session.refresh(row)
    return series_public(row)


@router.get("/{series_id}")
async def get_series(series_id: str, state: State) -> dict[str, Any]:
    async with state.db.session() as session:
        row = await session.get(Series, series_id)
    if row is None:
        raise ApiError(404, "series_not_found", id=series_id)
    return series_public(row)


@router.patch("/{series_id}")
async def patch_series(series_id: str, body: SeriesPatch, state: State) -> dict[str, Any]:
    async with state.db.session() as session:
        row = await session.get(Series, series_id)
        if row is None:
            raise ApiError(404, "series_not_found", id=series_id)
        if body.title is not None:
            row.title = body.title
        if body.ui_lang is not None:
            row.ui_lang = body.ui_lang
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return series_public(row)
