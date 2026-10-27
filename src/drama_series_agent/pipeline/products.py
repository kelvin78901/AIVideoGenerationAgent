"""Products and versions (SPEC 4.2).

Versions are append-only and are the source of truth. ``current`` is what the screen shows,
``adopted`` is what downstream uses, ``locked_hash`` is set when a gate locks the adopted one.
Only the first successful version of a product is adopted automatically; later runs only
become current, so an adopted version is never replaced behind the user's back (hard rule 5).
Candidate components (four pictures to choose from, M3) adopt nothing by themselves: the user
picks one and locks it (``lock_pick``).
Domain tables that mirror the adopted version register a materializer per slot (``on_adopt``).

The display status is worked out on read: a queued / running job first (from the ``job``
table), then a failed last run, stale (``pipeline/invalidation.py``), locked, adopted, ready.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import TYPE_CHECKING, Any

from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from drama_series_agent.core.db import Database
from drama_series_agent.core.events import EventBus, EventType
from drama_series_agent.core.models_db import Dependency, Job, Product, ProductVersion, utcnow
from drama_series_agent.pipeline.drafts import DependencyDraft, VersionDraft
from drama_series_agent.pipeline.errors import PipelineError
from drama_series_agent.pipeline.hashing import content_hash
from drama_series_agent.pipeline.schema import (
    EstimateOut,
    PickOut,
    ProductOut,
    PromptOut,
    RunningOut,
    VersionFileOut,
    VersionOut,
)

if TYPE_CHECKING:
    from drama_series_agent.pipeline.invalidation import Invalidation

__all__ = ["DependencyDraft", "ProductService", "VersionDraft", "product_public", "status_of"]

Materializer = Callable[[AsyncSession, Product, ProductVersion], Awaitable[None]]
# Writes what a lock decided (the asset gate's ``gate_decision``) in the lock's transaction.
LockRecorder = Callable[[AsyncSession, Product, ProductVersion], Awaitable[None]]
# Fills in what a product shows before its next run: the prompt (a default one if it never
# ran) and the estimate on the current route (pipeline/runs.py).
Describer = Callable[[Product], Awaitable[tuple[PromptOut | None, EstimateOut | None]]]
ACTIVE_JOB_STATES = ("queued", "waiting_confirm", "running")


def status_of(p: Product, *, job: Job | None = None, stale: bool = False) -> str:
    """Display status: an active job, a failed last run, stale, locked, adopted, ready."""
    if job is not None and job.state in ACTIVE_JOB_STATES:
        return "running" if job.state == "running" else "queued"
    if p.status == "failed":
        return "failed"
    if stale:
        return "stale"
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
    job: Job | None = None,
    stale: bool = False,
    prompt: PromptOut | None = None,
    estimate: EstimateOut | None = None,
) -> ProductOut:
    if p.prompt_json:
        prompt = PromptOut.model_validate(p.prompt_json)
    running = None
    if job is not None and job.state in ACTIVE_JOB_STATES:
        cascade = job.params_json.get("cascade")
        running = RunningOut(
            job_id=job.id,
            model_key=str(job.params_json.get("model_key", "")),
            state=job.state,
            cascade_id=str(cascade["id"]) if isinstance(cascade, dict) else None,
        )
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
        status=status_of(p, job=job, stale=stale),
        versions=[version_public(v) for v in sorted(versions, key=lambda v: v.n)],
        prompt=prompt,
        estimate=None if running else estimate,
        running=running,
        pick=PickOut.model_validate(p.pick_json) if p.pick_json else None,
        settings=p.settings_json,
        retired=p.retired,
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
    def __init__(
        self, db: Database, bus: EventBus, invalidation: Invalidation | None = None
    ) -> None:
        self._db = db
        self._bus = bus
        self._invalidation = invalidation
        self._materializers: dict[str, list[Materializer]] = {}
        self.describer: Describer | None = None
        # Slots of products made by the dozen (a line's audio): listed without the next run's
        # prompt and estimate, and a new take of one is not toasted.
        self.quiet_slots: set[str] = set()

    def on_adopt(self, slot: str, materializer: Materializer) -> None:
        """Rebuild the domain rows of ``slot`` from a newly adopted version (same transaction).
        Several run in the order they were registered (M4: an adopted script also gives its
        episode a 分镜规划 product)."""
        self._materializers.setdefault(slot, []).append(materializer)

    # ------------------------------------------------------------------ reads

    async def get(self, product_id: str) -> ProductOut:
        async with self._db.session() as session:
            p = await require_product(session, product_id)
            versions = await versions_of(session, p.id)
        return (await self._public(p.series_id, [p], {p.id: versions}))[0]

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
        return await self._public(None, products, by_product)

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
        make_current: bool = True,
    ) -> ProductVersion:
        """Append a version and make it current (unless ``make_current`` is False).

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
                workflow_id=draft.workflow_id,
                workflow_sha256=draft.workflow_sha256,
                comfy_env_hash=draft.comfy_env_hash,
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
            if make_current or p.current_version_id is None:
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
            {
                "product_id": p.id,
                "slot": p.slot,
                "version_id": v.id,
                "n": v.n,
                "origin": v.origin,
            },
        )
        await self._announce(p)
        return v

    async def append_edit(
        self, product_id: str, base: ProductVersion, payload: dict[str, Any]
    ) -> ProductVersion | None:
        """The user's edit of ``base`` (改设定、拖节拍、改剧本行): an adopted ``edit`` version with
        ``base``'s prompt and dependencies, so it turns stale with it. None when nothing
        changed."""
        if payload == base.payload_json:
            return None
        async with self._db.session() as session:
            deps = (
                await session.exec(select(Dependency).where(Dependency.version_id == base.id))
            ).all()
        draft = VersionDraft(
            payload=payload,
            intent=base.intent,
            compiled=base.compiled,
            compiled_overridden=base.compiled_overridden,
            dependencies=[
                DependencyDraft(d.upstream_product_id, d.upstream_hash, d.slice) for d in deps
            ],
        )
        return await self.append(
            product_id, draft, origin="edit", parent_version_id=base.id, adopt=True
        )

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

    async def unadopt(self, product_id: str) -> ProductOut:
        """「取消采纳」 (the take wall): nothing adopted until the user picks again. Refused
        while locked, and for slots whose adopted version is mirrored into domain tables
        (undoing that is not a thing those tables know)."""
        async with self._db.session() as session:
            p = await require_product(session, product_id)
            if p.locked_hash:
                raise PipelineError(409, "product_locked", id=p.id)
            if self._materializers.get(p.slot):
                raise PipelineError(409, "unadopt_unsupported", id=p.id, slot=p.slot)
            p.adopted_version_id = None
            p.updated_at = utcnow()
            session.add(p)
            await session.commit()
        await self._announce(p)
        return await self.get(p.id)

    async def rate(self, version_id: str, rating: int | None) -> ProductOut:
        """数字键打分 (1–5, None clears it); like ``note``, not part of what was made."""
        async with self._db.session() as session:
            v = await require_version(session, version_id)
            v.rating = rating
            session.add(v)
            await session.commit()
            p = await require_product(session, v.product_id)
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

    async def update_settings(self, product_id: str, changes: dict[str, Any]) -> ProductOut:
        """Merge ``changes`` into the product's settings (refused while locked: changing what
        a locked product was made from goes through the impact preview)."""
        async with self._db.session() as session:
            p = await require_product(session, product_id)
            if p.locked_hash:
                raise PipelineError(409, "product_locked", id=p.id)
            p.settings_json = {**(p.settings_json or {}), **changes}
            p.updated_at = utcnow()
            session.add(p)
            await session.commit()
        await self._announce(p)
        return await self.get(p.id)

    async def set_pick(self, product_id: str, version_id: str, idx: int) -> ProductOut:
        """「选这个」: remember candidate ``idx`` of a version (refused while locked)."""
        async with self._db.session() as session:
            p = await require_product(session, product_id)
            if p.locked_hash:
                raise PipelineError(409, "product_locked", id=p.id)
            source = await require_version(session, version_id)
            if source.product_id != p.id:
                raise PipelineError(404, "version_not_found", id=version_id)
            _candidate(source, idx)
            p.pick_json = {"version_id": source.id, "idx": idx}
            p.updated_at = utcnow()
            session.add(p)
            await session.commit()
        await self._announce(p)
        return await self.get(p.id)

    async def lock_pick(
        self,
        product_id: str,
        version_id: str,
        idx: int | None,
        *,
        record: LockRecorder | None = None,
    ) -> ProductVersion:
        """「锁定为参考」 (M3), in one transaction: candidate ``idx`` of a version becomes a
        ``pick`` version holding that file alone (``role: ref``, with the source's model, prompt
        and dependencies), which is adopted and locked; ``record`` writes the gate decision.
        ``idx`` None locks the version as it is (an upload, an API final, a voice).

        The current version stays, so the candidate grid keeps showing where the pick came
        from. The pick's hash is its file's content, so locking the same picture twice gives
        the same hash."""
        created = False
        async with self._db.session() as session:
            p = await require_product(session, product_id)
            if p.locked_hash:
                raise PipelineError(409, "product_locked", id=p.id)
            source = await require_version(session, version_id)
            if source.product_id != p.id:
                raise PipelineError(404, "version_not_found", id=version_id)
            v = source
            if idx is not None:
                v = await self._pick_version(session, p, source, idx)
                created = True
            await self._adopt(session, p, v)
            p.locked_hash = v.content_hash
            p.pick_json = {"version_id": source.id, "idx": idx or 0}
            p.updated_at = utcnow()
            session.add(p)
            if record is not None:
                await record(session, p, v)
            await session.commit()
            await session.refresh(v)
            await session.refresh(p)
        if created:
            await self._bus.publish(
                EventType.VERSION_CREATED,
                {
                    "product_id": p.id,
                    "slot": p.slot,
                    "version_id": v.id,
                    "n": v.n,
                    "origin": v.origin,
                },
            )
        await self._announce(p)
        return v

    async def unlock(self, product_id: str) -> ProductOut:
        async with self._db.session() as session:
            p = await require_product(session, product_id)
            p.locked_hash = None
            p.updated_at = utcnow()
            session.add(p)
            await session.commit()
        await self._announce(p)
        return await self.get(p.id)

    async def announce(self, product_id: str) -> None:
        """Tell the UI a product changed without a new version (a suggestion was decided:
        what downstream reads changed, so its status may have)."""
        async with self._db.session() as session:
            p = await require_product(session, product_id)
        await self._announce(p)

    async def set_prompt(self, product_id: str, prompt: dict[str, object]) -> None:
        async with self._db.session() as session:
            p = await require_product(session, product_id)
            p.prompt_json = dict(prompt)
            p.updated_at = utcnow()
            session.add(p)
            await session.commit()

    async def start_run(self, product_id: str, job_id: str) -> None:
        """A job will produce the next version; the product shows it as queued / running."""
        async with self._db.session() as session:
            p = await require_product(session, product_id)
            p.running_job_id = job_id
            p.updated_at = utcnow()
            session.add(p)
            await session.commit()
        await self._announce(p)

    async def finish_run(self, product_id: str, *, ok: bool | None) -> None:
        """The job ended: ``ok`` False marks the run failed, None (canceled) leaves it as was."""
        async with self._db.session() as session:
            p = await session.get(Product, product_id)
            if p is None:
                return
            p.running_job_id = None
            if ok is False:
                p.status = "failed"
            elif ok and p.status == "failed":
                p.status = "ready"
            p.updated_at = utcnow()
            session.add(p)
            await session.commit()
        await self._announce(p)

    # ------------------------------------------------------------------ internals

    async def _public(
        self,
        series_id: str | None,
        products: Sequence[Product],
        versions: dict[str, list[ProductVersion]],
    ) -> list[ProductOut]:
        async with self._db.session() as session:
            job_ids = [p.running_job_id for p in products if p.running_job_id]
            jobs = {
                j.id: j
                for j in (await session.exec(select(Job).where(col(Job.id).in_(job_ids)))).all()
            }
            stale = (
                await self._invalidation.stale_ids(session, products)
                if self._invalidation is not None
                else set()
            )
        out = []
        for p in products:
            prompt = estimate = None
            if self.describer is not None and p.slot not in self.quiet_slots:
                prompt, estimate = await self.describer(p)
            out.append(
                product_public(
                    p,
                    versions.get(p.id, []),
                    job=jobs.get(p.running_job_id or ""),
                    stale=p.id in stale,
                    prompt=prompt,
                    estimate=estimate,
                )
            )
        return out

    async def _pick_version(
        self, session: AsyncSession, p: Product, source: ProductVersion, idx: int
    ) -> ProductVersion:
        picked = {**_candidate(source, idx), "role": "ref"}
        prompts = [f for f in source.files_json if f.get("role") == "prompt"]
        candidates = source.payload_json.get("candidates")
        about = candidates[idx] if isinstance(candidates, list) and idx < len(candidates) else {}
        payload: dict[str, Any] = {"candidate": about}
        last_n = (
            await session.exec(
                select(func.max(ProductVersion.n)).where(ProductVersion.product_id == p.id)
            )
        ).one()
        v = ProductVersion(
            product_id=p.id,
            n=(last_n or 0) + 1,
            origin="pick",
            parent_version_id=source.id,
            payload_json=payload,
            files_json=[picked, *prompts],
            content_hash=content_hash(payload, [picked]),
            intent=source.intent,
            compiled=source.compiled,
            compiled_overridden=source.compiled_overridden,
            model_key=source.model_key,
            where=source.where,
            seed=source.seed,
            params_json={"from_version": source.id, "idx": idx},
            stage=source.stage,
        )
        session.add(v)
        await session.flush()
        query = select(Dependency).where(Dependency.version_id == source.id)
        for d in (await session.exec(query)).all():
            session.add(
                Dependency(
                    version_id=v.id,
                    product_id=p.id,
                    upstream_product_id=d.upstream_product_id,
                    slice=d.slice,
                    upstream_hash=d.upstream_hash,
                )
            )
        return v

    async def _adopt(self, session: AsyncSession, p: Product, v: ProductVersion) -> None:
        p.adopted_version_id = v.id
        if p.status == "failed":
            p.status = "ready"
        for materialize in self._materializers.get(p.slot, []):
            await materialize(session, p, v)

    async def _announce(self, p: Product) -> None:
        await self._bus.publish(
            EventType.PRODUCT_UPDATED,
            {
                "product_id": p.id,
                "series_id": p.series_id,
                "slot": p.slot,
                "status": status_of(p),
            },
        )


def _candidate(version: ProductVersion, idx: int) -> dict[str, Any]:
    """Candidate ``idx`` (``files[].idx``) of a version, or 422 ``no_such_candidate``."""
    for f in version.files_json:
        if f.get("role") == "candidate" and f.get("idx") == idx:
            return dict(f)
    raise PipelineError(422, "no_such_candidate", id=version.id, idx=idx)
