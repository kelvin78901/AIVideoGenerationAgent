"""Reading and editing the episode plan (SPEC 9.1 ``/series/{id}/episodes``, ``/episodes/…``,
``/beats/…``).

The plan is the series' ``episodes`` product (component ``split``). ``episode`` and ``beat``
mirror its adopted version (``materialize``), and that is what every page reads: the episodes
are where scripts, budgets and spending hang, so the list never shows a plan that is not
adopted (a rerun waits in the history until 采纳). The user's edits append an ``edit`` version
made from the adopted one and adopt it; it keeps the dependencies of the version it was made
from, so it turns stale with it. Each episode's slice ``episode:<id>`` (``ops.episode_slice``)
is what its script is written from, so dragging a beat makes exactly two scripts stale.
"""

from __future__ import annotations

from typing import Any

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from drama_series_agent.bible.schema import SourceSpanOut
from drama_series_agent.bible.service import BIBLE_SLOT
from drama_series_agent.core.db import Database
from drama_series_agent.core.models_db import (
    Beat,
    Episode,
    GateDecision,
    Job,
    Product,
    ProductVersion,
    Series,
    utcnow,
)
from drama_series_agent.episodes import ops
from drama_series_agent.episodes.schema import (
    STEP_IDS,
    BeatOut,
    BeatPatch,
    EpisodeOut,
    EpisodePatch,
    EpisodeProgressOut,
    ScriptStatus,
    StepId,
    StepProgressOut,
)
from drama_series_agent.pipeline.errors import PipelineError
from drama_series_agent.pipeline.invalidation import Invalidation
from drama_series_agent.pipeline.products import ACTIVE_JOB_STATES, ProductService
from drama_series_agent.script import ops as script_ops
from drama_series_agent.suggestions.service import SUGGESTIONS_SLOT

EPISODES_SLOT = "episodes"
SPLIT_COMPONENT = "split"
SCRIPT_SLOT = "script"
SCRIPT_COMPONENT = "script"


async def split_product(session: AsyncSession, series_id: str) -> Product | None:
    query = select(Product).where(
        Product.owner_type == "series", Product.owner_id == series_id, Product.slot == EPISODES_SLOT
    )
    return (await session.exec(query)).first()


async def script_product(session: AsyncSession, episode_id: str) -> Product | None:
    query = select(Product).where(
        Product.owner_type == "episode", Product.owner_id == episode_id, Product.slot == SCRIPT_SLOT
    )
    return (await session.exec(query)).first()


async def ensure_scripts(session: AsyncSession, series_id: str, episode_ids: list[str]) -> None:
    """Each episode has its 剧本化 product (owner ``episode``, slot ``script``)."""
    for episode_id in episode_ids:
        if await script_product(session, episode_id) is None:
            session.add(
                Product(
                    series_id=series_id,
                    owner_type="episode",
                    owner_id=episode_id,
                    slot=SCRIPT_SLOT,
                    component_id=SCRIPT_COMPONENT,
                )
            )


async def scene_counts(session: AsyncSession, series_id: str) -> list[dict[str, Any]]:
    """Each episode's id, number and scenes: the adopted script's once there is one, else the
    plan's estimate (``scene_count``), for the series-wide 场号."""
    rows = (
        await session.exec(
            select(Episode)
            .where(Episode.series_id == series_id, col(Episode.retired).is_(False))
            .order_by(col(Episode.idx))
        )
    ).all()
    out = []
    for r in rows:
        count = r.scene_count
        script = await script_product(session, r.id)
        if script is not None and script.adopted_version_id:
            v = await session.get(ProductVersion, script.adopted_version_id)
            if v is not None:
                count = script_ops.scene_count(v.payload_json)
        out.append({"id": r.id, "idx": r.idx, "scene_count": count})
    return out


async def materialize(session: AsyncSession, product: Product, version: ProductVersion) -> None:
    """Mirror an adopted plan: upsert episodes and beats by id (an episode's budget stays as the
    user set it), retire the ones it dropped; a new episode gets its 剧本化 product."""
    episodes = {
        r.id: r
        for r in (
            await session.exec(select(Episode).where(Episode.series_id == product.series_id))
        ).all()
    }
    beats = {
        r.id: r
        for r in (await session.exec(select(Beat).where(Beat.series_id == product.series_id))).all()
    }
    now = utcnow()
    kept: set[str] = set()
    for e in ops.episodes_of(version.payload_json):
        row = episodes.get(e["id"]) or Episode(
            id=e["id"], series_id=product.series_id, version_id=version.id, idx=e["idx"]
        )
        row.version_id = version.id
        row.idx = int(e["idx"])
        row.title = str(e.get("title") or "")
        row.hook = e.get("hook")
        row.cliffhanger = e.get("cliffhanger")
        row.target_seconds = e.get("target_seconds")
        row.scene_count = e.get("scene_count")
        row.retired = False
        row.updated_at = now
        session.add(row)
        kept.add(row.id)
        for b in e.get("beats") or []:
            beat = beats.get(b["id"]) or Beat(
                id=b["id"],
                series_id=product.series_id,
                episode_id=e["id"],
                version_id=version.id,
                idx=b["idx"],
            )
            beat.episode_id = e["id"]
            beat.version_id = version.id
            beat.idx = int(b["idx"])
            beat.text = str(b["text"])
            beat.emotion = float(b.get("emotion") or 0.0)
            beat.paras_json = list(b.get("paras") or [])
            beat.source_spans_json = list(b.get("source_spans") or [])
            beat.retired = False
            beat.updated_at = now
            session.add(beat)
            kept.add(beat.id)
    old: list[Episode | Beat] = [*episodes.values(), *beats.values()]
    for gone in old:
        if gone.id not in kept and not gone.retired:
            gone.retired = True
            gone.version_id = version.id
            gone.updated_at = now
            session.add(gone)
    await ensure_scripts(
        session, product.series_id, [e["id"] for e in ops.episodes_of(version.payload_json)]
    )


