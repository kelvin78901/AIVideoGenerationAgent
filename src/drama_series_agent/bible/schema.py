"""API shapes of the story bible (front-end contract ``web/src/api/schemas/novel.ts``)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

BibleKind = Literal["character", "location", "prop", "event", "relation"]


class SourceSpanOut(BaseModel):
    source_id: str
    start: int
    end: int


class BibleEntityOut(BaseModel):
    id: str
    series_id: str
    kind: BibleKind
    name: str
    aliases: list[str]
    # Kind-specific fields; ``summary`` is the one-line description the novel page shows.
    data: dict[str, Any]
    paras: list[int]  # paragraph numbers across the book, 0-based
    source_spans: list[SourceSpanOut]
    frozen: bool


class MergeSuggestionOut(BaseModel):
    """「可能是同一个」: two entries the model judged to be the same, waiting for the user."""

    id: str
    kind: BibleKind
    ids: list[str]
    reason: str


class BibleOut(BaseModel):
    """``GET /series/{id}/bible``: the version on screen (the product's current one)."""

    series_id: str
    product_id: str | None
    version_id: str | None
    # False while the version on screen is not the adopted one (「未采纳」).
    adopted: bool
    # The source the spans point into (may be an older import than the novel on screen).
    source_id: str | None
    entities: list[BibleEntityOut]
    merge_suggestions: list[MergeSuggestionOut]


class BiblePatch(BaseModel):
    """``PATCH /bible/{id}``: only the fields sent change."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=200)
    aliases: list[str] | None = None
    data: dict[str, Any] | None = None
    frozen: bool | None = None


class BibleMergeIn(BaseModel):
    """``POST /bible/merge``.

    - ``merge``: ``ids`` (two or more, one kind); the first one stays.
    - ``distinct``: ``ids`` (two) are not the same; the suggestion goes away for good.
    - ``split``: ``ids`` (one) gives up ``alias``, which becomes an entry of its own.
    """

    model_config = ConfigDict(extra="forbid")

    action: Literal["merge", "distinct", "split"]
    ids: list[str] = Field(min_length=1, max_length=20)
    alias: str | None = None


def bible_out(
    series_id: str,
    payload: dict[str, Any] | None,
    *,
    product_id: str | None = None,
    version_id: str | None = None,
    adopted: bool = True,
) -> BibleOut:
    """The pure view of a version payload (the same for adopted and unadopted versions)."""
    data = payload or {}
    return BibleOut(
        series_id=series_id,
        product_id=product_id,
        version_id=version_id,
        adopted=adopted,
        source_id=data.get("source_id"),
        entities=[entity_out(series_id, e) for e in data.get("entities") or []],
        merge_suggestions=[
            MergeSuggestionOut.model_validate(s) for s in data.get("merge_suggestions") or []
        ],
    )


def entity_out(series_id: str, e: dict[str, Any]) -> BibleEntityOut:
    return BibleEntityOut(
        id=e["id"],
        series_id=series_id,
        kind=e["kind"],
        name=e["name"],
        aliases=list(e.get("aliases") or []),
        data=dict(e.get("data") or {}),
        paras=list(e.get("paras") or []),
        source_spans=[SourceSpanOut.model_validate(s) for s in e.get("source_spans") or []],
        frozen=bool(e.get("frozen")),
    )
