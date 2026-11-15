"""More pictures of an asset (M5.5 step 11): 多参考图 and 六视图单张替换.

**多参考图** (slot ``ref_more``, owner the asset, a picture set: ``pipeline/pictures.py``): the
user's own pictures of a character, scene or prop beyond its main one, each with a ``purpose``
(正脸 / 服装 / 发型 / 姿势 / 其他). A keyframe sends them after every main picture, as far as
``max_refs`` goes, and only for an asset whose main picture is locked (they add to the
reference, they do not stand in for it).

**六视图单张替换** (``POST /products/{id}/views/{view}``): an uploaded picture takes one view's
place, the other five copied, the dependencies of the version it copies kept (the set follows
the same locked picture, outdated or not). 「重画这一张」 is a views run with ``params.view``
(``pipeline/components/views.py``).
"""

from __future__ import annotations

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from drama_series_agent.core.db import Database
from drama_series_agent.core.models_db import Asset, Dependency, Product, ProductVersion
from drama_series_agent.core.storage import BlobStore
from drama_series_agent.pipeline.drafts import DependencyDraft, VersionDraft, file_entry
from drama_series_agent.pipeline.errors import PipelineError
from drama_series_agent.pipeline.pictures import (
    Owner,
    PictureSet,
    add_picture,
    read_image,
    remove_picture,
)
from drama_series_agent.pipeline.products import ProductService

REF_MORE_SLOT = "ref_more"
PURPOSES = ("face", "outfit", "hair", "pose", "other")
PURPOSE_LABEL = {"face": "正脸", "outfit": "服装", "hair": "发型", "pose": "姿势", "other": "其他"}
MORE_KINDS = ("character", "scene", "prop")
MAX_MORE = 8
REF_MORE = PictureSet(REF_MORE_SLOT, "asset", PURPOSES, MAX_MORE)


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
    owner = await _owner(db, asset_id)
    return await add_picture(db, products, store, REF_MORE, owner, purpose, filename, data)


async def remove_more(db: Database, products: ProductService, asset_id: str, idx: int) -> str:
    """「删掉这张」: the others in a new version."""
    return await remove_picture(db, products, REF_MORE, await _owner(db, asset_id), idx)


async def _owner(db: Database, asset_id: str) -> Owner:
    async with db.session() as session:
        asset = await session.get(Asset, asset_id)
    if asset is None or asset.retired:
        raise PipelineError(404, "asset_not_found", id=asset_id)
    if asset.kind not in MORE_KINDS:
        raise PipelineError(422, "upload_not_supported", kind=asset.kind)
    return Owner(asset.series_id, asset.id, asset.name)


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
