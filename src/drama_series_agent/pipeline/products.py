"""Products and versions (SPEC 4.2).

Versions are append-only and are the source of truth. ``current`` is what the screen shows,
``adopted`` is what downstream uses, ``locked_hash`` is set when a gate locks the adopted one.
Only the first successful version of a product is adopted automatically; later runs only
become current, so an adopted version is never replaced behind the user's back (hard rule 5).
Domain tables that mirror the adopted version register a materializer per slot (``on_adopt``).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from drama_series_agent.core.db import Database
from drama_series_agent.core.events import EventBus, EventType
from drama_series_agent.core.models_db import Dependency, Product, ProductVersion, utcnow
from drama_series_agent.pipeline.errors import PipelineError
from drama_series_agent.pipeline.hashing import content_hash
from drama_series_agent.pipeline.schema import (
    EstimateOut,
    ProductOut,
    PromptOut,
    RunningOut,
    VersionFileOut,
    VersionOut,
)

Materializer = Callable[[AsyncSession, Product, ProductVersion], Awaitable[None]]


@dataclass
class DependencyDraft:
    upstream_product_id: str
    upstream_hash: str
    slice: str = ""


@dataclass
class VersionDraft:
    """What a run or an edit produced; ``append`` turns it into a version."""

    payload: dict[str, Any]
    files: list[dict[str, Any]] = field(default_factory=list)
    intent: str | None = None
    compiled: str | None = None
    compiled_overridden: bool = False
    model_key: str | None = None
    where: str | None = None
    seed: int | None = None
    params: dict[str, Any] = field(default_factory=dict)
    cost_usd: float = 0.0
    job_id: str | None = None
    fallback_reason: str | None = None
    stage: str | None = None
    note: str | None = None
    dependencies: list[DependencyDraft] = field(default_factory=list)
    # The demo seed inserts versions with the ids and times of the MSW fixtures.
    id: str | None = None
    created_at: datetime | None = None


def status_of(p: Product) -> str:
    """Display status: run state first, then locked > adopted > ready (SPEC 4.2)."""
    if p.status in ("queued", "running", "failed"):
        return p.status
    if p.locked_hash:
        return "locked"
    if p.adopted_version_id:
        return "adopted"
    return "ready" if p.current_version_id else "empty"


def version_public(v: ProductVersion) -> VersionOut:
    return VersionOut(
        id=v.id,
        product_id=v.product_id,
        n=v.n,
        origin=v.origin,
        parent_version_id=v.parent_version_id,
        payload=v.payload_json,
        files=[VersionFileOut.model_validate(f) for f in v.files_json],
        content_hash=v.content_hash,
        intent=v.intent,
        compiled=v.compiled,
        compiled_overridden=v.compiled_overridden,
        model_key=v.model_key,
        where=v.where,
        seed=v.seed,
        params=v.params_json,
        qa=v.qa_json,
        qa_pass=v.qa_pass,
        fallback_reason=v.fallback_reason,
        stage=v.stage,
        rating=v.rating,
        cost_usd=v.cost_usd,
        job_id=v.job_id,
        created_at=v.created_at,
        note=v.note,
    )


def product_public(
    p: Product,
    versions: Sequence[ProductVersion],
    *,
    estimate: EstimateOut | None = None,
) -> ProductOut:
    prompt = PromptOut.model_validate(p.prompt_json) if p.prompt_json else None
    running = None
    if p.running_job_id:
        running = RunningOut(job_id=p.running_job_id, model_key=prompt.model_key if prompt else "")
    return ProductOut(
        id=p.id,
        series_id=p.series_id,
        owner_type=p.owner_type,
        owner_id=p.owner_id,
        slot=p.slot,
        component_id=p.component_id,
        current_version_id=p.current_version_id,
        adopted_version_id=p.adopted_version_id,
        locked_hash=p.locked_hash,
        status=status_of(p),
        versions=[version_public(v) for v in sorted(versions, key=lambda v: v.n)],
        prompt=prompt,
        estimate=estimate,
        running=running,
    )


def parse_owner(owner: str) -> tuple[str, str]:
    kind, sep, owner_id = owner.partition(":")
    if not sep or not kind or not owner_id:
        raise PipelineError(422, "invalid_owner", owner=owner)
    return kind, owner_id


# --------------------------------------------------------------------------- session-level


async def require_product(session: AsyncSession, product_id: str) -> Product:
    p = await session.get(Product, product_id)
    if p is None:
        raise PipelineError(404, "product_not_found", id=product_id)
    return p


async def require_version(session: AsyncSession, version_id: str) -> ProductVersion:
    v = await session.get(ProductVersion, version_id)
    if v is None:
        raise PipelineError(404, "version_not_found", id=version_id)
    return v


async def versions_of(session: AsyncSession, product_id: str) -> list[ProductVersion]:
    rows = await session.exec(
        select(ProductVersion)
        .where(ProductVersion.product_id == product_id)
        .order_by(col(ProductVersion.n))
    )
    return list(rows.all())


class ProductService:
    def __init__(self, db: Database, bus: EventBus) -> None:
        self._db = db
        self._bus = bus
        self._materializers: dict[str, Materializer] = {}

    def on_adopt(self, slot: str, materializer: Materializer) -> None:
        """Rebuild the domain rows of ``slot`` from a newly adopted version (same transaction)."""
        self._materializers[slot] = materializer

    # ------------------------------------------------------------------ reads

    async def get(self, product_id: str) -> ProductOut:
        async with self._db.session() as session:
            p = await require_product(session, product_id)
            return product_public(p, await versions_of(session, p.id))

    async def find(
        self, *, owner: str | None = None, component: str | None = None
    ) -> list[ProductOut]:
        query = select(Product)
        if owner:
            owner_type, owner_id = parse_owner(owner)
            query = query.where(Product.owner_type == owner_type, Product.owner_id == owner_id)
        if component:
            query = query.where(Product.component_id == component)
        async with self._db.session() as session:
            products = list((await session.exec(query.order_by(col(Product.created_at)))).all())
            ids = [p.id for p in products]
            rows = await session.exec(
                select(ProductVersion).where(col(ProductVersion.product_id).in_(ids))
            )
            by_product: dict[str, list[ProductVersion]] = {}
            for v in rows.all():
                by_product.setdefault(v.product_id, []).append(v)
        return [product_public(p, by_product.get(p.id, [])) for p in products]

    # ------------------------------------------------------------------ writes

    async def ensure(
        self,
        *,
        series_id: str,
        owner_type: str,
        owner_id: str,
        slot: str,
        component_id: str,
        product_id: str | None = None,
    ) -> Product:
        """The product for (owner, slot), created empty if it does not exist yet."""
        async with self._db.session() as session:
            found = (
                await session.exec(
                    select(Product).where(
                        Product.owner_type == owner_type,
                        Product.owner_id == owner_id,
                        Product.slot == slot,
                    )
                )
            ).first()
            if found is not None:
                return found
            p = Product(
                series_id=series_id,
                owner_type=owner_type,
                owner_id=owner_id,
                slot=slot,
                component_id=component_id,
            )
            if product_id:
                p.id = product_id
            session.add(p)
            await session.commit()
            await session.refresh(p)
        await self._announce(p)
        return p

    async def append(
        self,
        product_id: str,
        draft: VersionDraft,
        *,
        origin: str,
        parent_version_id: str | None = None,
        adopt: bool | None = None,
    ) -> ProductVersion:
        """Append a version and make it current.

        ``adopt``: None = only if nothing is adopted yet (first success); True = adopt it (a
        user's edit); False = never.
        """
        async with self._db.session() as session:
            p = await require_product(session, product_id)
            last_n = (
                await session.exec(
                    select(func.max(ProductVersion.n)).where(ProductVersion.product_id == p.id)
                )
            ).one()
            v = ProductVersion(
                product_id=p.id,
                n=(last_n or 0) + 1,
                origin=origin,
                parent_version_id=parent_version_id,
                payload_json=draft.payload,
                files_json=draft.files,
                content_hash=content_hash(draft.payload, draft.files),
                intent=draft.intent,
                compiled=draft.compiled,
                compiled_overridden=draft.compiled_overridden,
                model_key=draft.model_key,
                where=draft.where,
                seed=draft.seed,
                params_json=draft.params,
                cost_usd=draft.cost_usd,
                job_id=draft.job_id,
                fallback_reason=draft.fallback_reason,
                stage=draft.stage,
                note=draft.note,
            )
            if draft.id:
                v.id = draft.id
            if draft.created_at:
                v.created_at = draft.created_at
            session.add(v)
            await session.flush()
            for dep in draft.dependencies:
                session.add(
                    Dependency(
                        version_id=v.id,
                        product_id=p.id,
                        upstream_product_id=dep.upstream_product_id,
                        slice=dep.slice,
                        upstream_hash=dep.upstream_hash,
                    )
                )
            p.current_version_id = v.id
            p.status = "ready"
            auto = adopt is None and p.adopted_version_id is None and not p.locked_hash
            if adopt or auto:
                if p.locked_hash:
                    raise PipelineError(409, "product_locked", id=p.id)
                await self._adopt(session, p, v)
            p.updated_at = utcnow()
            session.add(p)
            await session.commit()
            await session.refresh(v)
            await session.refresh(p)
        await self._bus.publish(
            EventType.VERSION_CREATED,
            {"product_id": p.id, "version_id": v.id, "n": v.n, "origin": v.origin},
        )
        await self._announce(p)
        return v

    async def set_current(self, version_id: str) -> ProductOut:
        async with self._db.session() as session:
            v = await require_version(session, version_id)
            p = await require_product(session, v.product_id)
            p.current_version_id = v.id
            p.updated_at = utcnow()
            session.add(p)
            await session.commit()
        await self._announce(p)
        return await self.get(p.id)

    async def adopt(self, version_id: str) -> ProductOut:
        """Adopt a version (and show it). Refused while a gate has the product locked."""
        async with self._db.session() as session:
            v = await require_version(session, version_id)
            p = await require_product(session, v.product_id)
            if p.locked_hash:
                raise PipelineError(409, "product_locked", id=p.id)
            await self._adopt(session, p, v)
            p.current_version_id = v.id
            p.updated_at = utcnow()
            session.add(p)
            await session.commit()
        await self._announce(p)
        return await self.get(p.id)

    async def lock(self, product_id: str) -> ProductOut:
        async with self._db.session() as session:
            p = await require_product(session, product_id)
            if not p.adopted_version_id:
                raise PipelineError(409, "nothing_adopted", id=p.id)
            adopted = await require_version(session, p.adopted_version_id)
            p.locked_hash = adopted.content_hash
            p.updated_at = utcnow()
            session.add(p)
            await session.commit()
        await self._announce(p)
        return await self.get(p.id)

    async def unlock(self, product_id: str) -> ProductOut:
        async with self._db.session() as session:
            p = await require_product(session, product_id)
            p.locked_hash = None
            p.updated_at = utcnow()
            session.add(p)
            await session.commit()
        await self._announce(p)
        return await self.get(p.id)

    # ------------------------------------------------------------------ internals

    async def _adopt(self, session: AsyncSession, p: Product, v: ProductVersion) -> None:
        p.adopted_version_id = v.id
        if p.status == "failed":
            p.status = "ready"
        materialize = self._materializers.get(p.slot)
        if materialize is not None:
            await materialize(session, p, v)

    async def _announce(self, p: Product) -> None:
        await self._bus.publish(
            EventType.PRODUCT_UPDATED,
            {"product_id": p.id, "series_id": p.series_id, "status": status_of(p)},
        )
