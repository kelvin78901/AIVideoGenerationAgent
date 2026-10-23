"""An episode's shots (M4): ``GET /episodes/{id}/shots``, ``PATCH /shots/{id}``,
``POST /shots/{id}/split|merge``.

The list is read from the shot plan's version on screen (its current one, like the script
page); the ``shot`` table mirrors the adopted one (``materialize``), and each shot that is not
continuous has its keyframe product (owner ``shot``, slot ``keyframe``). Edits to the plan
append an ``edit`` version and adopt it; the picture description is the keyframe prompt's
intent layer and the picked candidate is the keyframe product's pick, so neither touches the
plan (M3: 描述 = 意图层).

How long a shot runs is worked out when read (``timing.shot_duration``, Kelvin 2026-10-21):
dubbing again changes it without a new version.

**确认这个镜头** (``confirmed: true``) locks the keyframe's picked candidate (``lock_pick``; a
final's lone picture is locked as it is) and writes the shot's own ``gate_decision`` (gate
``shot``, scope the shot id) with the hashes of its settings (the plan's ``shot:<id>`` slice)
and of the locked keyframe, in one transaction. A continuous shot has no keyframe: only the
decision. Taking it back unlocks the keyframe and writes ``reopen``. A confirmed shot is
「待更新」 (``confirm_stale``) when its settings or its keyframe changed since; it is not edited
in place (409 ``shot_confirmed``): that goes through the impact preview (``shot_edit``), which
takes the confirmation back. The output spec locks when the first keyframe is adopted
(``lock_spec``, SPEC 13.3).

**分镜确认** (gate ``storyboard``) locks the episode's plan once every shot is confirmed and
none is 「待更新」 (``register``: its precondition, the 分镜 badge); taking a shot's
confirmation back reopens it. **改画幅** (``spec_aspect``) lists the keyframes drawn for the old
aspect: 「只改这里」 writes the spec and takes the shots' confirmations back, 「确认并同步」 also
draws the keyframes again (local drafts).
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from loguru import logger
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from drama_series_agent.core.db import Database
from drama_series_agent.core.models_db import (
    Asset,
    Episode,
    GateDecision,
    Job,
    OutputSpecRow,
    Product,
    ProductVersion,
    Scene,
    ScriptLine,
    Shot,
    utcnow,
)
from drama_series_agent.episodes.schema import StepProgressOut
from drama_series_agent.episodes.service import (
    EpisodeService,
    gate_confirmed,
    latest_gate,
    scene_numbers,
)
from drama_series_agent.pipeline.components.dub import LINE_AUDIO_SLOT
from drama_series_agent.pipeline.components.plan import (
    SHOT_PLAN_SLOT,
    PlanComponent,
    episode_assets,
    plan_product,
    shot_slice,
)
from drama_series_agent.pipeline.drafts import PlannedChange
from drama_series_agent.pipeline.errors import PipelineError
from drama_series_agent.pipeline.gates import GateService
from drama_series_agent.pipeline.impact import ImpactService
from drama_series_agent.pipeline.invalidation import Invalidation
from drama_series_agent.pipeline.products import ACTIVE_JOB_STATES, ProductService
from drama_series_agent.pipeline.runs import RunService
from drama_series_agent.pipeline.timing import ShotDuration, line_seconds, shot_duration
from drama_series_agent.shots import ops
from drama_series_agent.shots.schema import ShotEditIn, ShotOut, ShotPatch, ShotSplitIn
from drama_series_agent.spec.schema import SpecPatch, apply_patch

KEYFRAME_SLOT = "keyframe"
KF_COMPONENT = "kf"
SHOT_GATE = "shot"
STORYBOARD_GATE = "storyboard"
# The longest take the video route can make (seconds); None when no model on it says.
LongestTake = Callable[[], Awaitable[float | None]]
_HEADING_MARKS = re.compile(r"^(?:[日夜晨昏][　\s]+)?(?:[内外][　\s]+)?")


async def keyframe_products(session: AsyncSession, shot_ids: Iterable[str]) -> dict[str, Product]:
    rows = await session.exec(
        select(Product).where(
            Product.owner_type == "shot",
            col(Product.owner_id).in_(list(shot_ids)),
            Product.slot == KEYFRAME_SLOT,
        )
    )
    return {p.owner_id: p for p in rows.all()}


async def materialize(session: AsyncSession, product: Product, version: ProductVersion) -> None:
    """Mirror an adopted shot plan: upsert the episode's shots by id, retire the ones it dropped;
    each shot that is not continuous has its keyframe product (retired with the shot, back with
    it)."""
    episode_id = product.owner_id
    rows = {
        r.id: r
        for r in (await session.exec(select(Shot).where(Shot.episode_id == episode_id))).all()
    }
    now = utcnow()
    shots = ops.shots_of(version.payload_json)
    kept: set[str] = set()
    for n, s in enumerate(shots, 1):
        row = rows.get(s["id"]) or Shot(
            id=s["id"],
            series_id=product.series_id,
            episode_id=episode_id,
            scene_id=s["scene_id"],
            version_id=version.id,
            idx=n,
        )
        row.scene_id = s["scene_id"]
        row.version_id = version.id
        row.idx = n
        row.shot_type = s["shot_type"]
        row.framing = s["framing"]
        row.camera_move = s["camera_move"]
        row.duration_s = s.get("duration_s")
        row.manual_s = s.get("manual_s")
        row.intent = str(s.get("intent") or "")
        row.summary = str(s.get("summary") or "")
        row.sound = s.get("sound")
        row.line_ids_json = list(s.get("line_ids") or [])
        row.asset_ids_json = list(s.get("asset_ids") or [])
        row.tail_from = s.get("tail_from")
        row.tail_note = s.get("tail_note")
        row.blocking_json = list(s.get("blocking") or [])
        row.audio_mode = s["audio_mode"]
        row.difficulty = int(s.get("difficulty") or 1)
        row.retired = False
        row.updated_at = now
        session.add(row)
        kept.add(row.id)
    for gone in rows.values():
        if gone.id not in kept and not gone.retired:
            gone.retired = True
            gone.version_id = version.id
            gone.updated_at = now
            session.add(gone)
    existing = await keyframe_products(session, [*rows, *kept])
    wanted = {s["id"] for s in shots if s["shot_type"] != "continuous"}
    for s in shots:
        if s["id"] in wanted and s["id"] not in existing:
            session.add(
                Product(
                    series_id=product.series_id,
                    owner_type="shot",
                    owner_id=s["id"],
                    slot=KEYFRAME_SLOT,
                    component_id=KF_COMPONENT,
                )
            )
    for owner, p in existing.items():
        retired = owner not in wanted
        if p.retired != retired:
            p.retired = retired
            p.updated_at = now
            session.add(p)


async def ensure_plan(session: AsyncSession, product: Product, version: ProductVersion) -> None:
    """An episode with an adopted script has its 分镜规划 product (on the script's adopt)."""
    if await plan_product(session, product.owner_id) is None:
        session.add(
            Product(
                series_id=product.series_id,
                owner_type="episode",
                owner_id=product.owner_id,
                slot=SHOT_PLAN_SLOT,
                component_id=PlanComponent.id,
            )
        )


async def lock_spec(session: AsyncSession, product: Product, version: ProductVersion) -> None:
    """The output spec locks when the series' first keyframe is adopted (SPEC 13.3); later
    ones leave the time as it is."""
    row = await session.get(OutputSpecRow, product.series_id)
    if row is not None and row.locked_at is None:
        row.locked_at = utcnow()
        session.add(row)


async def record_shot_gate(
    session: AsyncSession,
    invalidation: Invalidation,
    series_id: str,
    shot_id: str,
    plan: Product,
    keyframe: Product | None,
    action: str,
    at: datetime | None = None,
) -> None:
    """The shot's own ``gate_decision``: on ``confirm`` the hashes of its settings and of its
    locked keyframe. Written in the caller's transaction (the lock's)."""
    hashes: dict[str, str] = {}
    if action == "confirm":
        if h := await invalidation.current_hash(session, plan.id, shot_slice(shot_id)):
            hashes[plan.id] = h
        if keyframe is not None and (h := await invalidation.current_hash(session, keyframe.id)):
            hashes[keyframe.id] = h
    last = await latest_gate(session, SHOT_GATE, shot_id)
    at = at or utcnow()
    if last is not None and at <= last.decided_at:  # keep them in order
        at = last.decided_at + timedelta(microseconds=1)
    session.add(
        GateDecision(
            series_id=series_id,
            gate=SHOT_GATE,
            scope_id=shot_id,
            action=action,
            product_hashes_json=hashes,
            decided_at=at,
        )
    )


async def shot_decisions(session: AsyncSession, shot_ids: Iterable[str]) -> dict[str, GateDecision]:
    """Each shot's last 确认这个镜头 decision."""
    rows = await session.exec(
        select(GateDecision)
        .where(GateDecision.gate == SHOT_GATE, col(GateDecision.scope_id).in_(list(shot_ids)))
        .order_by(col(GateDecision.decided_at))
    )
    return {d.scope_id: d for d in rows.all()}


async def line_audio_seconds(session: AsyncSession, line_ids: Iterable[str]) -> dict[str, float]:
    """Each dubbed line's audio length (its adopted take)."""
    products = (
        await session.exec(
            select(Product).where(
                Product.owner_type == "line",
                col(Product.owner_id).in_(list(line_ids)),
                Product.slot == LINE_AUDIO_SLOT,
                col(Product.adopted_version_id).is_not(None),
            )
        )
    ).all()
    versions = {
        v.id: v
        for v in (
            await session.exec(
                select(ProductVersion).where(
                    col(ProductVersion.id).in_([p.adopted_version_id for p in products])
                )
            )
        ).all()
    }
    out: dict[str, float] = {}
    for p in products:
        v = versions.get(p.adopted_version_id or "")
        f = next((f for f in v.files_json if f.get("role") == "audio"), None) if v else None
        if f is not None and isinstance(f.get("duration_s"), int | float):
            out[p.owner_id] = float(f["duration_s"])
    return out


def scene_place(heading: str) -> str:
    """「夜　内　林晚出租屋」 → 「林晚出租屋」."""
    return _HEADING_MARKS.sub("", heading.strip()).strip() or heading.strip()


def dialogue_text(lines: Iterable[ScriptLine]) -> str | None:
    rows = []
    for x in lines:
        if x.type not in ops.SPEAKING:
            continue
        who = x.character_name or ""
        rows.append(f"{who}（{x.tone}）：{x.text}" if x.tone else f"{who}：{x.text}")
    return "\n".join(rows) or None


@dataclass(frozen=True)
class ShotState:
    confirmed: bool  # its last decision is a confirm
    stale: bool  # confirmed, but its settings or its keyframe changed since (「待更新」)
    keyframe_stale: bool


def _line(code: str, params: dict[str, Any], cost: float | None = None) -> dict[str, Any]:
    return {"code": code, "params": params, "cost_usd": cost, "optional": False}


def _labels(episode_idx: int, shots: list[dict[str, Any]]) -> dict[str, str]:
    return {s["id"]: f"{episode_idx}-{i:02d}" for i, s in enumerate(shots, 1)}


class ShotService:
    def __init__(
        self,
        db: Database,
        products: ProductService,
        runs: RunService,
        invalidation: Invalidation,
        longest: LongestTake | None = None,
    ) -> None:
        self._db = db
        self._products = products
        self._runs = runs
        self._invalidation = invalidation
        self._longest = longest
        self._gates: GateService | None = None  # set by ``register``

    def register(self, gates: GateService, episodes: EpisodeService, impact: ImpactService) -> None:
        """分镜确认's precondition, the 分镜 badge, and the impact preview's ``shot_edit``,
        ``spec_aspect`` and the shot lines of the script's and the assets' changes."""

        async def shot_edit(target: str, patch: dict[str, Any]) -> PlannedChange:
            return await self.plan_edit(target, ShotEditIn.model_validate(patch))

        async def spec_aspect(target: str, patch: dict[str, Any]) -> PlannedChange:
            return await self.plan_aspect(target, SpecPatch.model_validate(patch))

        gates.precondition(STORYBOARD_GATE, self._all_confirmed)
        episodes.counters["storyboard"] = self.badge
        impact.kind("shot_edit", shot_edit)
        impact.kind("spec_aspect", spec_aspect)
        impact.extra("line_edit", self._line_shots)
        impact.extra("asset_edit", self._asset_shots)
        impact.extra("asset_unlock", self._asset_shots)
        self._gates = gates

    async def states(
        self, session: AsyncSession, plan: Product | None, shots: list[dict[str, Any]]
    ) -> tuple[dict[str, Product], dict[str, ShotState]]:
        """The shots' keyframe products (not retired) and whether each is confirmed and
        「待更新」."""
        ids = [s["id"] for s in shots]
        keyframes = {
            k: p for k, p in (await keyframe_products(session, ids)).items() if not p.retired
        }
        decisions = await shot_decisions(session, ids)
        stale_kf = await self._invalidation.stale_ids(session, keyframes.values())
        out: dict[str, ShotState] = {}
        for shot_id in ids:
            decided = decisions.get(shot_id)
            confirmed = decided is not None and decided.action == "confirm"
            kf = keyframes.get(shot_id)
            kf_stale = kf is not None and kf.id in stale_kf
            changed = False
            if confirmed and decided is not None and plan is not None:
                now = await self._invalidation.current_hash(session, plan.id, shot_slice(shot_id))
                changed = (decided.product_hashes_json or {}).get(plan.id) != now
            out[shot_id] = ShotState(confirmed, confirmed and (changed or kf_stale), kf_stale)
        return keyframes, out

    async def badge(self, session: AsyncSession, episode_id: str) -> StepProgressOut:
        """分镜 n / m: the shots confirmed; 待更新: the plan and the shots changed since."""
        plan = await plan_product(session, episode_id)
        v = await _current(session, plan)
        shots = ops.shots_of(v.payload_json) if v is not None else []
        if plan is None or not shots:
            return StepProgressOut(state="not_started")
        _, states = await self.states(session, plan, shots)
        stale = sum(1 for x in states.values() if x.stale or x.keyframe_stale)
        stale += len(await self._invalidation.stale_ids(session, [plan]))
        confirmed = await gate_confirmed(session, STORYBOARD_GATE, episode_id)
        return StepProgressOut(
            state="confirmed" if confirmed else "in_progress",
            done=sum(1 for x in states.values() if x.confirmed),
            total=len(shots),
            stale=stale,
        )

    async def _all_confirmed(self, session: AsyncSession, episode_id: str) -> None:
        """分镜确认 needs every shot confirmed and none 「待更新」."""
        episode = await session.get(Episode, episode_id)
        plan = await plan_product(session, episode_id)
        v = await _current(session, plan)
        shots = ops.shots_of(v.payload_json) if v is not None else []
        _, states = await self.states(session, plan, shots)
        labels = _labels(episode.idx if episode is not None else 0, shots)
        waiting = [labels[i] for i, x in states.items() if not x.confirmed or x.stale]
        if waiting:
            raise PipelineError(
                409, "shots_not_confirmed", count=len(waiting), labels="、".join(waiting)
            )

    # ------------------------------------------------------------------ reads

    async def of_episode(self, episode_id: str) -> list[ShotOut]:
        async with self._db.session() as session:
            episode = await session.get(Episode, episode_id)
            if episode is None or episode.retired:
                raise PipelineError(404, "episode_not_found", id=episode_id)
            plan = await plan_product(session, episode_id)
            v = await _current(session, plan)
            if v is None:
                return []
            shots = ops.shots_of(v.payload_json)
            lines = await _lines(session, episode_id)
            audio = await line_audio_seconds(
                session, [x.id for x in lines.values() if x.type in ops.SPEAKING]
            )
            numbers = await scene_numbers(session, episode.series_id)
            scenes = {
                s.id: s
                for s in (
                    await session.exec(select(Scene).where(Scene.episode_id == episode_id))
                ).all()
            }
            keyframes, states = await self.states(session, plan, shots)
        longest = await self._longest() if self._longest is not None else None
        labels = _labels(episode.idx, shots)
        out = []
        for i, s in enumerate(shots, 1):
            mine = [lines[x] for x in s.get("line_ids") or [] if x in lines]
            timing = _timing(s, mine, audio, longest)
            kf = keyframes.get(s["id"])
            state = states[s["id"]]
            scene = scenes.get(s["scene_id"])
            seed = str(s.get("intent") or "")
            intent = str(((kf.prompt_json if kf else None) or {}).get("intent") or seed)
            edited_from = ((kf.settings_json if kf else None) or {}).get("seed")
            pick = (kf.pick_json if kf else None) or {}
            out.append(
                ShotOut(
                    id=s["id"],
                    episode_id=episode_id,
                    scene_id=s["scene_id"],
                    label=labels[s["id"]],
                    scene_no=numbers.get(s["scene_id"], scene.idx if scene else 0),
                    scene_place=scene_place(scene.heading) if scene else "",
                    idx=i,
                    summary=str(s.get("summary") or ""),
                    intent=intent,
                    seed_changed=edited_from is not None and edited_from != seed,
                    shot_type=s["shot_type"],
                    framing=s["framing"],
                    camera_move=s["camera_move"],
                    duration_s=timing.seconds,
                    duration_source=timing.source,
                    min_s=timing.min_s,
                    planned_s=s.get("duration_s"),
                    manual_s=s.get("manual_s"),
                    longest_s=longest,
                    split_hint=timing.split,
                    line_ids=list(s.get("line_ids") or []),
                    dialogue=dialogue_text(mine),
                    sound=s.get("sound"),
                    audio_mode=s["audio_mode"],
                    asset_ids=list(s.get("asset_ids") or []),
                    tail_from=labels.get(s.get("tail_from") or ""),
                    tail_note=s.get("tail_note"),
                    blocking=s.get("blocking") or [],
                    keyframe_product_id=kf.id if kf else None,
                    video_product_id=None,
                    keyframe_pick=int(pick.get("idx") or 0)
                    if kf is not None and pick.get("version_id") == kf.current_version_id
                    else 0,
                    confirmed=state.confirmed,
                    confirm_stale=state.stale,
                )
            )
        return out

    async def get(self, shot_id: str) -> ShotOut:
        episode_id = await self._episode_of_shot(shot_id)
        shot = next((s for s in await self.of_episode(episode_id) if s.id == shot_id), None)
        if shot is None:
            raise PipelineError(404, "shot_not_found", id=shot_id)
        return shot

    # ------------------------------------------------------------------ edits

    async def patch(self, shot_id: str, body: ShotPatch) -> ShotOut:
        """改镜头设定. The plan's fields append an ``edit`` version; the picture description and
        the picked candidate are the keyframe product's."""
        fields = body.model_fields_set
        if body.confirmed is False:
            await self._unconfirm(shot_id)
        elif fields - {"confirmed"} and await self._confirmed(shot_id):
            raise PipelineError(409, "shot_confirmed", id=shot_id)
        changes = _changes(body)
        p, v = await self._locate(shot_id, editable=bool(changes))
        if changes:
            payload = await self._edited(p, v, shot_id, changes)
            await self._products.append_edit(p.id, v, payload)
        if body.intent is not None or body.keyframe_pick is not None:
            kf = await self._keyframe(shot_id)
            if body.intent is not None:
                await self._set_intent(kf, v, shot_id, body.intent)
            if body.keyframe_pick is not None:
                if kf.current_version_id is None:
                    raise PipelineError(409, "nothing_to_pick", id=shot_id)
                await self._products.set_pick(kf.id, kf.current_version_id, body.keyframe_pick)
        if body.confirmed:
            await self._confirm(shot_id)
        return await self.get(shot_id)

    async def split(self, shot_id: str, body: ShotSplitIn) -> list[ShotOut]:
        """拆分 (``ops.split``): one more shot after this one. A confirmed shot is split through
        the impact preview (``shot_edit``)."""
        if await self._confirmed(shot_id):
            raise PipelineError(409, "shot_confirmed", id=shot_id)
        p, v = await self._locate(shot_id)
        async with self._db.session() as session:
            lines = await _lines(session, p.owner_id)
        types = {x.id: x.type for x in lines.values()}
        payload, _ = _apply(lambda: ops.split(v.payload_json, shot_id, types, body.after_line_id))
        await self._products.append_edit(p.id, v, payload)
        return await self.of_episode(p.owner_id)

    async def merge(self, shot_id: str) -> list[ShotOut]:
        """和下一个合并 (``ops.merge``); confirmed ones go through the impact preview."""
        p, v = await self._locate(shot_id)
        for x in (shot_id, _next_in_scene(v.payload_json, shot_id)):
            if x is not None and await self._confirmed(x):
                raise PipelineError(409, "shot_confirmed", id=x)
        async with self._db.session() as session:
            lines = await _lines(session, p.owner_id)
        order = {line_id: n for n, line_id in enumerate(lines)}
        payload, _ = _apply(lambda: ops.merge(v.payload_json, shot_id, order))
        await self._products.append_edit(p.id, v, payload)
        return await self.of_episode(p.owner_id)

    # ------------------------------------------------------------------ the impact preview

    async def plan_edit(self, shot_id: str, body: ShotEditIn) -> PlannedChange:
        """``shot_edit``: change a confirmed shot (or one of a confirmed storyboard), split it
        or merge it with the next one. Lines: the shots whose confirmation it takes back, a new
        picture description's redraw, 分镜确认 reopened; the keyframes it makes 待更新 come from
        the plan's slices. 「确认并同步」 also draws the touched shots' keyframes again."""
        if body.confirmed is not None or body.keyframe_pick is not None:
            raise PipelineError(422, "invalid_patch", kind="shot_edit", issues="confirmed")
        p, v = await self._locate(shot_id, editable=False, locked_ok=True)
        payload: dict[str, Any] | None = None
        touched = [shot_id]
        async with self._db.session() as session:
            lines = await _lines(session, p.owner_id)
            episode = await session.get(Episode, p.owner_id)
            gate_on = await gate_confirmed(session, STORYBOARD_GATE, p.owner_id)
        if body.split is not None:
            types = {x.id: x.type for x in lines.values()}
            after = body.split.after_line_id
            payload, _ = _apply(lambda: ops.split(v.payload_json, shot_id, types, after))
        elif body.merge:
            order = {line_id: n for n, line_id in enumerate(lines)}
            payload, _ = _apply(lambda: ops.merge(v.payload_json, shot_id, order))
            nxt = _next_in_scene(v.payload_json, shot_id)
            touched += [nxt] if nxt else []
        elif changes := _changes(body):
            payload = await self._edited(p, v, shot_id, changes)
        if payload == v.payload_json:
            payload = None
        labels = _labels(episode.idx if episode is not None else 0, ops.shots_of(v.payload_json))
        confirmed = [x for x in touched if await self._confirmed(x)]
        kf = None if body.intent is None else await self._keyframe(shot_id)
        planned_lines: list[dict[str, Any]] = []
        if confirmed:
            shots = "、".join(labels[x] for x in confirmed)
            planned_lines.append(_line("shot_reconfirm", {"shots": shots, "count": len(confirmed)}))
        if kf is not None:
            planned_lines.append(_line("shot_redraw", {"shot": labels[shot_id]}))
        if gate_on:
            planned_lines.append(_line("gate_storyboard", {"n": episode.idx if episode else 0}))

        async def commit() -> None:
            if gate_on and self._gates is not None:
                await self._gates.reopen(STORYBOARD_GATE, p.owner_id)
            for x in confirmed:
                await self._unconfirm(x, reopen_gate=False)
            if payload is not None:
                await self._products.append_edit(p.id, v, payload)
            if kf is not None and body.intent is not None:
                await self._set_intent(kf, v, shot_id, body.intent)

        async def redraw() -> list[str]:
            async with self._db.session() as session:
                now = await _current(session, await plan_product(session, p.owner_id))
                shots = ops.shots_of(now.payload_json if now is not None else None)
                ids = [s["id"] for s in shots]
                again = set(touched)
                if body.split is not None and shot_id in ids and ids.index(shot_id) + 1 < len(ids):
                    again.add(ids[ids.index(shot_id) + 1])
                keyframes = await keyframe_products(session, again)
            return await self._redraw([k for k in keyframes.values() if not k.retired])

        return PlannedChange(
            product_id=p.id,
            series_id=p.series_id,
            base_version_id=v.id,
            commit=commit,
            payload=payload,
            content=body.model_dump(mode="json", exclude_unset=True),
            lines=planned_lines,
            relock=False,
            rerun=redraw,
        )

    async def plan_aspect(self, series_id: str, body: SpecPatch) -> PlannedChange:
        """``spec_aspect`` (改画幅, SPEC 13.3): the keyframes drawn so far (their API finals'
        price) and the scenes' reference pictures drawn for the old aspect (a hint). 「只改这里」
        writes the spec and takes the confirmations back (分镜确认 reopens); 「确认并同步」 also
        draws the keyframes again as local drafts."""
        async with self._db.session() as session:
            row = await session.get(OutputSpecRow, series_id)
            if row is None:
                raise PipelineError(404, "series_not_found", id=series_id)
            old = row.aspect
            keyframes = [
                k
                for k in (
                    await session.exec(
                        select(Product).where(
                            Product.series_id == series_id,
                            Product.owner_type == "shot",
                            Product.slot == KEYFRAME_SLOT,
                            col(Product.retired).is_(False),
                            col(Product.current_version_id).is_not(None),
                        )
                    )
                ).all()
            ]
            shots = list(
                (
                    await session.exec(
                        select(Shot).where(
                            Shot.series_id == series_id, col(Shot.retired).is_(False)
                        )
                    )
                ).all()
            )
            scenes = await _scene_refs_drawn_for(session, series_id, old)
        new = body.aspect or old
        changed = new != old
        lines: list[dict[str, Any]] = []
        if changed and keyframes:
            costs = [c for k in keyframes if (c := await self._runs.final_cost(k))]
            lines.append(
                _line(
                    "keyframes_redraw",
                    {"count": len(keyframes), "shots": len(shots)},
                    round(sum(costs), 4) if costs else None,
                )
            )
        if changed and scenes:
            lines.append(
                {**_line("ref_images_suggest", {"count": scenes, "aspect": old}), "optional": True}
            )

        async def commit() -> None:
            async with self._db.session() as session:
                spec = await session.get(OutputSpecRow, series_id)
                assert spec is not None
                apply_patch(spec, body)
                session.add(spec)
                await session.commit()
                confirmed = (
                    [s.id for s in shots if await gate_confirmed(session, SHOT_GATE, s.id)]
                    if changed
                    else []
                )
            for shot_id in confirmed:
                await self._unconfirm(shot_id)

        async def redraw() -> list[str]:
            return await self._redraw(keyframes) if changed else []

        return PlannedChange(
            product_id=f"spec:{series_id}",
            series_id=series_id,
            base_version_id=None,
            commit=commit,
            content={"from": old, **body.model_dump(mode="json", exclude_unset=True)},
            lines=lines,
            unaffected={"code": "unaffected_spec", "params": {}},
            relock=False,
            rerun=redraw,
            stale={"storyboard": len(keyframes)} if changed and keyframes else {},
        )

    async def _line_shots(self, line_id: str, patch: dict[str, Any]) -> list[dict[str, Any]]:
        """``line_edit`` of a spoken line: the shots it is in run as long as its new audio."""
        async with self._db.session() as session:
            line = await session.get(ScriptLine, line_id)
            if (
                line is None
                or line.type not in ops.SPEAKING
                or patch.get("text") in (None, line.text)
            ):
                return []
            labels = await _shot_labels(
                session, line.episode_id, lambda s: line_id in s.line_ids_json
            )
        if not labels:
            return []
        return [_line("shot_duration_follows", {"shots": "、".join(labels), "count": len(labels)})]

    async def _asset_shots(self, asset_id: str, patch: dict[str, Any]) -> list[dict[str, Any]]:
        """Changing or unlocking a locked asset: the shots that use it, and which of those with
        a keyframe were confirmed (a new picture makes them 「待更新」)."""
        async with self._db.session() as session:
            asset = await session.get(Asset, asset_id)
            if asset is None or asset.kind not in ops.REF_KINDS:
                return []
            using = [
                s
                for s in (
                    await session.exec(
                        select(Shot).where(
                            Shot.series_id == asset.series_id, col(Shot.retired).is_(False)
                        )
                    )
                ).all()
                if asset_id in s.asset_ids_json
            ]
            episodes = {
                e.id: e.idx
                for e in (
                    await session.exec(select(Episode).where(Episode.series_id == asset.series_id))
                ).all()
            }
            using.sort(key=lambda s: (episodes.get(s.episode_id, 0), s.idx))
            label = {s.id: f"{episodes.get(s.episode_id, 0)}-{s.idx:02d}" for s in using}
            drawn = [
                s.id
                for s in using
                if s.shot_type != "continuous" and await gate_confirmed(session, SHOT_GATE, s.id)
            ]
        if not using:
            return []
        out = [
            _line("shot_refs", {"ids": "、".join(label[s.id] for s in using), "count": len(using)})
        ]
        if drawn:
            shots = "、".join(label[x] for x in drawn)
            out.append(_line("shots_confirmed_redraw", {"shots": shots, "count": len(drawn)}))
        return out

    async def _redraw(self, keyframes: Iterable[Product]) -> list[str]:
        """「确认并同步」: new candidates of these keyframes (a busy one is left as it is)."""
        jobs = []
        for k in keyframes:
            try:
                jobs.append((await self._runs.start(k.id, "rerun")).id)
            except PipelineError as exc:
                logger.warning("keyframe {} not redrawn: {}", k.id, exc.code)
        return jobs

    # ------------------------------------------------------------------ confirming

    async def _confirmed(self, shot_id: str) -> bool:
        async with self._db.session() as session:
            last = await latest_gate(session, SHOT_GATE, shot_id)
        return last is not None and last.action == "confirm"

    async def _confirm(self, shot_id: str) -> None:
        """「确认这个镜头」: lock the picked keyframe with the shot's decision. A keyframe locked
        already (a 「待更新」 shot confirmed again) or a continuous shot only gets the decision."""
        p, v = await self._locate(shot_id, editable=False)
        shot = ops.find_shot(v.payload_json, shot_id)
        assert shot is not None
        if shot["shot_type"] == "continuous":
            tail = shot.get("tail_from")
            if not tail or ops.find_shot(v.payload_json, tail) is None:
                raise PipelineError(409, "no_tail_shot", id=shot_id)
            await self._decide(shot_id, p, None, "confirm")
            return
        kf = await self._keyframe(shot_id)
        if kf.current_version_id is None:
            raise PipelineError(409, "nothing_to_confirm", id=shot_id)
        if kf.locked_hash:
            await self._decide(shot_id, p, kf, "confirm")
            return
        async with self._db.session() as session:
            current = await session.get(ProductVersion, kf.current_version_id)
        assert current is not None
        candidates = [f for f in current.files_json if f.get("role") == "candidate"]
        pick = kf.pick_json or {}
        idx: int | None = int(pick.get("idx") or 0) if pick.get("version_id") == current.id else 0
        if len(candidates) <= 1:
            idx = None  # an API final's lone picture (or an upload) is locked as it is

        async def record(session: AsyncSession, keyframe: Product, _: ProductVersion) -> None:
            await record_shot_gate(
                session, self._invalidation, p.series_id, shot_id, p, keyframe, "confirm"
            )

        await self._products.lock_pick(kf.id, current.id, idx, record=record)

    async def _unconfirm(self, shot_id: str, *, reopen_gate: bool = True) -> None:
        """取消确认: unlock the keyframe and write ``reopen`` (nothing when not confirmed); a
        confirmed 分镜确认 of its episode reopens with it."""
        if not await self._confirmed(shot_id):
            return
        p, _ = await self._locate(shot_id, editable=False)
        async with self._db.session() as session:
            kf = (await keyframe_products(session, [shot_id])).get(shot_id)
            gate_on = await gate_confirmed(session, STORYBOARD_GATE, p.owner_id)
        if kf is not None and kf.locked_hash:
            await self._products.unlock(kf.id)
        await self._decide(shot_id, p, None, "reopen")
        if reopen_gate and gate_on and self._gates is not None:
            await self._gates.reopen(STORYBOARD_GATE, p.owner_id)

    async def _decide(self, shot_id: str, plan: Product, kf: Product | None, action: str) -> None:
        async with self._db.session() as session:
            await record_shot_gate(
                session, self._invalidation, plan.series_id, shot_id, plan, kf, action
            )
            await session.commit()

    # ------------------------------------------------------------------ internals

    async def _edited(
        self, p: Product, v: ProductVersion, shot_id: str, changes: dict[str, Any]
    ) -> dict[str, Any]:
        """The plan's payload with a shot's settings changed (checked: its references are the
        episode's, it is not shorter than its lines' audio)."""
        async with self._db.session() as session:
            assets, _ = await episode_assets(session, p.owner_id)
            lines = await _lines(session, p.owner_id)
            shot = ops.find_shot(v.payload_json, shot_id)
            assert shot is not None
            audio = await line_audio_seconds(session, shot.get("line_ids") or [])
        unknown = [a for a in changes.get("asset_ids", []) if a not in assets]
        if unknown:
            raise PipelineError(422, "asset_not_found", id=unknown[0])
        manual = changes.get("manual_s")
        if manual is not None:
            mine = [lines[x] for x in shot.get("line_ids") or [] if x in lines]
            floor = _timing(shot, mine, audio, None).min_s
            if manual < floor:
                raise PipelineError(422, "duration_below_audio", min_s=floor)
        characters = [a.id for a in assets.values() if a.kind == "character"]
        payload: dict[str, Any] = _apply(
            lambda: ops.patch(v.payload_json, shot_id, changes, characters)
        )
        return payload

    async def _set_intent(self, kf: Product, v: ProductVersion, shot_id: str, intent: str) -> None:
        """The picture description is the keyframe prompt's intent layer; the plan's seed is
        kept to say when a rerun gives a new one."""
        seed = str((ops.find_shot(v.payload_json, shot_id) or {}).get("intent") or "")
        await self._runs.save_prompt(kf.id, intent, None)
        await self._products.update_settings(kf.id, {"seed": seed})

    async def _episode_of_shot(self, shot_id: str) -> str:
        p, _ = await self._locate(shot_id, editable=False)
        return p.owner_id

    async def _locate(
        self, shot_id: str, *, editable: bool = True, locked_ok: bool = False
    ) -> tuple[Product, ProductVersion]:
        """The plan whose version on screen has this shot; an edit refuses a busy or locked
        plan (a locked one goes through the impact preview, ``locked_ok``)."""
        async with self._db.session() as session:
            row = await session.get(Shot, shot_id)
            if row is not None:
                plans = [p] if (p := await plan_product(session, row.episode_id)) else []
            else:
                query = select(Product).where(Product.slot == SHOT_PLAN_SLOT)
                plans = list((await session.exec(query.order_by(col(Product.created_at)))).all())
            for p in plans:
                v = await _current(session, p)
                if v is None or ops.find_shot(v.payload_json, shot_id) is None:
                    continue
                if (editable or locked_ok) and p.running_job_id:
                    job = await session.get(Job, p.running_job_id)
                    if job is not None and job.state in ACTIVE_JOB_STATES:
                        raise PipelineError(409, "product_busy", id=p.id)
                if editable and p.locked_hash:
                    raise PipelineError(409, "product_locked", id=p.id)
                return p, v
        raise PipelineError(404, "shot_not_found", id=shot_id)

    async def _keyframe(self, shot_id: str) -> Product:
        async with self._db.session() as session:
            kf = (await keyframe_products(session, [shot_id])).get(shot_id)
        if kf is None or kf.retired:
            raise PipelineError(409, "no_keyframe", id=shot_id)
        return kf


def _changes(body: ShotPatch) -> dict[str, Any]:
    """The plan's fields a patch sets (``duration_s`` is the user's seconds; null = automatic)."""
    fields = body.model_fields_set
    changes: dict[str, Any] = {
        k: getattr(body, k)
        for k in ("shot_type", "framing", "camera_move", "audio_mode")
        if k in fields and getattr(body, k) is not None
    }
    if "blocking" in fields and body.blocking is not None:
        changes["blocking"] = [b.model_dump() for b in body.blocking]
    if "asset_ids" in fields and body.asset_ids is not None:
        changes["asset_ids"] = list(dict.fromkeys(body.asset_ids))
    if "duration_s" in fields:
        changes["manual_s"] = body.duration_s
    return changes


def _next_in_scene(payload: dict[str, Any], shot_id: str) -> str | None:
    shots = ops.shots_of(payload)
    at = next((i for i, s in enumerate(shots) if s["id"] == shot_id), None)
    if at is None or at + 1 >= len(shots) or shots[at + 1]["scene_id"] != shots[at]["scene_id"]:
        return None
    return str(shots[at + 1]["id"])


async def _shot_labels(
    session: AsyncSession, episode_id: str, wanted: Callable[[Shot], bool]
) -> list[str]:
    episode = await session.get(Episode, episode_id)
    rows = (
        await session.exec(
            select(Shot).where(Shot.episode_id == episode_id, col(Shot.retired).is_(False))
        )
    ).all()
    n = episode.idx if episode is not None else 0
    return [f"{n}-{s.idx:02d}" for s in sorted(rows, key=lambda s: s.idx) if wanted(s)]


async def _scene_refs_drawn_for(session: AsyncSession, series_id: str, aspect: str) -> int:
    """How many locked scene reference pictures were drawn for ``aspect``."""
    rows = await session.exec(
        select(Asset, Product).where(
            Asset.series_id == series_id,
            Asset.kind == "scene",
            col(Asset.retired).is_(False),
            Product.owner_type == "asset",
            Product.owner_id == Asset.id,
            col(Product.locked_hash).is_not(None),
        )
    )
    n = 0
    for _, product in rows.all():
        v = await session.get(ProductVersion, product.adopted_version_id or "")
        while v is not None and "aspect" not in (v.payload_json or {}) and v.parent_version_id:
            v = await session.get(ProductVersion, v.parent_version_id)
        if v is not None and (v.payload_json or {}).get("aspect") == aspect:
            n += 1
    return n


async def _current(session: AsyncSession, p: Product | None) -> ProductVersion | None:
    if p is None or p.current_version_id is None:
        return None
    return await session.get(ProductVersion, p.current_version_id)


async def _lines(session: AsyncSession, episode_id: str) -> dict[str, ScriptLine]:
    """The episode's lines in script order."""
    scenes = {
        s.id: s.idx
        for s in (await session.exec(select(Scene).where(Scene.episode_id == episode_id))).all()
    }
    rows = (
        await session.exec(
            select(ScriptLine).where(
                ScriptLine.episode_id == episode_id, col(ScriptLine.retired).is_(False)
            )
        )
    ).all()
    ordered = sorted(rows, key=lambda x: (scenes.get(x.scene_id, 0), x.idx))
    return {x.id: x for x in ordered}


def _timing(
    shot: dict[str, Any],
    lines: Iterable[ScriptLine],
    audio: dict[str, float],
    longest: float | None,
) -> ShotDuration:
    dialogue: list[float] = []
    voiceover: list[float] = []
    for x in lines:
        if x.type not in ops.SPEAKING:
            continue
        seconds = line_seconds(x.text, x.duration_s, audio.get(x.id))
        (dialogue if x.type == "dialogue" else voiceover).append(seconds)
    return shot_duration(dialogue, voiceover, shot.get("duration_s"), shot.get("manual_s"), longest)


def _apply(fn: Callable[[], Any]) -> Any:
    try:
        return fn()
    except ops.ShotEditError as exc:
        status = 404 if exc.code.endswith("_not_found") else 422
        raise PipelineError(status, exc.code, **exc.params) from exc
