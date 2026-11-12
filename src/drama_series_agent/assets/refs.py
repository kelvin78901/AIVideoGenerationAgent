"""More pictures of an asset (M5.5 step 11): 多参考图 and 六视图单张替换.

**多参考图** (slot ``ref_more``, owner the asset): the user's own pictures of a character, scene
or prop beyond its main one, each with a ``purpose`` (正脸 / 服装 / 发型 / 姿势 / 其他). One
version holds them all (files ``role: ref``, ``idx``, ``purpose``); adding or removing one
appends a version with the rest copied, and it is adopted at once: they are not chosen. A
keyframe sends them after every main picture, as far as ``max_refs`` goes, and only for an asset
whose main picture is locked (they add to the reference, they do not stand in for it).

**六视图单张替换** (``POST /products/{id}/views/{view}``): an uploaded picture takes one view's
place, the other five copied, the dependencies of the version it copies kept (the set follows
the same locked picture, outdated or not). 「重画这一张」 is a views run with ``params.view``
(``pipeline/components/views.py``).
"""

from __future__ import annotations

from typing import Any

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from drama_series_agent.core.db import Database
from drama_series_agent.core.models_db import Asset, Dependency, Product, ProductVersion
from drama_series_agent.core.storage import BlobStore
from drama_series_agent.media.image import MAX_UPLOAD_BYTES, ImageInfo, NotAnImage, image_info
from drama_series_agent.pipeline.drafts import DependencyDraft, VersionDraft, file_entry
from drama_series_agent.pipeline.errors import PipelineError
from drama_series_agent.pipeline.invalidation import Invalidation
from drama_series_agent.pipeline.products import ProductService

REF_MORE_SLOT = "ref_more"
# A product nothing runs: the user's files only (``runs.describe`` finds no template for it).
UPLOAD_COMPONENT = "upload"
PURPOSES = ("face", "outfit", "hair", "pose", "other")
PURPOSE_LABEL = {"face": "正脸", "outfit": "服装", "hair": "发型", "pose": "姿势", "other": "其他"}
MORE_KINDS = ("character", "scene", "prop")
MAX_MORE = 8


def read_image(filename: str, data: bytes) -> ImageInfo:
    if len(data) > MAX_UPLOAD_BYTES:
        raise PipelineError(413, "file_too_large", limit=MAX_UPLOAD_BYTES)
    try:
        return image_info(data)
    except NotAnImage:
        raise PipelineError(422, "not_an_image", filename=filename) from None


def more_files(v: ProductVersion | None) -> list[dict[str, Any]]:
    """A ``ref_more`` version's pictures in order."""
    files = [f for f in (v.files_json if v is not None else []) if f.get("role") == "ref"]
    return sorted(files, key=lambda f: int(f.get("idx") or 0))


async def more_product(session: AsyncSession, asset_id: str) -> Product | None:
    query = select(Product).where(
        Product.owner_type == "asset", Product.owner_id == asset_id, Product.slot == REF_MORE_SLOT
    )
    return (await session.exec(query)).first()


async def more_refs(
    session: AsyncSession, invalidation: Invalidation, asset_ids: list[str]
) -> dict[str, dict[str, Any]]:
    """For a keyframe: each asset's extra pictures (adopted version), with the product and the
    version's hash to depend on."""
    rows = (
        await session.exec(
            select(Product).where(
                Product.owner_type == "asset",
                col(Product.owner_id).in_(asset_ids),
                Product.slot == REF_MORE_SLOT,
                col(Product.adopted_version_id).is_not(None),
            )
        )
    ).all()
    out: dict[str, dict[str, Any]] = {}
    for p in rows:
        v = await session.get(ProductVersion, p.adopted_version_id)
        files = more_files(v)
        if v is not None and files:
            h = await invalidation.current_hash(session, p.id, "")
            out[p.owner_id] = {"product_id": p.id, "hash": h, "files": files}
    return out


def _renumbered(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{**f, "idx": i} for i, f in enumerate(files)]


def _more_draft(files: list[dict[str, Any]], note: str | None, intent: str) -> VersionDraft:
    files = _renumbered(files)
    return VersionDraft(
        payload={"refs": [{"purpose": f.get("purpose") or "other"} for f in files]},
        files=files,
        intent=intent,
        note=note,
    )


