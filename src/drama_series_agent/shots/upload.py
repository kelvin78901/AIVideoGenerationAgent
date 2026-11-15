"""「上传关键帧」 (M5.5 step 10): a picture of the user's own becomes a shot's keyframe.

``POST /shots/{id}/keyframe/upload`` takes the file and, optionally, the box the user cut out
(source pixels; none: the whole picture). The largest box of the output spec's aspect inside it
(``media/image.py:frame_rect``) is scaled to the delivery size (hard rule 10) and becomes a
version with that one candidate, ``origin=upload``, picked; the first keyframe version is
adopted as a run's would be. A cut-out smaller than the draft tier is kept with ``low_res`` in
its payload (only a warning). 「确认这个镜头」 locks it as it is (one candidate), so the take's
first frame is this picture; 「用 API 出终版」 may start from it like from a local draft.

A continuous shot has no keyframe of its own (409 ``no_keyframe``); a locked keyframe takes no
upload (409 ``product_locked``). The version records no dependencies: the picture is the user's,
nothing upstream makes it outdated.
"""

from __future__ import annotations

from typing import Any

from drama_series_agent.core.db import Database
from drama_series_agent.core.models_db import Episode, Product, Shot
from drama_series_agent.core.storage import BlobStore
from drama_series_agent.media.image import (
    MAX_UPLOAD_BYTES,
    BadCrop,
    NotAnImage,
    Rect,
    fit,
    frame_rect,
    image_info,
)
from drama_series_agent.pipeline.components.media import output_frame
from drama_series_agent.pipeline.drafts import VersionDraft, file_entry
from drama_series_agent.pipeline.errors import PipelineError
from drama_series_agent.pipeline.pictures import SHOT_REFS, Owner, add_picture, remove_picture
from drama_series_agent.pipeline.products import ProductService
from drama_series_agent.shots.service import keyframe_products
from drama_series_agent.spec.dims import dims


async def upload_keyframe(
    db: Database,
    products: ProductService,
    store: BlobStore,
    shot_id: str,
    filename: str,
    data: bytes,
    box: Rect | None = None,
) -> Product:
    """The keyframe product with the uploaded picture as its current version, picked."""
    if len(data) > MAX_UPLOAD_BYTES:
        raise PipelineError(413, "file_too_large", limit=MAX_UPLOAD_BYTES)
    try:
        info = image_info(data)
    except NotAnImage:
        raise PipelineError(422, "not_an_image", filename=filename) from None
    async with db.session() as session:
        shot = await session.get(Shot, shot_id)
        if shot is None or shot.retired:
            raise PipelineError(404, "shot_not_found", id=shot_id)
        kf = (await keyframe_products(session, [shot_id])).get(shot_id)
        if shot.shot_type == "continuous" or kf is None or kf.retired:
            raise PipelineError(409, "no_keyframe", id=shot_id)
        if kf.locked_hash:
            raise PipelineError(409, "product_locked", id=kf.id)
        frame = await output_frame(session, kf.series_id)
        intent = (kf.prompt_json or {}).get("intent") or shot.intent
    size = dims(frame["aspect"], frame["delivery"])  # type: ignore[arg-type]
    draft_size = dims(frame["aspect"], "draft")  # type: ignore[arg-type]
    try:
        crop = frame_rect(info.w, info.h, size.w, size.h, box)
    except BadCrop as exc:
        raise PipelineError(422, "invalid_crop", reason=str(exc)) from None
    try:
        picture = await fit(data, crop, size.w, size.h)
    except NotAnImage:
        raise PipelineError(422, "not_an_image", filename=filename) from None
    sha = store.put_bytes(picture)
    name = filename[:200]
    low_res = crop.w < draft_size.w or crop.h < draft_size.h
    cut: dict[str, Any] = {"x": crop.x, "y": crop.y, "w": crop.w, "h": crop.h}
    payload: dict[str, Any] = {"candidates": [{}], "crop": cut, "source": [info.w, info.h]}
    if low_res:
        payload["low_res"] = True
    draft = VersionDraft(
        payload=payload,
        files=[file_entry("candidate", sha, "image/png", w=size.w, h=size.h, idx=0)],
        intent=str(intent or ""),
        params={"filename": name, "crop": cut},
        note=name or None,
    )
    v = await products.append(kf.id, draft, origin="upload")
    await products.set_pick(kf.id, v.id, 0)
    async with db.session() as session:
        fresh = await session.get(Product, kf.id)
    assert fresh is not None
    return fresh


async def _shot_owner(db: Database, shot_id: str) -> Owner:
    async with db.session() as session:
        shot = await session.get(Shot, shot_id)
        if shot is None or shot.retired:
            raise PipelineError(404, "shot_not_found", id=shot_id)
        if shot.shot_type == "continuous":  # drawn from the shot before: no keyframe to guide
            raise PipelineError(409, "no_keyframe", id=shot_id)
        episode = await session.get(Episode, shot.episode_id)
    label = f"{episode.idx if episode else 0}-{shot.idx:02d}"
    return Owner(shot.series_id, shot.id, label)


async def add_shot_ref(
    db: Database,
    products: ProductService,
    store: BlobStore,
    shot_id: str,
    purpose: str,
    filename: str,
    data: bytes,
) -> str:
    """镜头参考图 (M5.5 step 12): a picture for this shot's 构图 / 姿势 / 光线 / 风格."""
    owner = await _shot_owner(db, shot_id)
    return await add_picture(db, products, store, SHOT_REFS, owner, purpose, filename, data)


async def remove_shot_ref(db: Database, products: ProductService, shot_id: str, idx: int) -> str:
    return await remove_picture(db, products, SHOT_REFS, await _shot_owner(db, shot_id), idx)
