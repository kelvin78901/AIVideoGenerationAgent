"""Reading and editing an episode's script (SPEC 9.1 ``/episodes/{id}/script``, ``/lines/…``,
``/scenes/…``).

Each episode's script is its ``script`` product (component ``script``, owner the episode).
Reads show the product's current version through one pure view (``ops.view``), adopted or not,
with scenes numbered across the series (``episodes.service.scene_counts``). The user's edits
append an ``edit`` version made from the current one and adopt it (M2 plan 设计要点); it keeps
the dependencies of the version it was made from, so it turns stale with it. A confirmed
script is locked, and editing it goes through the impact preview (M2 plan step 10).
「重写这一段」 only proposes a text (``ScriptComponent.rewrite``); keeping it is an edit.
``scene`` and ``script_line`` mirror the adopted version (``materialize``).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from drama_series_agent.bible.schema import SourceSpanOut
from drama_series_agent.core.db import Database
from drama_series_agent.core.models_db import (
    Episode,
    Job,
    Product,
    ProductVersion,
    Scene,
    ScriptLine,
    utcnow,
)
from drama_series_agent.episodes import ops as episode_ops
from drama_series_agent.episodes.service import SCRIPT_SLOT, scene_counts, script_product
from drama_series_agent.pipeline.drafts import PlannedChange
from drama_series_agent.pipeline.errors import PipelineError
from drama_series_agent.pipeline.products import ACTIVE_JOB_STATES, ProductService
from drama_series_agent.script import ops
from drama_series_agent.script.schema import (
    BlockRewriteIn,
    LinePatch,
    RewriteProposalOut,
    SceneOut,
    ScenePatch,
    ScriptLineOut,
    ScriptOut,
)


class Rewriter(Protocol):
    """「重写这一段」 (the script component): returns (proposed text, model key)."""

    async def rewrite(
        self,
        product: Product,
        payload: dict[str, Any],
        block_id: str,
        *,
        model: str | None,
        instruction: str | None,
        confirm_budget: bool,
    ) -> tuple[str, str]: ...


SPEAKING = ("dialogue", "vo")


async def script_slicer(
    session: AsyncSession, product: Product, version: ProductVersion, name: str
) -> Any:
    """``assets`` (素材分析, M3): scenes with their place and time, each line's id, type and
    character, and the text of the lines that are not spoken, so rewording dialogue never makes
    the asset list stale. ``shots`` (分镜规划, M4): the same without any text, so only adding,
    removing or recasting lines makes the plan stale; rewording an action line makes only the
    keyframes of its shots stale (Kelvin 2026-10-21). ``line:<id>`` (台词配音, 关键帧): what that
    line says, how and by whom (None once the script drops it). Any other name is a key of the
    payload."""
    if name.startswith("line:"):
        wanted = name.removeprefix("line:")
        for s in ops.scenes_of(version.payload_json):
            for x in s.get("lines") or []:
                if x.get("id") == wanted:
                    keys = ("type", "character_id", "tone", "text")
                    return {k: x.get(k) for k in keys}
        return None
    if name not in ("assets", "shots"):
        return version.payload_json if name == "" else version.payload_json.get(name)
    return [
        {
            "id": s["id"],
            "location_id": s.get("location_id"),
            "time": s.get("time_of_day"),
            "lines": [
                {
                    "id": x["id"],
                    "type": x.get("type"),
                    "character_id": x.get("character_id"),
                    **(
                        {}
                        if x.get("type") in SPEAKING or name == "shots"
                        else {"text": x.get("text")}
                    ),
                }
                for x in s.get("lines") or []
            ],
        }
        for s in ops.scenes_of(version.payload_json)
    ]


async def materialize(session: AsyncSession, product: Product, version: ProductVersion) -> None:
    """Mirror an adopted script: upsert the episode's scenes and lines by id, retire the ones it
    dropped."""
    episode_id = product.owner_id
    scenes = {
        r.id: r
        for r in (await session.exec(select(Scene).where(Scene.episode_id == episode_id))).all()
    }
    lines = {
        r.id: r
        for r in (
            await session.exec(select(ScriptLine).where(ScriptLine.episode_id == episode_id))
        ).all()
    }
    now = utcnow()
    kept: set[str] = set()
    for n, s in enumerate(ops.scenes_of(version.payload_json), 1):
        row = scenes.get(s["id"]) or Scene(
            id=s["id"],
            series_id=product.series_id,
            episode_id=episode_id,
            version_id=version.id,
            idx=n,
        )
        row.version_id = version.id
        row.idx = n
        row.heading = str(s.get("heading") or "")
        row.location_id = s.get("location_id")
        row.time_of_day = s.get("time_of_day")
        row.paras_json = list(s.get("paras") or [])
        row.source_spans_json = list(s.get("source_spans") or [])
        row.retired = False
        row.updated_at = now
        session.add(row)
        kept.add(row.id)
        for m, x in enumerate(s.get("lines") or [], 1):
            line = lines.get(x["id"]) or ScriptLine(
                id=x["id"],
                series_id=product.series_id,
                episode_id=episode_id,
                scene_id=s["id"],
                version_id=version.id,
                idx=m,
            )
            line.scene_id = s["id"]
            line.version_id = version.id
            line.idx = m
            line.type = str(x.get("type") or "action")
            line.character_id = x.get("character_id")
            line.character_name = x.get("character_name")
            line.tone = x.get("tone")
            line.text = str(x.get("text") or "")
            line.mood = x.get("mood")
            line.duration_s = x.get("duration_s")
            line.overlay_shot = x.get("overlay_shot")
            line.paras_json = list(x.get("paras") or [])
            line.source_spans_json = list(x.get("source_spans") or [])
            line.ai_added = bool(x.get("ai_added"))
            line.cliffhanger = bool(x.get("cliffhanger"))
            line.retired = False
            line.updated_at = now
            session.add(line)
            kept.add(line.id)
    old: list[Scene | ScriptLine] = [*scenes.values(), *lines.values()]
    for gone in old:
        if gone.id not in kept and not gone.retired:
            gone.retired = True
            gone.version_id = version.id
            gone.updated_at = now
            session.add(gone)
    # A line's dubbing retires with it, and comes back with it (台词配音, M3).
    dubbed = await session.exec(
        select(Product).where(Product.owner_type == "line", col(Product.owner_id).in_(list(lines)))
    )
    for p in dubbed.all():
        retired = p.owner_id not in kept
        if p.retired != retired:
            p.retired = retired
            p.updated_at = now
            session.add(p)


def script_out(
    episode_id: str,
    payload: dict[str, Any] | None,
    first_scene: int,
    *,
    product_id: str | None,
    version_id: str | None = None,
    adopted: bool = True,
) -> ScriptOut:
    scenes, lines = ops.view(payload or {}, first_scene)
    return ScriptOut(
        episode_id=episode_id,
        product_id=product_id,
        version_id=version_id,
        adopted=adopted,
        source_id=(payload or {}).get("source_id"),
        scenes=[
            SceneOut(
                id=s["id"],
                episode_id=episode_id,
                idx=s["idx"],
                heading=s["heading"],
                location_id=s.get("location_id"),
                time_of_day=s.get("time_of_day"),
                paras=list(s.get("paras") or []),
                source_spans=[SourceSpanOut.model_validate(x) for x in s.get("source_spans") or []],
                edited=s["edited"],
            )
            for s in scenes
        ],
        lines=[
            ScriptLineOut(
                id=x["id"],
                scene_id=x["scene_id"],
                idx=x["idx"],
                type=x["type"],
                character_id=x.get("character_id"),
                character_name=x.get("character_name"),
                tone=x.get("tone"),
                text=x["text"],
                mood=x.get("mood"),
                duration_s=x.get("duration_s"),
                overlay_shot=x.get("overlay_shot"),
                paras=list(x.get("paras") or []),
                source_spans=[SourceSpanOut.model_validate(s) for s in x.get("source_spans") or []],
                ai_added=bool(x.get("ai_added")),
                cliffhanger=bool(x.get("cliffhanger")),
                edited=x["edited"],
            )
            for x in lines
        ],
    )


class ScriptService:
    def __init__(
        self, db: Database, products: ProductService, rewriter: Rewriter | None = None
    ) -> None:
        self._db = db
        self._products = products
        self.rewriter = rewriter

    # ------------------------------------------------------------------ reads

    async def get(self, episode_id: str) -> ScriptOut:
        async with self._db.session() as session:
            ep = await session.get(Episode, episode_id)
            if ep is None or ep.retired:
                raise PipelineError(404, "episode_not_found", id=episode_id)
            p = await script_product(session, episode_id)
            v = await self._current(session, p)
            first = episode_ops.first_scene(await scene_counts(session, ep.series_id), episode_id)
        if p is None or v is None:
            return script_out(episode_id, None, first, product_id=p.id if p else None)
        return script_out(
            episode_id,
            v.payload_json,
            first,
            product_id=p.id,
            version_id=v.id,
            adopted=v.id == p.adopted_version_id,
        )

    # ------------------------------------------------------------------ edits

    async def patch_line(self, line_id: str, body: LinePatch) -> ScriptOut:
        planned = await self.plan_line(line_id, body)
        await planned.commit()
        return await self.get(await self._episode_of(planned.product_id))

    async def patch_scene(self, scene_id: str, body: ScenePatch) -> ScriptOut:
        planned = await self.plan_scene(scene_id, body)
        await planned.commit()
        return await self.get(await self._episode_of(planned.product_id))

    async def plan_line(
        self, line_id: str, body: LinePatch, *, allow_locked: bool = False
    ) -> PlannedChange:
        """改一行, worked out but not written; ``allow_locked`` for a confirmed script (the
        impact preview, ``line_edit``)."""
        p, v = await self._locate(line_id, "line_not_found", allow_locked=allow_locked)
        payload = self._apply(lambda: ops.patch_line(v.payload_json, line_id, text=body.text))
        return self._planned(p, v, payload)

    async def plan_scene(
        self, scene_id: str, body: ScenePatch, *, allow_locked: bool = False
    ) -> PlannedChange:
        """改场景标题 (``scene_edit``), as ``plan_line``."""
        p, v = await self._locate(scene_id, "scene_not_found", allow_locked=allow_locked)
        payload = self._apply(
            lambda: ops.patch_scene(v.payload_json, scene_id, heading=body.heading)
        )
        return self._planned(p, v, payload)

    async def rewrite(
        self, block_id: str, body: BlockRewriteIn, *, scene: bool
    ) -> RewriteProposalOut:
        """A proposal for a line or a scene heading; a busy product can still be asked (nothing
        is saved), a locked one too (keeping the text goes through the impact preview)."""
        if self.rewriter is None:
            raise PipelineError(409, "component_not_ready", id="script")
        missing = "scene_not_found" if scene else "line_not_found"
        p, v = await self._locate(block_id, missing, editable=False)
        find = ops.find_scene if scene else ops.find_line
        if find(v.payload_json, block_id) is None:
            raise PipelineError(404, missing, id=block_id)
        text, model = await self.rewriter.rewrite(
            p,
            v.payload_json,
            block_id,
            model=body.model,
            instruction=body.instruction,
            confirm_budget=body.confirm_budget,
        )
        return RewriteProposalOut(text=text, model_key=model)

    # ------------------------------------------------------------------ internals

    @staticmethod
    def _apply(fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        try:
            return fn()
        except ops.ScriptEditError as exc:
            status = 404 if exc.code.endswith("_not_found") else 422
            raise PipelineError(status, exc.code, **exc.params) from exc

    @staticmethod
    async def _current(session: AsyncSession, p: Product | None) -> ProductVersion | None:
        if p is None or p.current_version_id is None:
            return None
        return await session.get(ProductVersion, p.current_version_id)

    def _planned(self, p: Product, v: ProductVersion, payload: dict[str, Any]) -> PlannedChange:
        async def commit() -> None:
            await self._products.append_edit(p.id, v, payload)

        return PlannedChange(
            product_id=p.id,
            series_id=p.series_id,
            base_version_id=v.id,
            commit=commit,
            payload=payload,
            content=payload,
        )

    async def _episode_of(self, product_id: str) -> str:
        async with self._db.session() as session:
            p = await session.get(Product, product_id)
        assert p is not None
        return p.owner_id

    async def _locate(
        self, block_id: str, missing: str, *, editable: bool = True, allow_locked: bool = False
    ) -> tuple[Product, ProductVersion]:
        """The script whose version on screen has this line or scene; an edit refuses a busy or
        locked product (an edit while it runs would be lost when the run finishes; a locked one
        goes through the impact preview, which passes ``allow_locked``)."""
        async with self._db.session() as session:
            row: Scene | ScriptLine | None = await session.get(ScriptLine, block_id)
            row = row or await session.get(Scene, block_id)
            if row is not None:
                products = [p] if (p := await script_product(session, row.episode_id)) else []
            else:
                query = select(Product).where(Product.slot == SCRIPT_SLOT)
                products = list((await session.exec(query.order_by(col(Product.created_at)))).all())
            for p in products:
                v = await self._current(session, p)
                if v is None or not ops.has_block(v.payload_json, block_id):
                    continue
                if editable and p.running_job_id:
                    job = await session.get(Job, p.running_job_id)
                    if job is not None and job.state in ACTIVE_JOB_STATES:
                        raise PipelineError(409, "product_busy", id=p.id)
                if editable and not allow_locked and p.locked_hash:
                    raise PipelineError(409, "product_locked", id=p.id)
                return p, v
        raise PipelineError(404, missing, id=block_id)
