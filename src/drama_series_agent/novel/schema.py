"""API shapes of the novel (front-end contract ``web/src/api/schemas/novel.ts``)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from drama_series_agent.novel.parse import ChapterDraft, ParsedNovel


class ChapterOut(BaseModel):
    id: str | None  # None in a dry run
    idx: int
    # The heading line; None for text before the first heading or a part of a length split.
    title: str | None
    start: int
    end: int
    para_start: int  # number of the first paragraph, counted across the book
    para_count: int
    chars: int


class SourceOut(BaseModel):
    id: str
    filename: str
    sha256: str
    encoding: str
    split_by: Literal["heading", "length"]
    chars: int
    rights_confirmed_at: datetime
    imported_at: datetime


class ChapterEditIn(BaseModel):
    """``PUT /series/{id}/novel/chapters/{idx}``: the chapter as the user left it."""

    model_config = ConfigDict(extra="forbid")

    # None or empty: no title (text before the first heading, a part of a length split).
    title: str | None = Field(default=None, max_length=200)
    paragraphs: list[Annotated[str, Field(max_length=20000)]] = Field(max_length=5000)


class ParagraphOut(BaseModel):
    idx: int
    text: str
    start: int
    end: int


class NovelOut(BaseModel):
    """``GET /series/{id}/novel``: the adopted source and one chapter's paragraphs."""

    series_id: str
    source: SourceOut | None  # None until a novel is imported
    chapters: list[ChapterOut]
    chapter: int | None  # idx of the chapter whose paragraphs are listed
    paragraphs: list[ParagraphOut]


class NovelImportOut(BaseModel):
    """``POST /series/{id}/novel``: what was found (``dry_run``) or imported."""

    dry_run: bool
    # The text is the same as the current source's: nothing was added.
    unchanged: bool
    source_id: str | None
    filename: str
    encoding: str
    split_by: Literal["heading", "length"]
    chars: int
    chapters: list[ChapterOut]
    # ``dry_run``: the file as kept for replacing a confirmed novel (``novel_replace``).
    upload_id: str | None = None


def chapter_out(c: ChapterDraft, chapter_id: str | None) -> ChapterOut:
    return ChapterOut(
        id=chapter_id,
        idx=c.idx,
        title=c.title,
        start=c.start,
        end=c.end,
        para_start=c.para_start,
        para_count=len(c.paras),
        chars=c.chars,
    )


def import_out(
    parsed: ParsedNovel,
    filename: str,
    *,
    dry_run: bool,
    source_id: str | None = None,
    chapter_ids: list[str] | None = None,
    unchanged: bool = False,
    upload_id: str | None = None,
) -> NovelImportOut:
    ids: list[str | None] = list(chapter_ids) if chapter_ids else [None] * len(parsed.chapters)
    return NovelImportOut(
        dry_run=dry_run,
        unchanged=unchanged,
        source_id=source_id,
        filename=filename,
        encoding=parsed.encoding,
        split_by=parsed.split_by,
        chars=parsed.chars,
        chapters=[chapter_out(c, i) for c, i in zip(parsed.chapters, ids, strict=True)],
        upload_id=upload_id,
    )
