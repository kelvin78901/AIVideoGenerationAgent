"""Step gates (SPEC 4.2 ``gate_decision``; M2 plan step 10): 「确认原文」, 「确认剧本」 and
「素材确认」 (M3).

Confirming a gate locks the adopted version of each product it covers (``locked_hash``) and
records their effective hashes; reopening unlocks them. While a product is locked, editing it
goes through the impact preview (``pipeline/impact.py``). The novel gate covers the series'
novel, bible and suggestions (the front end sends an episode id as its scope; it is the
series'); the script gate covers one episode's script. The later gates arrive with their
milestones (the demo pages still get them from MSW).

The assets gate of an episode covers the assets it uses, which another service lists
(``members``): each is locked on its own (an asset belongs to the series), so confirming needs
them all locked already (409 ``assets_not_locked``) and records their hashes, and reopening
unlocks none. Unlocking an asset reopens the confirmed episodes that use it.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from drama_series_agent.bible.service import BIBLE_SLOT
from drama_series_agent.core.db import Database
from drama_series_agent.core.events import EventBus, EventType
from drama_series_agent.core.models_db import Episode, GateDecision, Job, Product, Series, utcnow
from drama_series_agent.episodes.service import SCRIPT_SLOT, latest_gate
from drama_series_agent.novel.service import NOVEL_SLOT
from drama_series_agent.pipeline.errors import PipelineError
from drama_series_agent.pipeline.invalidation import Invalidation
from drama_series_agent.pipeline.products import ACTIVE_JOB_STATES, ProductService
from drama_series_agent.suggestions.service import ADOPTED_SLICE, SUGGESTIONS_SLOT

GateId = Literal["novel", "script", "assets"]

# What each gate is about (the owner of its products) and the slots it locks; the first one
# must have something adopted. A gate without slots has its products listed by ``members``.
GATES: dict[str, tuple[str, tuple[str, ...]]] = {
    "novel": ("series", (NOVEL_SLOT, BIBLE_SLOT, SUGGESTIONS_SLOT)),
    "script": ("episode", (SCRIPT_SLOT,)),
    "assets": ("episode", ()),
}
# (session, scope id) → each product the gate covers, with the name the user knows it by.
Members = Callable[[AsyncSession, str], Awaitable[list[tuple[str, Product]]]]
# A product's effective hash is its whole adopted payload, except where downstream reads less
# (the suggestions: only the accepted ones, with the user's decisions).
_EFFECTIVE_SLICE = {SUGGESTIONS_SLOT: ADOPTED_SLICE}


class GateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope_id: str


class GateDecisionOut(BaseModel):
    id: str
    gate: str
    scope_id: str  # the series (novel gate) or the episode (script gate)
    action: Literal["confirm", "reopen"]
    decided_at: datetime


def gate_out(row: GateDecision) -> GateDecisionOut:
    return GateDecisionOut(
        id=row.id,
        gate=row.gate,
        scope_id=row.scope_id,
        action="confirm" if row.action == "confirm" else "reopen",
        decided_at=row.decided_at,
    )


def gate_of(owner_type: str, owner_id: str, slot: str) -> tuple[str, str] | None:
    """The gate a product is under and its scope id; None for a product no gate covers."""
    for gate, (owner, slots) in GATES.items():
        if owner_type == owner and slot in slots:
            return gate, owner_id
    return None


class GateService:
    def __init__(
        self, db: Database, bus: EventBus, products: ProductService, invalidation: Invalidation
    ) -> None:
        self._db = db
        self._bus = bus
        self._products = products
        self._invalidation = invalidation
        self._members: dict[str, Members] = {}

    def members(self, gate: str, fn: Members) -> None:
        self._members[gate] = fn

    async def confirm(self, gate: str, scope_id: str) -> GateDecisionOut:
        """Lock what the gate covers. Confirming again only locks again (one decision)."""
        if gate in self._members:
            return await self._confirm_members(gate, scope_id)
        async with self._db.session() as session:
            series_id, scope = await self._scope(session, gate, scope_id)
            products = await self._products_of(session, gate, scope)
            first = products.get(GATES[gate][1][0])
            if first is None or first.adopted_version_id is None:
                raise PipelineError(409, "nothing_adopted", gate=gate, scope_id=scope)
            for p in products.values():
                if p.running_job_id:
                    job = await session.get(Job, p.running_job_id)
                    if job is not None and job.state in ACTIVE_JOB_STATES:
                        raise PipelineError(409, "product_busy", id=p.id)
            adopted = [p for p in products.values() if p.adopted_version_id]
            hashes = {
                p.id: h
                for p in adopted
                if (
                    h := await self._invalidation.current_hash(
                        session, p.id, _EFFECTIVE_SLICE.get(p.slot, "")
                    )
                )
            }
        for p in adopted:
            if not p.locked_hash:
                await self._products.lock(p.id)
        return await self._record(series_id, gate, scope, "confirm", hashes)

    async def reopen(self, gate: str, scope_id: str) -> GateDecisionOut:
        """Unlock what the gate covers: it can be edited and rerun again, then confirmed."""
        async with self._db.session() as session:
            series_id, scope = await self._scope(session, gate, scope_id)
            products = await self._products_of(session, gate, scope)
        if gate in self._members:  # locked on their own: only the decision changes
            return await self._record(series_id, gate, scope, "reopen", {})
        for p in products.values():
            if p.locked_hash:
                await self._products.unlock(p.id)
        return await self._record(series_id, gate, scope, "reopen", {})

    async def reopen_for(self, product: Product) -> None:
        """Reopen the gate a product is under, if it is confirmed (the sync replaced it)."""
        found = gate_of(product.owner_type, product.owner_id, product.slot)
        if found is None:
            return
        gate, scope = found
        async with self._db.session() as session:
            row = await latest_gate(session, gate, scope)
        if row is not None and row.action == "confirm":
            await self.reopen(gate, scope)

    async def reopen_using(self, gate: str, product_id: str) -> list[str]:
        """Reopen the confirmed scopes of ``gate`` whose members include this product (an
        unlocked asset: the episodes that use it). Returns their ids."""
        fn = self._members.get(gate)
        if fn is None:
            return []
        async with self._db.session() as session:
            p = await session.get(Product, product_id)
            if p is None:
                return []
            rows = await session.exec(select(Episode).where(Episode.series_id == p.series_id))
            scopes: list[str] = []
            for e in rows.all():
                row = await latest_gate(session, gate, e.id)
                confirmed = row is not None and row.action == "confirm"
                if confirmed and any(m.id == product_id for _, m in await fn(session, e.id)):
                    scopes.append(e.id)
        for scope in scopes:
            await self.reopen(gate, scope)
        return scopes

    # ------------------------------------------------------------------ internals

    async def _confirm_members(self, gate: str, scope_id: str) -> GateDecisionOut:
        async with self._db.session() as session:
            series_id, scope = await self._scope(session, gate, scope_id)
            members = await self._members[gate](session, scope)
            if not members:
                raise PipelineError(409, "nothing_adopted", gate=gate, scope_id=scope)
            unlocked = [name for name, p in members if not p.locked_hash]
            if unlocked:
                raise PipelineError(
                    409,
                    f"{gate}_not_locked",
                    gate=gate,
                    scope_id=scope,
                    count=len(unlocked),
                    names="、".join(unlocked),
                )
            hashes = {
                p.id: h
                for _, p in members
                if (h := await self._invalidation.current_hash(session, p.id, ""))
            }
        return await self._record(series_id, gate, scope, "confirm", hashes)

    @staticmethod
    async def _scope(session: AsyncSession, gate: str, scope_id: str) -> tuple[str, str]:
        """(series id, the gate's scope id): the novel gate takes an episode or the series."""
        if gate not in GATES:
            raise PipelineError(404, "unknown_gate", gate=gate)
        episode = await session.get(Episode, scope_id)
        if episode is not None and not episode.retired:
            if gate == "novel":
                return episode.series_id, episode.series_id
            return episode.series_id, episode.id
        if gate == "novel" and await session.get(Series, scope_id) is not None:
            return scope_id, scope_id
        raise PipelineError(404, "episode_not_found", id=scope_id)

    @staticmethod
    async def _products_of(session: AsyncSession, gate: str, scope: str) -> dict[str, Product]:
        owner_type, slots = GATES[gate]
        rows = await session.exec(
            select(Product).where(Product.owner_type == owner_type, Product.owner_id == scope)
        )
        return {p.slot: p for p in rows.all() if p.slot in slots}

    async def _record(
        self, series_id: str, gate: str, scope: str, action: str, hashes: dict[str, str]
    ) -> GateDecisionOut:
        async with self._db.session() as session:
            last = await latest_gate(session, gate, scope)
            if last is not None and last.action == action:
                return gate_out(last)
            at = utcnow()
            if last is not None and at <= last.decided_at:  # keep them in order
                at = last.decided_at + timedelta(microseconds=1)
            row = GateDecision(
                series_id=series_id,
                gate=gate,
                scope_id=scope,
                action=action,
                product_hashes_json=hashes,
                decided_at=at,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
        await self._bus.publish(
            EventType.GATE_UPDATED,
            {"gate": gate, "scope_id": scope, "series_id": series_id, "action": action},
        )
        return gate_out(row)