async def episodes_slicer(
    session: AsyncSession, product: Product, version: ProductVersion, name: str
) -> Any:
    """``episode:<id>``: one episode as its script reads it; other slices are payload keys."""
    payload = version.payload_json
    kind, _, key = name.partition(":")
    if kind == "episode":
        return ops.episode_slice(payload, key)
    return payload if name == "" else payload.get(name)


async def _latest_gate(session: AsyncSession, gate: str, scope_id: str) -> GateDecision | None:
    query = (
        select(GateDecision)
        .where(GateDecision.gate == gate, GateDecision.scope_id == scope_id)
        .order_by(col(GateDecision.decided_at).desc())
    )
    return (await session.exec(query)).first()


async def _confirmed(session: AsyncSession, gate: str, scope_id: str) -> bool:
    row = await _latest_gate(session, gate, scope_id)
    return row is not None and row.action == "confirm"


class EpisodeService:
    def __init__(self, db: Database, products: ProductService, invalidation: Invalidation) -> None:
        self._db = db
        self._products = products
        self._invalidation = invalidation

    # ------------------------------------------------------------------ reads

    async def list_episodes(self, series_id: str) -> list[EpisodeOut]:
        async with self._db.session() as session:
            if await session.get(Series, series_id) is None:
                raise PipelineError(404, "series_not_found", id=series_id)
            return await self._list(session, series_id)

    async def budget(self, episode_id: str) -> float | None:
        """What the episode may spend (``modelhub.budget``); None = no budget set."""
        async with self._db.session() as session:
            row = await session.get(Episode, episode_id)
        return row.budget_usd if row is not None and not row.retired else None

    async def progress(self, episode_id: str) -> EpisodeProgressOut:
        """The nav badges: 小说 and 剧本 from the products and gates; the later steps arrive
        with their milestones (not started until then)."""
        async with self._db.session() as session:
            ep = await self._episode(session, episode_id)
            series_products = list(
                (
                    await session.exec(
                        select(Product).where(
                            Product.owner_type == "series", Product.owner_id == ep.series_id
                        )
                    )
                ).all()
            )
            script = await self._script(session, ep.id)
            stale = await self._invalidation.stale_ids(
                session, [*series_products, *([script] if script else [])]
            )
            by_slot = {p.slot: p for p in series_products}

            def stale_of(*products: Product | None) -> int:
                return sum(1 for p in products if p is not None and p.id in stale)

            novel_confirmed = await _confirmed(session, "novel", ep.series_id)
            novel = StepProgressOut(
                state="confirmed" if novel_confirmed else "in_progress",
                stale=stale_of(by_slot.get(BIBLE_SLOT), by_slot.get(SUGGESTIONS_SLOT)),
            )
            status = await self._script_status(session, ep.id, script)
            script_step = StepProgressOut(
                state={"confirmed": "confirmed", "draft": "in_progress"}.get(status, "not_started"),
                stale=stale_of(by_slot.get(EPISODES_SLOT), script),
            )
        steps: dict[StepId, StepProgressOut] = {
            s: StepProgressOut(state="not_started") for s in STEP_IDS
        }
        steps["novel"] = novel
        steps["script"] = script_step
        return EpisodeProgressOut(episode_id=ep.id, steps=steps)

    # ------------------------------------------------------------------ edits

    async def patch_episode(self, episode_id: str, body: EpisodePatch) -> EpisodeOut:
        changes: dict[str, Any] = body.model_dump(exclude_unset=True)
        budget_set = "budget_usd" in changes
        budget = changes.pop("budget_usd", None)
        async with self._db.session() as session:
            ep = await self._episode(session, episode_id)
            series_id = ep.series_id
            if budget_set:
                ep.budget_usd = None if budget is None else round(float(budget), 4)
                ep.updated_at = utcnow()
                session.add(ep)
                await session.commit()
        if changes:
            p, v = await self._locate(series_id)
            payload = self._apply(lambda: ops.patch_episode(v.payload_json, episode_id, **changes))
            await self._edit(p, v, payload)
        listed = await self.list_episodes(series_id)
        return next(e for e in listed if e.id == episode_id)

    async def patch_beat(self, beat_id: str, body: BeatPatch) -> list[EpisodeOut]:
        """Returns the whole plan: a drag changes two episodes."""
        async with self._db.session() as session:
            row = await session.get(Beat, beat_id)
            if row is None or row.retired:
                raise PipelineError(404, "beat_not_found", id=beat_id)
            series_id = row.series_id
            if body.episode_id is not None:
                await self._episode(session, body.episode_id, series_id)
        p, v = await self._locate(series_id)
        payload = self._apply(
            lambda: ops.patch_beat(
                v.payload_json,
                beat_id,
                text=body.text,
                emotion=body.emotion,
                episode_id=body.episode_id,
                position=body.position,
            )
        )
        await self._edit(p, v, payload)
        return await self.list_episodes(series_id)

    # ------------------------------------------------------------------ internals

    async def _list(self, session: AsyncSession, series_id: str) -> list[EpisodeOut]:
        rows = list(
            (
                await session.exec(
                    select(Episode)
                    .where(Episode.series_id == series_id, col(Episode.retired).is_(False))
                    .order_by(col(Episode.idx))
                )
            ).all()
        )
        beats: dict[str, list[Beat]] = {}
        query = select(Beat).where(Beat.series_id == series_id, col(Beat.retired).is_(False))
        for b in (await session.exec(query.order_by(col(Beat.idx)))).all():
            beats.setdefault(b.episode_id, []).append(b)
        ranges = ops.scene_ranges(await scene_counts(session, series_id))
        out = []
        for r in rows:
            status = await self._script_status(session, r.id, await self._script(session, r.id))
            scenes = ranges.get(r.id)
            out.append(
                EpisodeOut(
                    id=r.id,
                    series_id=r.series_id,
                    idx=r.idx,
                    title=r.title,
                    hook=r.hook,
                    cliffhanger=r.cliffhanger,
                    target_seconds=r.target_seconds,
                    scene_count=r.scene_count,
                    budget_usd=r.budget_usd,
                    stage="script_pending" if status == "none" else "in_progress",
                    scene_from=scenes[0] if scenes else None,
                    scene_to=scenes[1] if scenes else None,
                    shot_count=None,
                    script_status=status,
                    beats=[
                        BeatOut(
                            id=b.id,
                            episode_id=r.id,
                            idx=b.idx,
                            text=b.text,
                            emotion=b.emotion,
                            paras=list(b.paras_json),
                            source_spans=[
                                SourceSpanOut.model_validate(s) for s in b.source_spans_json
                            ],
                        )
                        for b in beats.get(r.id, [])
                    ],
                )
            )
        return out

    @staticmethod
    async def _episode(
        session: AsyncSession, episode_id: str, series_id: str | None = None
    ) -> Episode:
        row = await session.get(Episode, episode_id)
        if row is None or row.retired or (series_id is not None and row.series_id != series_id):
            raise PipelineError(404, "episode_not_found", id=episode_id)
        return row

    @staticmethod
    async def _script(session: AsyncSession, episode_id: str) -> Product | None:
        return await script_product(session, episode_id)

    @staticmethod
    async def _script_status(
        session: AsyncSession, episode_id: str, script: Product | None
    ) -> ScriptStatus:
        if script is None or script.adopted_version_id is None:
            return "none"
        return "confirmed" if await _confirmed(session, "script", episode_id) else "draft"

    @staticmethod
    def _apply(fn: Any) -> Any:
        try:
            return fn()
        except ops.EpisodeEditError as exc:
            status = 404 if exc.code.endswith("_not_found") else 422
            raise PipelineError(status, exc.code, **exc.params) from exc

    async def _locate(self, series_id: str) -> tuple[Product, ProductVersion]:
        """The plan on screen (the adopted version); refuses a busy or locked product (an edit
        while 分集规划 runs would be lost when it finishes)."""
        async with self._db.session() as session:
            p = await split_product(session, series_id)
            v = (
                await session.get(ProductVersion, p.adopted_version_id)
                if p is not None and p.adopted_version_id
                else None
            )
            if p is None or v is None:
                raise PipelineError(409, "upstream_not_ready", slot=EPISODES_SLOT)
            if p.running_job_id:
                job = await session.get(Job, p.running_job_id)
                if job is not None and job.state in ACTIVE_JOB_STATES:
                    raise PipelineError(409, "product_busy", id=p.id)
            if p.locked_hash:
                raise PipelineError(409, "product_locked", id=p.id)
            return p, v

    async def _edit(self, p: Product, v: ProductVersion, payload: dict[str, Any]) -> None:
        await self._products.append_edit(p.id, v, payload)
