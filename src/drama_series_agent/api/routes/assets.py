"""Assets (SPEC 9.1, M3): ``/series/{id}/assets``, ``/assets/{id}``, ``/episodes/{id}/assets/…``;
M5.5: 新建素材, 多参考图 ``/assets/{id}/refs``, 六视图单张替换 ``/products/{id}/views/{view}``."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from pydantic import BaseModel

from drama_series_agent.api.state import StudioState, get_state
from drama_series_agent.assets.dub import DubIn, DubLineOut, DubOut, DubStartOut, LineDubPatch
from drama_series_agent.assets.schema import (
    AssetCreateIn,
    AssetLockIn,
    AssetOut,
    AssetPatch,
    MatrixOut,
)
from drama_series_agent.core.jobs import job_public
from drama_series_agent.media.image import MAX_UPLOAD_BYTES
from drama_series_agent.pipeline.schema import ProductOut

router = APIRouter(tags=["assets"])

State = Annotated[StudioState, Depends(get_state)]


@router.get("/series/{series_id}/assets")
async def list_assets(
    series_id: str,
    state: State,
    episode: Annotated[str | None, Query(max_length=64)] = None,
) -> list[AssetOut]:
    """The series' assets, characters first; ``scenes`` and ``source`` are about ``episode``."""
    return await state.assets.list_assets(series_id, episode)


@router.post("/series/{series_id}/assets")
async def create_asset(series_id: str, body: AssetCreateIn, state: State) -> AssetOut:
    """「新建素材」 (M5.5): ``manual``, with its product; 409 ``asset_exists`` for the same kind
    and name."""
    return await state.assets.create(series_id, body)


@router.patch("/assets/{asset_id}")
async def patch_asset(asset_id: str, body: AssetPatch, state: State) -> AssetOut:
    """改描述 / 选这个 / 画面文字 / 音色来源 (409 ``product_locked`` once locked)."""
    return await state.assets.patch(asset_id, body)


@router.post("/assets/{asset_id}/lock")
async def lock_asset(asset_id: str, state: State, body: AssetLockIn | None = None) -> AssetOut:
    """「锁定为参考」: the picked candidate (of the version on screen unless ``body`` names one)
    becomes the locked reference; the asset's gate decision keeps its file's hash. Unlocking
    goes through ``/impact/preview`` (kind ``asset_unlock``)."""
    return await state.assets.lock(asset_id, body)


@router.post("/assets/{asset_id}/upload")
async def upload_asset(
    asset_id: str, state: State, file: Annotated[UploadFile, File()]
) -> AssetOut:
    """「上传参考图」 (PNG, JPEG, WebP): a new version with that one candidate, picked."""
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    return await state.assets.upload(asset_id, file.filename or "", data)


@router.post("/assets/{asset_id}/refs")
async def add_asset_ref(
    asset_id: str,
    state: State,
    file: Annotated[UploadFile, File()],
    purpose: Annotated[str, Form(max_length=16)] = "other",
) -> ProductOut:
    """多参考图 (M5.5): another picture with what it is for (``face`` / ``outfit`` / ``hair`` /
    ``pose`` / ``other``); the ``ref_more`` product, its new version adopted."""
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    product_id = await state.assets.add_more(asset_id, purpose, file.filename or "", data)
    return await state.products.get(product_id)


@router.delete("/assets/{asset_id}/refs/{idx}")
async def remove_asset_ref(asset_id: str, idx: int, state: State) -> ProductOut:
    """删掉一张多参考图: the others in a new version."""
    return await state.products.get(await state.assets.remove_more(asset_id, idx))


class ViewReplaceOut(BaseModel):
    """六视图单张替换: the views product after an upload, or the job redrawing that view."""

    product: ProductOut | None = None
    job: dict[str, Any] | None = None


@router.post("/products/{product_id}/views/{view}")
async def replace_view(
    product_id: str,
    view: str,
    state: State,
    file: Annotated[UploadFile | None, File()] = None,
) -> ViewReplaceOut:
    """六视图单张替换 (M5.5): with a file, that picture takes the view's place (the other five
    copied); without, 「重画这一张」 (409 ``views_outdated`` when the set follows another
    picture)."""
    if file is None:
        return ViewReplaceOut(job=job_public(await state.assets.redraw_view(product_id, view)))
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    pid = await state.assets.upload_view(product_id, view, file.filename or "", data)
    return ViewReplaceOut(product=await state.products.get(pid))


@router.post("/episodes/{episode_id}/assets/analyze")
async def analyze(episode_id: str, state: State) -> dict[str, Any]:
    """「重新分析剧本」 → the queued 素材分析 job (its version is adopted when it succeeds)."""
    return job_public(await state.assets.analyze(episode_id))


@router.get("/episodes/{episode_id}/assets/matrix")
async def matrix(episode_id: str, state: State) -> MatrixOut:
    """出场矩阵: the episode's scenes × the assets it uses."""
    return await state.assets.matrix(episode_id)


@router.get("/episodes/{episode_id}/dub")
async def episode_dub(episode_id: str, state: State) -> DubOut:
    """台词配音: the episode's spoken lines with their audio, and the scenes' lengths."""
    return await state.dub.status(episode_id)


@router.post("/episodes/{episode_id}/dub")
async def dub_episode(episode_id: str, state: State, body: DubIn | None = None) -> DubStartOut:
    """「全部配音」: the estimate (``dry_run``), or one run per line without current audio."""
    return await state.dub.dub(episode_id, body or DubIn())


@router.patch("/lines/{line_id}/dub")
async def set_line_emotion(line_id: str, body: LineDubPatch, state: State) -> DubLineOut:
    """A line's emotion by hand (None: from its tone again); the next take uses it."""
    return await state.dub.set_emotion(line_id, body)
