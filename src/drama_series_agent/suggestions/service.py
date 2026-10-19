"""Reading and deciding enrichment suggestions (SPEC 9.1 ``/series/{id}/suggestions``,
``/suggestions/…``).

The suggestions are the series' ``suggestions`` product (component ``enrich``). Reads show the
product's current version (adopted or not) with the user's decisions; deciding writes
``suggestion_decision`` only, never a version (``ops`` explains why). Downstream reads the
accepted ones through the ``adopted`` slice (``suggestions_slicer``), so 采纳 / 撤销采纳 makes
the bible stale and undoing it makes it fresh again. ``suggestion`` mirrors the adopted
version (``materialize``).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Literal, Protocol

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from drama_series_agent.core.db import Database
from drama_series_agent.core.models_db import (
    Job,
    Product,
    ProductVersion,
    Series,
    Suggestion,
    SuggestionDecision,
    utcnow,
)
from drama_series_agent.novel.service import NovelService
from drama_series_agent.pipeline.errors import PipelineError
from drama_series_agent.pipeline.products import ACTIVE_JOB_STATES, ProductService
from drama_series_agent.suggestions import ops
from drama_series_agent.suggestions.schema import (
    RewriteIn,
    SuggestionOut,
    SuggestionsOut,
    suggestion_out,
    suggestions_out,
)

SUGGESTIONS_SLOT = "suggestions"
ENRICH_COMPONENT = "enrich"
ADOPTED_SLICE = "adopted"


class Rewriter(Protocol):
    """「按要求重写这一条」 (the enrich component): returns (new text, model key)."""

    async def rewrite(
        self,
        product: Product,
        suggestion: Mapping[str, Any],
        paragraph: str,
        instruction: str,
        *,
        confirm_budget: bool,
    ) -> tuple[str, str]: ...


async def enrich_product(session: AsyncSession, series_id: str) -> Product | None:
    query = select(Product).where(
        Product.owner_type == "series",
        Product.owner_id == series_id,
        Product.slot == SUGGESTIONS_SLOT,
    )
    return (await session.exec(query)).first()


def _decision(row: SuggestionDecision) -> dict[str, Any]:
    return {
        "status": row.status,
        "text": row.text,
        "rewrite_instruction": row.rewrite_instruction,
        "rewritten_by": row.rewritten_by,
    }


async def decisions_of(session: AsyncSession, ids: Iterable[str]) -> dict[str, dict[str, Any]]:
    wanted = list(ids)
    if not wanted:
        return {}
    query = select(SuggestionDecision).where(col(SuggestionDecision.suggestion_id).in_(wanted))
    return {r.suggestion_id: _decision(r) for r in (await session.exec(query)).all()}


async def _payload_decisions(
    session: AsyncSession, payload: Mapping[str, Any]
) -> dict[str, dict[str, Any]]:
    return await decisions_of(session, (s["id"] for s in payload.get("suggestions") or []))


async def suggestions_slicer(
    session: AsyncSession, product: Product, version: ProductVersion, name: str
) -> Any:
    """``adopted``: the accepted suggestions with their final text (what downstream reads)."""
    payload = version.payload_json
    if name == ADOPTED_SLICE:
        return ops.additions(payload, await _payload_decisions(session, payload))
    return payload if name == "" else payload.get(name)


async def adopted_additions(
    session: AsyncSession, series_id: str
) -> tuple[str, list[dict[str, Any]]] | None:
    """(product id, accepted additions) of the series' adopted 小说补全; None before one."""
    p = await enrich_product(session, series_id)
    if p is None or p.adopted_version_id is None:
        return None
    v = await session.get(ProductVersion, p.adopted_version_id)
    if v is None:
        return None
    payload = v.payload_json
    return p.id, ops.additions(payload, await _payload_decisions(session, payload))


async def materialize(session: AsyncSession, product: Product, version: ProductVersion) -> None:
    """Mirror an adopted version: upsert its suggestions by id, retire the ones it dropped."""
    query = select(Suggestion).where(Suggestion.series_id == product.series_id)
    rows = {r.id: r for r in (await session.exec(query)).all()}
    now = utcnow()
    kept: set[str] = set()
    for s in version.payload_json.get("suggestions") or []:
        row = rows.get(s["id"]) or Suggestion(
            id=s["id"],
            series_id=product.series_id,
            version_id=version.id,
            kind=s["kind"],
            para_idx=s["para_idx"],
        )
        row.version_id = version.id
        row.kind = s["kind"]
        row.para_idx = s["para_idx"]
        row.anchor_span_json = dict(s.get("anchor_span") or {})
        row.reason = s.get("reason") or ""
        row.text = s["text"]
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


