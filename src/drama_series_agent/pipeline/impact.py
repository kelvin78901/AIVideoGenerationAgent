"""Change impact (SPEC 9.1 ``/impact/preview|apply``; PLAN 失效传播; M2 plan step 10).

Editing confirmed work (a product a gate has locked) is previewed first. The domain service
works the change out without writing it (``PlannedChange``); the preview stages it in a
transaction that is rolled back (its version written and adopted, or its decision saved), so
the slice hashes downstream reads come from the same code as staleness
(``pipeline/invalidation.py``). Products with a dependency on a slice that changes are
directly affected; what depends on those, further down, is listed as optional (it reruns only
if the rerun changes what it reads).

``apply``: ``undo`` drops the preview; ``mark`` writes the change, lifting the lock for the
write and putting it back (the gate stays confirmed: the user confirmed this change), and
staleness follows on its own; ``rerun`` (确认并同步) writes it the same way and hands what
it made stale to ``pipeline/cascade.py`` (rerun and adopt, down to the scripts). A preview lives
in memory
until it is applied (a restart loses it: 404 ``impact_not_found``, preview again); applying
re-plans the change and refuses it (409 ``impact_outdated``) when what it was made from has
changed since.
"""

from __future__ import annotations

from collections import OrderedDict, deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from drama_series_agent.bible.schema import BibleMergeIn, BiblePatch
from drama_series_agent.bible.service import BIBLE_SLOT, BibleService
from drama_series_agent.core.db import Database
from drama_series_agent.core.models_db import (
    Dependency,
    Episode,
    Product,
    ProductVersion,
    new_id,
)
from drama_series_agent.episodes.schema import BeatPatch
from drama_series_agent.episodes.service import EPISODES_SLOT, SCRIPT_SLOT, EpisodeService
from drama_series_agent.novel.schema import ChapterEditIn
from drama_series_agent.novel.service import NOVEL_SLOT, NovelService
from drama_series_agent.pipeline.components.assets import ASSET_LIST_SLOT
from drama_series_agent.pipeline.drafts import PlannedChange
from drama_series_agent.pipeline.errors import PipelineError
from drama_series_agent.pipeline.gates import gate_of
from drama_series_agent.pipeline.hashing import content_hash
from drama_series_agent.pipeline.invalidation import Invalidation
from drama_series_agent.pipeline.products import ProductService
from drama_series_agent.script.schema import LinePatch, ScenePatch
from drama_series_agent.script.service import ScriptService
from drama_series_agent.suggestions.service import SUGGESTIONS_SLOT, SuggestionService

ImpactAction = Literal["mark", "rerun", "undo"]
Planner = Callable[[str, dict[str, Any]], Awaitable[PlannedChange]]
# The next run's price of a product on its current route; None = free (local) or unknown.
Estimator = Callable[[Product], Awaitable[float | None]]

# Pipeline order (of the lines, and of a sync's reruns); the navigation step each slot's
# 「待更新」 counts in. The suggestions come before the bible: the bible is extracted from the
# text plus the accepted additions, while the suggestions only read its names (M2 plan 计划变更
# 5), so a sync that reruns both builds the bible from the new suggestions.
PIPELINE_ORDER = {
    NOVEL_SLOT: 0,
    SUGGESTIONS_SLOT: 1,
    BIBLE_SLOT: 2,
    EPISODES_SLOT: 3,
    SCRIPT_SLOT: 4,
    ASSET_LIST_SLOT: 5,
    "ref_image": 6,
    "text_image": 6,
    "voice": 6,
    "ref_views": 7,
}
_STEP = {
    NOVEL_SLOT: "novel",
    BIBLE_SLOT: "novel",
    SUGGESTIONS_SLOT: "novel",
    EPISODES_SLOT: "script",
    SCRIPT_SLOT: "script",
    ASSET_LIST_SLOT: "assets",
    "ref_image": "assets",
    "text_image": "assets",
    "voice": "assets",
    "ref_views": "assets",
}
_KEPT = 100  # previews kept in memory


class Cascader(Protocol):
    """确认并同步 (``pipeline/cascade.py``): returns the first reruns' job ids."""

    async def start(self, series_id: str, origin: str) -> list[str]: ...


