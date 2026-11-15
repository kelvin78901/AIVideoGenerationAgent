"""An episode's shots (M4, SPEC 9.1): ``GET /episodes/{id}/shots``, ``PATCH /shots/{id}``,
``POST /shots/{id}/split|merge``, ``POST /shots/{id}/keyframe/upload`` and 镜头参考图
``/shots/{id}/refs`` (M5.5, ``shots/upload.py``). Edits append an ``edit`` version of the
episode's 分镜规划 and adopt it (``shots/service.py``)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, UploadFile

from drama_series_agent.api.state import StudioState, get_state
from drama_series_agent.core.jobs import job_public
from drama_series_agent.media.image import MAX_UPLOAD_BYTES, Rect
from drama_series_agent.pipeline.errors import PipelineError
from drama_series_agent.pipeline.schema import ProductOut
from drama_series_agent.shots.schema import ShotChecksOut, ShotOut, ShotPatch, ShotSplitIn
from drama_series_agent.shots.upload import add_shot_ref, remove_shot_ref, upload_keyframe

router = APIRouter(tags=["shots"])

State = Annotated[StudioState, Depends(get_state)]


@router.get("/episodes/{episode_id}/shots")
async def list_shots(episode_id: str, state: State) -> list[ShotOut]:
    """The plan's version on screen; empty before the first run."""
    return await state.shots.of_episode(episode_id)


@router.get("/episodes/{episode_id}/shot-checks")
async def shot_checks(episode_id: str, state: State) -> ShotChecksOut:
    """分镜检查 (M5.5): the rules' findings now, and the model's last check (only warnings)."""
    return await state.shots.checks(episode_id)


@router.post("/episodes/{episode_id}/shot-checks")
async def run_shot_checks(episode_id: str, state: State) -> dict[str, Any]:
    """「检查」 → the queued model check of the episode's plan."""
    return job_public(await state.shots.run_checks(episode_id))


@router.patch("/shots/{shot_id}")
async def patch_shot(shot_id: str, body: ShotPatch, state: State) -> ShotOut:
    """改镜头设定; 422 ``duration_below_audio {min_s}`` shorter than its lines' audio."""
    return await state.shots.patch(shot_id, body)


@router.post("/shots/{shot_id}/split")
async def split_shot(shot_id: str, body: ShotSplitIn, state: State) -> list[ShotOut]:
    """拆分: the episode's shots after it."""
    return await state.shots.split(shot_id, body)


@router.post("/shots/{shot_id}/merge")
async def merge_shot(shot_id: str, state: State) -> list[ShotOut]:
    """和同一场的下一个镜头合并; 422 ``no_next_shot``."""
    return await state.shots.merge(shot_id)


@router.post("/shots/{shot_id}/keyframe/upload")
async def upload_shot_keyframe(
    shot_id: str,
    state: State,
    file: Annotated[UploadFile, File()],
    x: Annotated[int | None, Form()] = None,
    y: Annotated[int | None, Form()] = None,
    w: Annotated[int | None, Form()] = None,
    h: Annotated[int | None, Form()] = None,
) -> ProductOut:
    """「上传关键帧」 (PNG, JPEG, WebP): cut to the frame (the box ``x, y, w, h`` in the
    picture's pixels, else centred), at the delivery size, one candidate, picked; ``low_res`` in
    the payload when the cut-out is smaller than the draft tier (only a warning)."""
    given = [v for v in (x, y, w, h) if v is not None]
    if given and len(given) != 4:
        raise PipelineError(422, "invalid_crop", reason="give x, y, w and h together")
    box = Rect(x, y, w, h) if x is not None and y is not None and w and h else None
    if given and box is None:
        raise PipelineError(422, "invalid_crop", reason="empty box")
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    kf = await upload_keyframe(
        state.db, state.products, state.store, shot_id, file.filename or "", data, box
    )
    return await state.products.get(kf.id)


@router.post("/shots/{shot_id}/refs")
async def add_shot_picture(
    shot_id: str,
    state: State,
    file: Annotated[UploadFile, File()],
    purpose: Annotated[str, Form(max_length=16)] = "composition",
) -> ProductOut:
    """镜头参考图 (M5.5): a picture for this shot's ``composition`` / ``pose`` / ``light`` /
    ``style``; the ``shot_refs`` product, its new version adopted (at most 4). A continuous
    shot has no keyframe to guide (409 ``no_keyframe``)."""
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    pid = await add_shot_ref(
        state.db, state.products, state.store, shot_id, purpose, file.filename or "", data
    )
    return await state.products.get(pid)


@router.delete("/shots/{shot_id}/refs/{idx}")
async def remove_shot_picture(shot_id: str, idx: int, state: State) -> ProductOut:
    return await state.products.get(await remove_shot_ref(state.db, state.products, shot_id, idx))