class SuggestionService:
    def __init__(
        self,
        db: Database,
        products: ProductService,
        novel: NovelService,
        rewriter: Rewriter | None = None,
    ) -> None:
        self._db = db
        self._products = products
        self._novel = novel
        self.rewriter = rewriter

    # ------------------------------------------------------------------ reads

    async def get(self, series_id: str) -> SuggestionsOut:
        async with self._db.session() as session:
            if await session.get(Series, series_id) is None:
                raise PipelineError(404, "series_not_found", id=series_id)
            p = await enrich_product(session, series_id)
            v = await self._current(session, p)
            if p is None or v is None:
                return suggestions_out(series_id, None, {}, product_id=p.id if p else None)
            decisions = await _payload_decisions(session, v.payload_json)
        return suggestions_out(
            series_id,
            v.payload_json,
            decisions,
            product_id=p.id,
            version_id=v.id,
            adopted=v.id == p.adopted_version_id,
        )

    # ------------------------------------------------------------------ decisions

    async def decide(
        self, suggestion_id: str, action: Literal["accept", "reject", "reset"]
    ) -> SuggestionOut:
        """采纳 / 忽略 / 撤销 (reset: back to undecided, or to 「已重写」 after a rewrite)."""
        p, s = await self._locate(suggestion_id)
        async with self._db.session() as session:
            row = await self._row(session, p, suggestion_id)
            if action == "accept":
                row.status = "accepted"
            elif action == "reject":
                row.status = "rejected"
            else:
                row.status = "rewritten" if row.rewrite_instruction else "pending"
            decision = await self._save(session, row)
        await self._products.announce(p.id)
        return suggestion_out(p.series_id, s, decision)

    async def accept_all(self, series_id: str) -> SuggestionsOut:
        """「全部采纳」: every suggestion on screen that was not ignored."""
        async with self._db.session() as session:
            if await session.get(Series, series_id) is None:
                raise PipelineError(404, "series_not_found", id=series_id)
            p = await enrich_product(session, series_id)
            v = await self._current(session, p)
            if p is None or v is None:
                return await self.get(series_id)
            await self._guard(session, p)
            for s in v.payload_json.get("suggestions") or []:
                row = await self._row(session, p, s["id"])
                if row.status != "rejected":
                    row.status = "accepted"
                    row.updated_at = utcnow()
                    session.add(row)
            await session.commit()
        await self._products.announce(p.id)
        return await self.get(series_id)

    async def rewrite(self, suggestion_id: str, body: RewriteIn) -> SuggestionOut:
        """「按要求重写这一条」 on the component's route; kept as the decision's text (an accepted
        suggestion stays accepted with the new text)."""
        instruction = body.instruction.strip()
        if not instruction:
            raise PipelineError(422, "instruction_required")
        if self.rewriter is None:
            raise PipelineError(409, "component_not_ready", id=ENRICH_COMPONENT)
        p, s = await self._locate(suggestion_id)
        async with self._db.session() as session:
            span = s.get("anchor_span") or {}
            book = await self._novel.book_of(session, str(span.get("source_id")))
            decision = (await decisions_of(session, [suggestion_id])).get(suggestion_id)
        paragraph = book.paragraph(int(s["para_idx"])) if book is not None else ""
        current = {**s, "text": ops.final_text(s, decision)}
        text, model = await self.rewriter.rewrite(
            p, current, paragraph, instruction, confirm_budget=body.confirm_budget
        )
        async with self._db.session() as session:
            row = await self._row(session, p, suggestion_id)
            row.text = text
            row.rewrite_instruction = instruction
            row.rewritten_by = model
            if row.status != "accepted":
                row.status = "rewritten"
            saved = await self._save(session, row)
        await self._products.announce(p.id)
        return suggestion_out(p.series_id, s, saved)

    # ------------------------------------------------------------------ internals

    @staticmethod
    async def _current(session: AsyncSession, p: Product | None) -> ProductVersion | None:
        if p is None or p.current_version_id is None:
            return None
        return await session.get(ProductVersion, p.current_version_id)

    @staticmethod
    async def _guard(session: AsyncSession, p: Product) -> None:
        """A decision changes what downstream reads: not while enrichment runs (its result
        would carry the old decisions) nor while a gate has it locked."""
        if p.running_job_id:
            job = await session.get(Job, p.running_job_id)
            if job is not None and job.state in ACTIVE_JOB_STATES:
                raise PipelineError(409, "product_busy", id=p.id)
        if p.locked_hash:
            raise PipelineError(409, "product_locked", id=p.id)

    async def _locate(self, suggestion_id: str) -> tuple[Product, dict[str, Any]]:
        """The 小说补全 product whose version on screen has this suggestion."""
        async with self._db.session() as session:
            row = await session.get(Suggestion, suggestion_id)
            if row is not None:
                products = [p] if (p := await enrich_product(session, row.series_id)) else []
            else:
                query = select(Product).where(Product.slot == SUGGESTIONS_SLOT)
                products = list((await session.exec(query.order_by(col(Product.created_at)))).all())
            for p in products:
                v = await self._current(session, p)
                s = ops.find(v.payload_json, suggestion_id) if v is not None else None
                if s is not None:
                    await self._guard(session, p)
                    return p, s
        raise PipelineError(404, "suggestion_not_found", id=suggestion_id)

    @staticmethod
    async def _row(session: AsyncSession, p: Product, suggestion_id: str) -> SuggestionDecision:
        row = await session.get(SuggestionDecision, suggestion_id)
        return row or SuggestionDecision(suggestion_id=suggestion_id, series_id=p.series_id)

    @staticmethod
    async def _save(session: AsyncSession, row: SuggestionDecision) -> dict[str, Any]:
        row.updated_at = utcnow()
        session.add(row)
        await session.commit()
        return _decision(row)