class ImpactChangeIn(BaseModel):
    """``POST /impact/preview``: the change, not written yet."""

    model_config = ConfigDict(extra="forbid")

    kind: str
    target_id: str
    patch: dict[str, Any] = Field(default_factory=dict)


class MessageOut(BaseModel):
    code: str
    params: dict[str, Any] = Field(default_factory=dict)


class ImpactLineOut(MessageOut):
    cost_usd: float | None
    optional: bool


class ImpactOut(BaseModel):
    id: str
    change: ImpactChangeIn
    lines: list[ImpactLineOut]
    unaffected: MessageOut | None
    rerun_cost_usd: float
    stale: dict[str, int]  # navigation step → products it would mark 待更新


class ImpactApplyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    impact_id: str
    action: ImpactAction


class ImpactApplyOut(BaseModel):
    action: ImpactAction
    stale: dict[str, int]
    job_ids: list[str]


@dataclass(frozen=True)
class Node:
    """A product as the preview reads it (copied out before the staged write is rolled back)."""

    id: str
    slot: str
    owner_type: str
    owner_id: str
    locked: bool
    edited: bool  # its adopted version is the user's edit
    n: int | None  # episode number of an episode's product


@dataclass
class _Affected:
    nodes: dict[str, Node]
    direct: list[str]
    further: list[str]
    noop: bool  # the change writes nothing new


@dataclass
class _Preview:
    change: ImpactChangeIn
    planned: PlannedChange
    stale: dict[str, int] = field(default_factory=dict)


def rank(node: Node) -> tuple[int, int]:
    """Where a product comes in the pipeline (an episode's after the one before)."""
    return PIPELINE_ORDER.get(node.slot, 9), node.n or 0


async def series_graph(
    session: AsyncSession, series_id: str
) -> tuple[dict[str, Node], list[tuple[str, str, str]]]:
    """The series' products, and what each one shows (adopted, else current) was built from:
    (product, upstream product, slice). Plain data: it outlives a rolled-back session."""
    query = select(Product).where(Product.series_id == series_id)
    products = list((await session.exec(query)).all())
    shown = [v for p in products if (v := p.adopted_version_id or p.current_version_id)]
    deps = await session.exec(select(Dependency).where(col(Dependency.version_id).in_(shown)))
    edges = sorted({(d.product_id, d.upstream_product_id, d.slice) for d in deps.all()})
    adopted = [p.adopted_version_id for p in products if p.adopted_version_id]
    versions = await session.exec(select(ProductVersion).where(col(ProductVersion.id).in_(adopted)))
    origins = {v.id: v.origin for v in versions.all()}
    rows = await session.exec(select(Episode).where(Episode.series_id == series_id))
    episodes = {e.id: e.idx for e in rows.all()}
    nodes = {
        p.id: Node(
            id=p.id,
            slot=p.slot,
            owner_type=p.owner_type,
            owner_id=p.owner_id,
            locked=bool(p.locked_hash),
            edited=origins.get(p.adopted_version_id or "") == "edit",
            n=episodes.get(p.owner_id) if p.owner_type == "episode" else None,
        )
        for p in products
    }
    return nodes, edges


