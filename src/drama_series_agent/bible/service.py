"""Reading and editing the story bible (SPEC 9.1 ``/series/{id}/bible``, ``/bible/…``).

The bible is the series' ``bible`` product (component ``extract``). Reads show the product's
current version through one pure view (``bible_out``), adopted or not. The user's edits append
an ``edit`` version made from the current one and adopt it (M2 plan 设计要点); it keeps the
dependencies of the version it was made from, so it turns stale with it. ``bible_entity``
mirrors the adopted version (``materialize``) for the foreign keys of later steps.
"""

from __future__ import annotations

from typing import Any

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from drama_series_agent.bible import merge as ops
from drama_series_agent.bible.schema import (
    BibleEntityOut,
    BibleMergeIn,
    BibleOut,
    BiblePatch,
    bible_out,
    entity_out,
)
from drama_series_agent.core.db import Database
from drama_series_agent.core.models_db import (
    BibleEntity,
    Dependency,
    Job,
    Product,
    ProductVersion,
    Series,
    utcnow,
)
from drama_series_agent.novel.service import NovelService
from drama_series_agent.pipeline.drafts import DependencyDraft, VersionDraft
from drama_series_agent.pipeline.errors import PipelineError
from drama_series_agent.pipeline.products import ACTIVE_JOB_STATES, ProductService

BIBLE_SLOT = "bible"
EXTRACT_COMPONENT = "extract"


async def bible_product(session: AsyncSession, series_id: str) -> Product | None:
    query = select(Product).where(
        Product.owner_type == "series", Product.owner_id == series_id, Product.slot == BIBLE_SLOT
    )
    return (await session.exec(query)).first()


async def materialize(session: AsyncSession, product: Product, version: ProductVersion) -> None:
    """Mirror an adopted version: upsert its entries by id, retire the ones it dropped."""
    rows = {
        r.id: r
        for r in (
            await session.exec(
                select(BibleEntity).where(BibleEntity.series_id == product.series_id)
            )
        ).all()
    }
    now = utcnow()
    kept: set[str] = set()
    for e in version.payload_json.get("entities") or []:
        row = rows.get(e["id"]) or BibleEntity(
            id=e["id"], series_id=product.series_id, version_id=version.id, kind=e["kind"], name=""
        )
        row.version_id = version.id
        row.kind = e["kind"]
        row.name = e["name"]
        row.aliases_json = list(e.get("aliases") or [])
        row.data_json = dict(e.get("data") or {})
        row.paras_json = list(e.get("paras") or [])
        row.source_spans_json = list(e.get("source_spans") or [])
        row.frozen = bool(e.get("frozen"))
        row.retired = False
        row.updated_at = now
        session.add(row)
        kept.add(row.id)
    for row in rows.values():
        if row.id not in kept and not row.retired:
            row.retired = True
            row.version_id = version.id
            row.updated_at = now
            session.add(row)


class BibleService:
    def __init__(self, db: Database, products: ProductService, novel: NovelService) -> None:
        self._db = db
        self._products = products
        self._novel = novel

    # ------------------------------------------------------------------ reads

    async def get(self, series_id: str) -> BibleOut:
        async with self._db.session() as session:
            if await session.get(Series, series_id) is None:
                raise PipelineError(404, "series_not_found", id=series_id)
            p = await bible_product(session, series_id)
            v = await self._current(session, p)
        if p is None or v is None:
            return bible_out(series_id, None, product_id=p.id if p else None)
        return bible_out(
            series_id,
            v.payload_json,
            product_id=p.id,
            version_id=v.id,
            adopted=v.id == p.adopted_version_id,
        )

    # ------------------------------------------------------------------ edits

    async def patch(self, entity_id: str, body: BiblePatch) -> BibleEntityOut:
        p, v = await self._locate(entity_id)
        changes: dict[str, Any] = body.model_dump(exclude_unset=True)
        payload = self._apply(lambda: ops.patch(v.payload_json, entity_id, **changes))
        await self._edit(p, v, payload)
        entity = ops.find(payload, entity_id)
        assert entity is not None
        return entity_out(p.series_id, entity)

    async def merge(self, body: BibleMergeIn) -> BibleOut:
        p, v = await self._locate(body.ids[0])
        current = v.payload_json
        if body.action == "merge":
            payload = self._apply(lambda: ops.merge(current, body.ids))
        elif body.action == "distinct":
            payload = self._apply(lambda: ops.distinct(current, body.ids))
        else:
            if len(body.ids) != 1 or not (body.alias or "").strip():
                raise PipelineError(422, "split_needs_alias")
            async with self._db.session() as session:
                book = await self._novel.book_of(session, str(current.get("source_id")))
            if book is None:
                raise PipelineError(409, "source_missing", id=current.get("source_id"))
            alias = str(body.alias).strip()
            payload, _ = self._apply(
                lambda: ops.split(current, body.ids[0], alias, book.paragraph, book.span)
            )
        await self._edit(p, v, payload)
        return await self.get(p.series_id)

    # ------------------------------------------------------------------ internals

    @staticmethod
    def _apply(fn: Any) -> Any:
        try:
            return fn()
        except ops.BibleEditError as exc:
            status = 404 if exc.code == "entity_not_found" else 422
            raise PipelineError(status, exc.code, **exc.params) from exc

    @staticmethod
    async def _current(session: AsyncSession, p: Product | None) -> ProductVersion | None:
        if p is None or p.current_version_id is None:
            return None
        return await session.get(ProductVersion, p.current_version_id)

    async def _locate(self, entity_id: str) -> tuple[Product, ProductVersion]:
        """The bible product whose version on screen has this entry; refuses a busy or locked
        product (an edit while extraction runs would be lost when it finishes)."""
        async with self._db.session() as session:
            row = await session.get(BibleEntity, entity_id)
            if row is not None:
                products = [p] if (p := await bible_product(session, row.series_id)) else []
            else:
                query = select(Product).where(Product.slot == BIBLE_SLOT)
                products = list((await session.exec(query.order_by(col(Product.created_at)))).all())
            for p in products:
                v = await self._current(session, p)
                if v is None or ops.find(v.payload_json, entity_id) is None:
                    continue
                if p.running_job_id:
                    job = await session.get(Job, p.running_job_id)
                    if job is not None and job.state in ACTIVE_JOB_STATES:
                        raise PipelineError(409, "product_busy", id=p.id)
                if p.locked_hash:
                    raise PipelineError(409, "product_locked", id=p.id)
                return p, v
        raise PipelineError(404, "entity_not_found", id=entity_id)

    async def _edit(self, p: Product, v: ProductVersion, payload: dict[str, Any]) -> None:
        if payload == v.payload_json:
            return
        async with self._db.session() as session:
            deps = (
                await session.exec(select(Dependency).where(Dependency.version_id == v.id))
            ).all()
        draft = VersionDraft(
            payload=payload,
            intent=v.intent,
            compiled=v.compiled,
            compiled_overridden=v.compiled_overridden,
            dependencies=[
                DependencyDraft(d.upstream_product_id, d.upstream_hash, d.slice) for d in deps
            ],
        )
        await self._products.append(p.id, draft, origin="edit", parent_version_id=v.id, adopt=True)
