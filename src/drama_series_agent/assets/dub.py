"""台词配音 of an episode (M3): ``GET / POST /episodes/{id}/dub``, ``PATCH /lines/{id}/dub``.

``status`` lists the episode's spoken lines in script order: who speaks, the adopted audio, the
emotion, whether it is current, and each scene's length from it (``pipeline/timing.py``).
``dub`` is 「全部配音」: the total estimate first (``dry_run``), then one ``product.run`` per
line without current audio whose voice is locked. A line's emotion can be set by hand; it is a
setting of the line's product, used from the next take on.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import col, select

from drama_series_agent.assets.service import _scene_numbers
from drama_series_agent.core.config import get_config
from drama_series_agent.core.db import Database
from drama_series_agent.core.models_db import Episode, Product, ProductVersion, Scene, ScriptLine
from drama_series_agent.pipeline.components.dub import (
    LINE_AUDIO_SLOT,
    SPEAKING,
    DubComponent,
    pick_voice,
    series_voices,
)
from drama_series_agent.pipeline.errors import PipelineError
from drama_series_agent.pipeline.invalidation import Invalidation
from drama_series_agent.pipeline.products import ProductService
from drama_series_agent.pipeline.runs import RunService
from drama_series_agent.pipeline.schema import VersionFileOut
from drama_series_agent.pipeline.timing import line_seconds, scene_seconds

DubStatus = Literal["done", "stale", "missing", "running", "failed", "no_voice", "voice_not_locked"]
TO_DUB = ("missing", "stale", "failed")


class DubLineOut(BaseModel):
    line_id: str
    scene_id: str
    idx: int
    text: str
    tone: str
    speaker: str  # the character's name as the script writes it
    voice_asset_id: str | None
    voice_name: str | None
    product_id: str | None
    status: DubStatus
    emotion: str
    emotion_set: bool  # chosen by hand (else from the tone)
    tone_emotion: str  # what the tone calls for (config/voice.yaml tones)
    audio: VersionFileOut | None
    seconds: float  # the audio's length, else the script's estimate


class DubSceneOut(BaseModel):
    scene_id: str
    number: int  # series-wide 场号
    seconds: float  # its spoken lines one after another
    dubbed: int
    lines: int


class DubOut(BaseModel):
    episode_id: str
    lines: list[DubLineOut]
    scenes: list[DubSceneOut]
    done: int
    total: int


class DubIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dry_run: bool = False
    # 「配音 / 重配」 of these lines, whatever their state; None: every line without current audio.
    line_ids: list[str] | None = Field(default=None, max_length=500)


class DubSkipOut(BaseModel):
    line_id: str
    code: Literal["no_voice", "voice_not_locked", "product_busy"]
    name: str


class DubStartOut(BaseModel):
    estimate_usd: float
    lines: int
    jobs: list[str]
    skipped: list[DubSkipOut]


class LineDubPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    emotion: str | None = Field(default=None, max_length=32)  # None: from the tone again


class DubService:
    def __init__(
        self,
        db: Database,
        products: ProductService,
        runs: RunService,
        invalidation: Invalidation,
        component: DubComponent,
    ) -> None:
        self._db = db
        self._products = products
        self._runs = runs
        self._invalidation = invalidation
        self._component = component

    async def status(self, episode_id: str) -> DubOut:
        async with self._db.session() as session:
            episode = await session.get(Episode, episode_id)
            if episode is None:
                raise PipelineError(404, "episode_not_found", id=episode_id)
            scenes = list(
                (
                    await session.exec(
                        select(Scene)
                        .where(Scene.episode_id == episode_id, col(Scene.retired).is_(False))
                        .order_by(col(Scene.idx))
                    )
                ).all()
            )
            order = {s.id: s.idx for s in scenes}
            lines = [
                x
                for x in (
                    await session.exec(
                        select(ScriptLine).where(
                            ScriptLine.episode_id == episode_id,
                            col(ScriptLine.retired).is_(False),
                            col(ScriptLine.type).in_(SPEAKING),
                        )
                    )
                ).all()
                if x.scene_id in order
            ]
            lines.sort(key=lambda x: (order[x.scene_id], x.idx))
            products = {
                p.owner_id: p
                for p in (
                    await session.exec(
                        select(Product).where(
                            Product.owner_type == "line",
                            col(Product.owner_id).in_([x.id for x in lines]),
                            Product.slot == LINE_AUDIO_SLOT,
                        )
                    )
                ).all()
            }
            adopted = {
                v.id: v
                for v in (
                    await session.exec(
                        select(ProductVersion).where(
                            col(ProductVersion.id).in_(
                                [p.adopted_version_id for p in products.values()]
                            )
                        )
                    )
                ).all()
            }
            stale = await self._invalidation.stale_ids(session, list(products.values()))
            voices, uses, voice_products = await series_voices(session, episode.series_id)
            numbers = await _scene_numbers(session, episode.series_id)
        cfg = get_config().voice
        out: list[DubLineOut] = []
        for x in lines:
            p = products.get(x.id)
            voice = pick_voice(x, voices, uses)
            vp = voice_products.get(voice.id) if voice is not None else None
            v = adopted.get(p.adopted_version_id or "") if p is not None else None
            f = next((f for f in v.files_json if f.get("role") == "audio"), None) if v else None
            audio = VersionFileOut.model_validate(f) if f else None
            chosen = ((p.settings_json if p else None) or {}).get("emotion")
            status: DubStatus
            if p is not None and p.running_job_id:
                status = "running"
            elif audio is not None:
                status = "stale" if p is not None and p.id in stale else "done"
            elif voice is None or vp is None:
                status = "no_voice"
            elif not vp.locked_hash:
                status = "voice_not_locked"
            elif p is not None and p.status == "failed":
                status = "failed"
            else:
                status = "missing"
            out.append(
                DubLineOut(
                    line_id=x.id,
                    scene_id=x.scene_id,
                    idx=x.idx,
                    text=x.text,
                    tone=x.tone or "",
                    speaker=x.character_name or "",
                    voice_asset_id=voice.id if voice else None,
                    voice_name=voice.name if voice else None,
                    product_id=p.id if p else None,
                    status=status,
                    emotion=chosen or cfg.emotion_of(x.tone),
                    emotion_set=bool(chosen),
                    tone_emotion=cfg.emotion_of(x.tone),
                    audio=audio,
                    seconds=line_seconds(x.text, x.duration_s, audio.duration_s if audio else None),
                )
            )
        return DubOut(
            episode_id=episode_id,
            lines=out,
            scenes=[
                DubSceneOut(
                    scene_id=s.id,
                    number=numbers.get(s.id, s.idx),
                    seconds=scene_seconds(x.seconds for x in out if x.scene_id == s.id),
                    dubbed=sum(1 for x in out if x.scene_id == s.id and x.audio is not None),
                    lines=sum(1 for x in out if x.scene_id == s.id),
                )
                for s in scenes
            ],
            done=sum(1 for x in out if x.status == "done"),
            total=len(out),
        )

    async def dub(self, episode_id: str, body: DubIn) -> DubStartOut:
        """「全部配音」: every line without current audio whose voice is locked; with
        ``line_ids``, those lines again (「重配」) as long as their voice is locked."""
        now = await self.status(episode_id)
        lines = now.lines
        if body.line_ids is not None:
            wanted = set(body.line_ids)
            known = {x.line_id for x in lines}
            missing = [i for i in body.line_ids if i not in known]
            if missing:
                raise PipelineError(404, "line_not_found", id=missing[0])
            lines = [x for x in lines if x.line_id in wanted]
        skipped = [
            DubSkipOut(line_id=x.line_id, code=x.status, name=x.voice_name or x.speaker)
            for x in lines
            if x.status in ("no_voice", "voice_not_locked")
        ]
        skipped += [
            DubSkipOut(line_id=x.line_id, code="product_busy", name="")
            for x in lines
            if x.status == "running"
        ]
        redo = TO_DUB if body.line_ids is None else (*TO_DUB, "done")
        todo = [x for x in lines if x.status in redo]
        products = [await self._ensure(episode_id, x.line_id) for x in todo]
        total = 0.0
        for p in products:
            _, est = await self._runs.describe(p)
            total += est.cost_usd if est is not None else 0.0
        jobs: list[str] = []
        if not body.dry_run:
            for x, p in zip(todo, products, strict=True):
                try:
                    jobs.append((await self._runs.start(p.id, "run")).id)
                except PipelineError as exc:
                    if exc.code != "product_busy":
                        raise
                    skipped.append(DubSkipOut(line_id=x.line_id, code="product_busy", name=""))
        return DubStartOut(
            estimate_usd=round(total, 6), lines=len(todo), jobs=jobs, skipped=skipped
        )

    async def set_emotion(self, line_id: str, body: LineDubPatch) -> DubLineOut:
        known = {e.id for e in get_config().voice.emotions}
        if body.emotion is not None and body.emotion not in known:
            raise PipelineError(422, "unknown_emotion", emotion=body.emotion)
        async with self._db.session() as session:
            line = await session.get(ScriptLine, line_id)
        if line is None or line.retired or line.type not in SPEAKING:
            raise PipelineError(404, "line_not_found", id=line_id)
        p = await self._ensure(line.episode_id, line_id)
        await self._products.update_settings(p.id, {"emotion": body.emotion})
        now = await self.status(line.episode_id)
        return next(x for x in now.lines if x.line_id == line_id)

    async def _ensure(self, episode_id: str, line_id: str) -> Product:
        async with self._db.session() as session:
            episode = await session.get(Episode, episode_id)
        assert episode is not None
        return await self._products.ensure(
            series_id=episode.series_id,
            owner_type="line",
            owner_id=line_id,
            slot=LINE_AUDIO_SLOT,
            component_id=self._component.id,
        )