class ImpactService:
    def __init__(
        self,
        db: Database,
        products: ProductService,
        invalidation: Invalidation,
        estimate: Estimator,
    ) -> None:
        self._db = db
        self._products = products
        self._invalidation = invalidation
        self._estimate = estimate
        self._planners: dict[str, Planner] = {}
        self.cascade: Cascader | None = None
        self._previews: OrderedDict[str, _Preview] = OrderedDict()

    def kind(self, name: str, planner: Planner) -> None:
        self._planners[name] = planner

    # ------------------------------------------------------------------ preview

    async def preview(self, change: ImpactChangeIn) -> ImpactOut:
        planned = await self._plan(change)
        found = await self._affected(planned)
        lines, stale, total = await self._describe(planned, found)
        impact_id = f"imp-{new_id()}"
        unaffected = planned.unaffected
        self._previews[impact_id] = _Preview(change, planned, stale)
        while len(self._previews) > _KEPT:
            self._previews.popitem(last=False)
        return ImpactOut(
            id=impact_id,
            change=change,
            lines=lines,
            unaffected=MessageOut.model_validate(unaffected) if unaffected else None,
            rerun_cost_usd=total,
            stale=stale,
        )

    # ------------------------------------------------------------------ apply

    async def apply(self, body: ImpactApplyIn) -> ImpactApplyOut:
        if body.impact_id not in self._previews:
            raise PipelineError(404, "impact_not_found", id=body.impact_id)
        preview = self._previews.pop(body.impact_id)
        if body.action == "undo":
            return ImpactApplyOut(action="undo", stale={}, job_ids=[])
        planned = await self._plan(preview.change)
        before = preview.planned
        if (planned.base_version_id, planned.content) != (before.base_version_id, before.content):
            raise PipelineError(409, "impact_outdated", id=body.impact_id)
        await self._write(planned)
        jobs: list[str] = []
        if body.action == "rerun" and self.cascade is not None:
            jobs = await self.cascade.start(planned.series_id, planned.product_id)
        return ImpactApplyOut(action=body.action, stale=preview.stale, job_ids=jobs)

    async def _write(self, planned: PlannedChange) -> None:
        """Commit a change to a locked product: unlock for the write, lock what it adopted."""
        async with self._db.session() as session:
            p = await session.get(Product, planned.product_id)
        locked = p is not None and bool(p.locked_hash)
        if not planned.relock:
            await planned.commit()
            return
        if locked:
            await self._products.unlock(planned.product_id)
        try:
            await planned.commit()
        finally:
            if locked:
                await self._products.lock(planned.product_id)

    # ------------------------------------------------------------------ internals

    async def _plan(self, change: ImpactChangeIn) -> PlannedChange:
        planner = self._planners.get(change.kind)
        if planner is None:
            raise PipelineError(422, "unknown_change_kind", kind=change.kind)
        try:
            return await planner(change.target_id, change.patch)
        except ValidationError as exc:
            raise PipelineError(422, "invalid_patch", kind=change.kind, issues=str(exc)) from exc

    async def _affected(self, planned: PlannedChange) -> _Affected:
        async with self._db.session() as session:
            nodes, edges = await series_graph(session, planned.series_id)
            keys = {(up, name) for _, up, name in edges}
            changed: set[tuple[str, str]] = set()
            noop = await self._noop(session, planned)
            if not noop:
                before = {k: await self._invalidation.current_hash(session, *k) for k in keys}
                # SQLite starts the write transaction here (the reads above ran outside one),
                # and nothing staged is ever committed.
                await self._stage(session, planned)
                after = {k: await self._invalidation.current_hash(session, *k) for k in keys}
                changed = {k for k in keys if before[k] != after[k]}
            await session.rollback()
        me = planned.product_id
        direct = {down for down, up, name in edges if (up, name) in changed and down != me}
        below: dict[str, set[str]] = {}
        for down, up, _ in edges:
            below.setdefault(up, set()).add(down)
        reached: set[str] = set()
        queue = deque(direct)
        while queue:
            for nxt in below.get(queue.popleft(), ()):
                if nxt not in reached and nxt not in direct and nxt != me:
                    reached.add(nxt)
                    queue.append(nxt)

        def ordered(ids: set[str]) -> list[str]:
            return sorted(ids, key=lambda i: rank(nodes[i]))

        return _Affected(nodes, ordered(direct), ordered(reached), noop)

    @staticmethod
    async def _noop(session: AsyncSession, planned: PlannedChange) -> bool:
        if planned.stage is not None:
            return False
        if planned.payload is None:
            return True
        base = (
            await session.get(ProductVersion, planned.base_version_id)
            if planned.base_version_id
            else None
        )
        return base is not None and base.payload_json == planned.payload

    @staticmethod
    async def _stage(session: AsyncSession, planned: PlannedChange) -> None:
        if planned.stage is not None:
            await planned.stage(session)
        if planned.payload is not None:
            p = await session.get(Product, planned.product_id)
            assert p is not None
            v = ProductVersion(
                product_id=p.id,
                n=0,
                origin="edit",
                payload_json=planned.payload,
                content_hash=content_hash(planned.payload, []),
            )
            session.add(v)
            await session.flush()
            p.adopted_version_id = v.id
            session.add(p)
        await session.flush()

    async def _describe(
        self, planned: PlannedChange, found: _Affected
    ) -> tuple[list[ImpactLineOut], dict[str, int], float]:
        nodes = found.nodes
        ids = [*found.direct, *found.further]
        costs: dict[str, float | None] = {}
        async with self._db.session() as session:
            rows = (await session.exec(select(Product).where(col(Product.id).in_(ids)))).all()
        for p in rows:
            costs[p.id] = await self._estimate(p)

        def line(
            code: str, node: Node, *, cost: float | None = None, optional: bool = False
        ) -> ImpactLineOut:
            params: dict[str, Any] = {"n": node.n} if node.n is not None else {}
            return ImpactLineOut(code=code, params=params, cost_usd=cost, optional=optional)

        lines: list[ImpactLineOut] = []
        me = nodes.get(planned.product_id)
        if me is not None and me.locked and not found.noop:
            lines.append(line(f"self_{me.slot}", me))
        lines += [line(f"stale_{nodes[i].slot}", nodes[i], cost=costs.get(i)) for i in found.direct]
        lines += [
            line(f"then_{nodes[i].slot}", nodes[i], cost=costs.get(i), optional=True)
            for i in found.further
        ]
        gates: dict[tuple[str, str], Node] = {}
        for i in ids:
            node = nodes[i]
            under = gate_of(node.owner_type, node.owner_id, node.slot) if node.locked else None
            if under is not None:
                gates.setdefault(under, node)
        lines += [line(f"gate_{gate}", node) for (gate, _), node in gates.items()]
        lines += [line(f"edited_{nodes[i].slot}", nodes[i]) for i in ids if nodes[i].edited]
        lines += [ImpactLineOut.model_validate(x) for x in planned.lines]

        stale: dict[str, int] = {}
        for i in found.direct:
            step = _STEP.get(nodes[i].slot)
            if step:
                stale[step] = stale.get(step, 0) + 1
        total = round(sum(c for c in costs.values() if c), 4)
        return lines, stale, total


