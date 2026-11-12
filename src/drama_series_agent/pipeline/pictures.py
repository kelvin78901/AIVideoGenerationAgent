"""Picture sets (M5.5 steps 11–12): products that hold only the user's own pictures, each with
what it is for, which a keyframe sends after the pictures it draws from.

- ``ref_more`` (owner an asset): 多参考图, 正脸 / 服装 / 发型 / 姿势 / 其他 (``assets/refs.py``);
- ``shot_refs`` (owner a shot): 镜头参考图, 构图 / 姿势 / 光线 / 风格 (``shots/upload.py``);
- ``style_board`` (owner the series): 风格板, every picture only for the look.

One version holds the whole set (files ``role: ref``, ``idx``, ``purpose``; payload
``refs: [{purpose}]``). Adding or removing a picture appends a version with the rest copied and
adopts it at once: a set is not chosen from. Nothing runs these products (``component_id:
upload``: no template, so no estimate). A keyframe depends on the set it sent (its current
hash), so changing the set makes it 「待更新」.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from drama_series_agent.core.db import Database
from drama_series_agent.core.models_db import Product, ProductVersion
from drama_series_agent.core.storage import BlobStore
from drama_series_agent.media.image import MAX_UPLOAD_BYTES, ImageInfo, NotAnImage, image_info
from drama_series_agent.pipeline.drafts import VersionDraft, file_entry
from drama_series_agent.pipeline.errors import PipelineError
from drama_series_agent.pipeline.invalidation import Invalidation
from drama_series_agent.pipeline.products import ProductService

# A product nothing runs: the user's files only (``runs.describe`` finds no template for it).
UPLOAD_COMPONENT = "upload"


@dataclass(frozen=True)
class PictureSet:
    slot: str
    owner_type: str
    purposes: tuple[str, ...]
    limit: int


SHOT_REFS = PictureSet("shot_refs", "shot", ("composition", "pose", "light", "style"), 4)
SHOT_PURPOSE_LABEL = {"composition": "构图", "pose": "姿势", "light": "光线", "style": "风格"}
STYLE_BOARD = PictureSet("style_board", "series", ("style",), 4)


@dataclass(frozen=True)
class Owner:
    series_id: str
    owner_id: str
    name: str  # the version's intent: whose pictures these are


def read_image(filename: str, data: bytes) -> ImageInfo:
    if len(data) > MAX_UPLOAD_BYTES:
        raise PipelineError(413, "file_too_large", limit=MAX_UPLOAD_BYTES)
    try:
        return image_info(data)
    except NotAnImage:
        raise PipelineError(422, "not_an_image", filename=filename) from None


def set_files(v: ProductVersion | None) -> list[dict[str, Any]]:
    """A set's pictures in order."""
    files = [f for f in (v.files_json if v is not None else []) if f.get("role") == "ref"]
    return sorted(files, key=lambda f: int(f.get("idx") or 0))


async def set_product(session: AsyncSession, kind: PictureSet, owner_id: str) -> Product | None:
    query = select(Product).where(
        Product.owner_type == kind.owner_type,
        Product.owner_id == owner_id,
        Product.slot == kind.slot,
    )
    return (await session.exec(query)).first()


async def adopted_set(
    session: AsyncSession, kind: PictureSet, owner_id: str
) -> ProductVersion | None:
    p = await set_product(session, kind, owner_id)
    if p is None or not p.adopted_version_id:
        return None
    return await session.get(ProductVersion, p.adopted_version_id)


async def sets_of(
    session: AsyncSession, invalidation: Invalidation, kind: PictureSet, owner_ids: list[str]
) -> dict[str, dict[str, Any]]:
    """For a keyframe: each owner's set (adopted version), with the product and its hash."""
    rows = (
        await session.exec(
            select(Product).where(
                Product.owner_type == kind.owner_type,
                col(Product.owner_id).in_(owner_ids),
                Product.slot == kind.slot,
                col(Product.adopted_version_id).is_not(None),
            )
        )
    ).all()
    out: dict[str, dict[str, Any]] = {}
    for p in rows:
        files = set_files(await session.get(ProductVersion, p.adopted_version_id))
        if files:
            h = await invalidation.current_hash(session, p.id, "")
            out[p.owner_id] = {"product_id": p.id, "hash": h, "files": files}
    return out


def _draft(files: list[dict[str, Any]], note: str | None, intent: str) -> VersionDraft:
    files = [{**f, "idx": i} for i, f in enumerate(files)]
    return VersionDraft(
        payload={"refs": [{"purpose": f.get("purpose")} for f in files]},
        files=files,
        intent=intent,
        note=note,
    )


async def add_picture(
    db: Database,
    products: ProductService,
    store: BlobStore,
    kind: PictureSet,
    owner: Owner,
    purpose: str,
    filename: str,
    data: bytes,
) -> str:
    """The picture after the set's others, with what it is for; the set product's id."""
    if purpose not in kind.purposes:
        raise PipelineError(422, "invalid_purpose", purpose=purpose)
    info = read_image(filename, data)
    async with db.session() as session:
        files = set_files(await adopted_set(session, kind, owner.owner_id))
    if len(files) >= kind.limit:
        raise PipelineError(409, "too_many_refs", limit=kind.limit)
    sha = store.put_bytes(data)
    name = filename[:200]
    files.append(file_entry("ref", sha, info.mime, w=info.w, h=info.h, purpose=purpose))
    p = await products.ensure(
        series_id=owner.series_id,
        owner_type=kind.owner_type,
        owner_id=owner.owner_id,
        slot=kind.slot,
        component_id=UPLOAD_COMPONENT,
    )
    draft = _draft(files, name or None, owner.name)
    draft.params = {"filename": name, "purpose": purpose}
    await products.append(p.id, draft, origin="upload", adopt=True)
    return p.id


async def remove_picture(
    db: Database, products: ProductService, kind: PictureSet, owner: Owner, idx: int
) -> str:
    """「删掉这张」: the others in a new version."""
    async with db.session() as session:
        current = await adopted_set(session, kind, owner.owner_id)
    files = set_files(current)
    if current is None or not 0 <= idx < len(files):
        raise PipelineError(404, "ref_not_found", id=owner.owner_id, idx=idx)
    gone = files.pop(idx)
    draft = _draft(files, None, owner.name)
    draft.params = {"removed": gone["sha256"]}
    await products.append(current.product_id, draft, origin="edit", adopt=True)
    return current.product_id
