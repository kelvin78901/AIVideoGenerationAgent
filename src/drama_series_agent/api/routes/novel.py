"""``/series/{id}/novel``: import a .txt / .docx (SPEC 4.1) and read it chapter by chapter."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile

from drama_series_agent.api.state import StudioState, get_state
from drama_series_agent.novel.parse import MAX_UPLOAD_BYTES
from drama_series_agent.novel.schema import NovelImportOut, NovelOut

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