# ------------------------------------------------------------------ the kinds of change


class _Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["accept", "reject", "reset"]


class _ChapterEdit(ChapterEditIn):
    chapter: int = Field(ge=0)


class _Replace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    upload_id: str
    filename: str = Field(max_length=300)


def register_kinds(
    impact: ImpactService,
    *,
    novel: NovelService,
    bible: BibleService,
    suggestions: SuggestionService,
    episodes: EpisodeService,
    script: ScriptService,
) -> None:
    """The changes the preview knows (M2): what the front end sends as ``patch`` for each."""

    async def line_edit(target: str, patch: dict[str, Any]) -> PlannedChange:
        return await script.plan_line(target, LinePatch.model_validate(patch), allow_locked=True)

    async def scene_edit(target: str, patch: dict[str, Any]) -> PlannedChange:
        # The script page sends the block's text; the API's field is the heading.
        heading = patch.get("heading", patch.get("text"))
        body = ScenePatch.model_validate({"heading": heading})
        return await script.plan_scene(target, body, allow_locked=True)

    async def bible_edit(target: str, patch: dict[str, Any]) -> PlannedChange:
        return await bible.plan_patch(target, BiblePatch.model_validate(patch), allow_locked=True)

    async def bible_merge(target: str, patch: dict[str, Any]) -> PlannedChange:
        body = BibleMergeIn.model_validate({"ids": [target], **patch})
        return await bible.plan_merge(body, allow_locked=True)

    async def suggestion_decision(target: str, patch: dict[str, Any]) -> PlannedChange:
        return await suggestions.plan_decision(target, _Decision.model_validate(patch).action)

    async def beat_move(target: str, patch: dict[str, Any]) -> PlannedChange:
        return await episodes.plan_beat(target, BeatPatch.model_validate(patch))

    async def novel_edit(target: str, patch: dict[str, Any]) -> PlannedChange:
        body = _ChapterEdit.model_validate(patch)
        return await novel.plan_edit(
            target, body.chapter, body.title, body.paragraphs, allow_locked=True
        )

    async def novel_replace(target: str, patch: dict[str, Any]) -> PlannedChange:
        body = _Replace.model_validate(patch)
        return await novel.plan_replace(target, body.upload_id, body.filename)

    for name, planner in {
        "line_edit": line_edit,
        "scene_edit": scene_edit,
        "bible_edit": bible_edit,
        "bible_merge": bible_merge,
        "suggestion_decision": suggestion_decision,
        "beat_move": beat_move,
        "novel_edit": novel_edit,
        "novel_replace": novel_replace,
    }.items():
        impact.kind(name, planner)
