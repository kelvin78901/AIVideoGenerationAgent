"""``/series/{id}/novel``: import a .txt / .docx (SPEC 4.1), read it chapter by chapter and
edit a chapter by paragraphs (M2 step 7b)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile

from drama_series_agent.api.state import StudioState, get_state
from drama_series_agent.novel.parse import MAX_UPLOAD_BYTES
from drama_series_agent.novel.schema import ChapterEditIn, NovelImportOut, NovelOut

router = APIRouter(tags=["novel"])

State = Annotated[StudioState, Depends(get_state)]


@router.post("/series/{series_id}/novel")
async def import_novel(
    series_id: str,
    state: State,
    file: Annotated[UploadFile, File()],
    rights_confirmed: Annotated[bool, Form()] = False,
    dry_run: Annotated[bool, Form()] = False,
) -> NovelImportOut:
    """``dry_run`` only reports what was found (the import dialog's chapter preview).

    Importing needs ``rights_confirmed`` (the user owns the adaptation rights, SPEC 15).
    """
    # One byte over the limit is enough to refuse it (413 file_too_large).
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    name = file.filename or ""
    if dry_run:
        return await state.novel.preview(series_id, name, data)
    return await state.novel.import_novel(series_id, name, data, rights_confirmed=rights_confirmed)


@router.get("/series/{series_id}/novel")
async def get_novel(
    series_id: str, state: State, chapter: Annotated[int | None, Query(ge=0)] = None
) -> NovelOut:
    """The novel in use and the paragraphs of one chapter (``chapter``, 0-based; the first)."""
    return await state.novel.get(series_id, chapter)


@router.put("/series/{series_id}/novel/chapters/{idx}")
async def edit_chapter(series_id: str, idx: int, body: ChapterEditIn, state: State) -> NovelOut:
    """逐段编辑: the chapter's title and paragraphs as the user left them → a new source and an
    adopted ``edit`` version (nothing when unchanged); returns that chapter."""
    return await state.novel.edit_chapter(series_id, idx, body.title, body.paragraphs)
