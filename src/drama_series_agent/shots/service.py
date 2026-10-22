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
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Iterable
from typing import Any

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from drama_series_agent.core.db import Database
from drama_series_agent.core.models_db import (
    Episode,
    Job,
    Product,
    ProductVersion,
    Scene,
    ScriptLine,
    Shot,
    utcnow,
)
from drama_series_agent.episodes.service import scene_numbers
from drama_series_agent.pipeline.components.dub import LINE_AUDIO_SLOT
from drama_series_agent.pipeline.components.plan import (
    SHOT_PLAN_SLOT,
    PlanComponent,
    episode_assets,
    plan_product,
)
from drama_series_agent.pipeline.errors import PipelineError
from drama_series_agent.pipeline.products import ACTIVE_JOB_STATES, ProductService
from drama_series_agent.pipeline.runs import RunService
from drama_series_agent.pipeline.timing import ShotDuration, line_seconds, shot_duration
from drama_series_agent.shots import ops
from drama_series_agent.shots.schema import ShotOut, ShotPatch, ShotSplitIn

KEYFRAME_SLOT = "keyframe"
KF_COMPONENT = "kf"
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


class ShotService:
    def __init__(
        self,
        db: Database,
        products: ProductService,
        runs: RunService,
        longest: LongestTake | None = None,
    ) -> None:
        self._db = db
        self._products = products
        self._runs = runs
        self._longest = longest

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
            keyframes = await keyframe_products(session, [s["id"] for s in shots])
        longest = await self._longest() if self._longest is not None else None
        labels = {s["id"]: f"{episode.idx}-{i:02d}" for i, s in enumerate(shots, 1)}
        out = []
        for i, s in enumerate(shots, 1):
            mine = [lines[x] for x in s.get("line_ids") or [] if x in lines]
            timing = _timing(s, mine, audio, longest)
            kf = keyframes.get(s["id"])
            kf = kf if kf is not None and not kf.retired else None
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
                    confirmed=False,
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
        if body.confirmed is not None:
            raise PipelineError(409, "component_not_ready", id=KF_COMPONENT)
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
        p, v = await self._locate(shot_id, editable=bool(changes))
        if changes:
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
            payload = _apply(lambda: ops.patch(v.payload_json, shot_id, changes, characters))
            await self._products.append_edit(p.id, v, payload)
        if body.intent is not None or body.keyframe_pick is not None:
            kf = await self._keyframe(shot_id)
            if body.intent is not None:
                seed = str((ops.find_shot(v.payload_json, shot_id) or {}).get("intent") or "")
                await self._runs.save_prompt(kf.id, body.intent, None)
                await self._products.update_settings(kf.id, {"seed": seed})
            if body.keyframe_pick is not None:
                if kf.current_version_id is None:
                    raise PipelineError(409, "nothing_to_pick", id=shot_id)
                await self._products.set_pick(kf.id, kf.current_version_id, body.keyframe_pick)
        return await self.get(shot_id)

    async def split(self, shot_id: str, body: ShotSplitIn) -> list[ShotOut]:
        """拆分 (``ops.split``): one more shot after this one."""
        p, v = await self._locate(shot_id)
        async with self._db.session() as session:
            lines = await _lines(session, p.owner_id)
        types = {x.id: x.type for x in lines.values()}
        payload, _ = _apply(lambda: ops.split(v.payload_json, shot_id, types, body.after_line_id))
        await self._products.append_edit(p.id, v, payload)
        return await self.of_episode(p.owner_id)

    async def merge(self, shot_id: str) -> list[ShotOut]:
        """和下一个合并 (``ops.merge``)."""
        p, v = await self._locate(shot_id)
        async with self._db.session() as session:
            lines = await _lines(session, p.owner_id)
        order = {line_id: n for n, line_id in enumerate(lines)}
        payload, _ = _apply(lambda: ops.merge(v.payload_json, shot_id, order))
        await self._products.append_edit(p.id, v, payload)
        return await self.of_episode(p.owner_id)

    # ------------------------------------------------------------------ internals

    async def _episode_of_shot(self, shot_id: str) -> str:
        p, _ = await self._locate(shot_id, editable=False)
        return p.owner_id

    async def _locate(
        self, shot_id: str, *, editable: bool = True
    ) -> tuple[Product, ProductVersion]:
        """The plan whose version on screen has this shot; an edit refuses a busy or locked
        plan (a locked one goes through the impact preview)."""
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
                if editable and p.running_job_id:
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