async def add_more(
    db: Database,
    products: ProductService,
    store: BlobStore,
    asset_id: str,
    purpose: str,
    filename: str,
    data: bytes,
) -> str:
    """「加参考图」: the picture after the asset's others, with what it is for."""
    if purpose not in PURPOSES:
        raise PipelineError(422, "invalid_purpose", purpose=purpose)
    info = read_image(filename, data)
    asset, current = await _asset_more(db, asset_id)
    files = more_files(current)
    if len(files) >= MAX_MORE:
        raise PipelineError(409, "too_many_refs", limit=MAX_MORE)
    sha = store.put_bytes(data)
    name = filename[:200]
    files.append(
        file_entry("ref", sha, info.mime, w=info.w, h=info.h, idx=len(files), purpose=purpose)
    )
    p = await products.ensure(
        series_id=asset.series_id,
        owner_type="asset",
        owner_id=asset.id,
        slot=REF_MORE_SLOT,
        component_id=UPLOAD_COMPONENT,
    )
    draft = _more_draft(files, name or None, asset.name)
    draft.params = {"filename": name, "purpose": purpose}
    await products.append(p.id, draft, origin="upload", adopt=True)
    return p.id


async def remove_more(db: Database, products: ProductService, asset_id: str, idx: int) -> str:
    """「删掉这张」: the others in a new version."""
    asset, current = await _asset_more(db, asset_id)
    files = more_files(current)
    if current is None or not 0 <= idx < len(files):
        raise PipelineError(404, "ref_not_found", id=asset_id, idx=idx)
    gone = files.pop(idx)
    draft = _more_draft(files, None, asset.name)
    draft.params = {"removed": gone["sha256"]}
    await products.append(current.product_id, draft, origin="edit", adopt=True)
    return current.product_id


async def _asset_more(db: Database, asset_id: str) -> tuple[Asset, ProductVersion | None]:
    async with db.session() as session:
        asset = await session.get(Asset, asset_id)
        if asset is None or asset.retired:
            raise PipelineError(404, "asset_not_found", id=asset_id)
        if asset.kind not in MORE_KINDS:
            raise PipelineError(422, "upload_not_supported", kind=asset.kind)
        p = await more_product(session, asset_id)
        v = (
            await session.get(ProductVersion, p.adopted_version_id)
            if p is not None and p.adopted_version_id
            else None
        )
        return asset, v


async def views_version(
    session: AsyncSession, product_id: str, views_slot: str
) -> tuple[Product, ProductVersion]:
    """A character's views product and its adopted set (to replace one view of)."""
    p = await session.get(Product, product_id)
    if p is None or p.retired:
        raise PipelineError(404, "product_not_found", id=product_id)
    if p.slot != views_slot:
        raise PipelineError(422, "not_views", id=product_id)
    if p.locked_hash:
        raise PipelineError(409, "product_locked", id=p.id)
    v = await session.get(ProductVersion, p.adopted_version_id) if p.adopted_version_id else None
    if v is None:
        raise PipelineError(409, "no_views", id=product_id)
    return p, v


async def replace_view(
    db: Database,
    products: ProductService,
    store: BlobStore,
    product_id: str,
    view: str,
    views_slot: str,
    filename: str,
    data: bytes,
) -> str:
    """An uploaded picture as one view; the other views and the dependencies copied."""
    info = read_image(filename, data)
    async with db.session() as session:
        p, v = await views_version(session, product_id, views_slot)
        deps = (await session.exec(select(Dependency).where(Dependency.version_id == v.id))).all()
        kept = [DependencyDraft(d.upstream_product_id, d.upstream_hash, d.slice) for d in deps]
    idx = next((int(f["idx"]) for f in v.files_json if f.get("view") == view), None)
    if idx is None:
        raise PipelineError(422, "unknown_view", view=view)
    sha = store.put_bytes(data)
    name = filename[:200]
    mine = file_entry("view", sha, info.mime, w=info.w, h=info.h, idx=idx, view=view)
    files = [mine if f.get("view") == view else dict(f) for f in v.files_json]
    payload = dict(v.payload_json)
    payload["uploaded"] = sorted({*payload.get("uploaded", []), view})
    draft = VersionDraft(
        payload=payload,
        files=files,
        intent=v.intent,
        params={"filename": name, "view": view},
        note=name or None,
        dependencies=kept,
    )
    await products.append(p.id, draft, origin="upload", parent_version_id=v.id, adopt=True)
    return p.id
