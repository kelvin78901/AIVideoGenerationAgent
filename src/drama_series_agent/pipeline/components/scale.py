"""比例参考 (M5.5 ``scale``): once a prop's reference is locked, one real-looking photo of it with
a locked character, so every keyframe after sees how big it is next to a person.

Run 17's umbrella stood as tall as the door handle: its locked picture was a lone product shot,
nothing in it to measure by. The prop's real size (``physical``, M5.5 step 5a) goes in the
prompt; this picture shows it.

- Runs by itself after the prop is locked (``AssetService.lock``), every run adopted, like
  补视图 (``views``): it follows the locked pictures, it is not chosen.
- The character: one whose name the prop's description mentions, else the one that shares the
  most scenes with it, else the series' first locked one; none locked → 409
  ``no_character`` and nothing is drawn (a warning in the log).
- Depends on both locked pictures, so a new lock of either makes it 「待更新」.
- The keyframe sends it right after the prop's own picture (``kf._references``).
"""

from __future__ import annotations

from typing import Any

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from drama_series_agent.assets.ops import physical_text
from drama_series_agent.core.models_db import Asset, AssetUse, Product
from drama_series_agent.modelhub.adapters.base import Estimate
from drama_series_agent.pipeline.component import Inputs, RunContext
from drama_series_agent.pipeline.components.img import REF_IMAGE_SLOT, prop_physical
from drama_series_agent.pipeline.components.media import (
    MediaCall,
    MediaComponent,
    frame_size,
    locked_ref,
    output_frame,
    prompt_text,
)
from drama_series_agent.pipeline.drafts import VersionDraft, file_entry
from drama_series_agent.pipeline.errors import PipelineError
from drama_series_agent.prompts.compiler import Block

REF_SCALE_SLOT = "ref_scale"
SCALE_GUIDE = (
    "实拍照片，一张完整的画面：参考图 1 的人物自然地拿着、或站在参考图 2 的道具旁边，人物全身入画，"
    "看得出道具和人的真实比例；道具的样子、颜色、材质、上面的字和参考图 2 一模一样，人物的长相、"
    "发型、衣着和参考图 1 一样。"
)
# Run 19: the note's description says it is stuck on the umbrella's handle, and this picture drew
# a black umbrella for it, which 1-04's keyframe copied (a black umbrella, a second note). The
# picture is only for the size: the prop alone, nothing the scene would have.
ONLY_PROP = (
    "画面里只有这个人和这件道具，不要画任何别的物件（道具的描述里说它贴在、放在、挂在别的东西上，"
    "也只画道具本身）；背景是素净的浅色墙面，光线均匀柔和，没有窗户、灯具和家具，不是棚拍产品图。"
)


async def asset_ref(session: AsyncSession, asset_id: str) -> tuple[Product, dict[str, Any]] | None:
    """An asset's reference product and its locked picture, if locked."""
    p = (
        await session.exec(
            select(Product).where(
                Product.owner_type == "asset",
                Product.owner_id == asset_id,
                Product.slot == REF_IMAGE_SLOT,
            )
        )
    ).first()
    ref = await locked_ref(session, p) if p is not None else None
    return (p, ref) if p is not None and ref is not None else None


async def scale_character(
    session: AsyncSession, prop: Asset, description: str
) -> tuple[Asset, Product, dict[str, Any]] | None:
    """The locked character the prop is shown with (see the module's docstring)."""
    rows = await session.exec(
        select(Asset).where(
            Asset.series_id == prop.series_id,
            Asset.kind == "character",
            col(Asset.retired).is_(False),
        )
    )
    locked: list[tuple[Asset, Product, dict[str, Any]]] = []
    for c in sorted(rows.all(), key=lambda a: (int((a.seed_json or {}).get("order") or 0), a.id)):
        found = await asset_ref(session, c.id)
        if found is not None:
            locked.append((c, *found))
    if not locked:
        return None
    named = [x for x in locked if x[0].name and x[0].name in description]
    if named:
        return named[0]
    uses = list((await session.exec(select(AssetUse))).all())
    scenes_of: dict[str, set[str]] = {}
    for u in uses:
        scenes_of.setdefault(u.asset_id, set()).add(u.scene_id)
    mine = scenes_of.get(prop.id, set())
    return max(locked, key=lambda x: len(scenes_of.get(x[0].id, set()) & mine))


class ScaleComponent(MediaComponent):
    id = "scale"
    slot = REF_SCALE_SLOT
    owner_type = "asset"
    # It follows the locked pictures; never chosen, so each run is adopted.
    adopt_every_run = True

    async def inputs(self, session: AsyncSession, product: Product) -> Inputs:
        prop = await session.get(Asset, product.owner_id)
        if prop is None or prop.retired or prop.kind != "prop":
            raise PipelineError(404, "asset_not_found", id=product.owner_id)
        mine = await asset_ref(session, prop.id)
        if mine is None:
            raise PipelineError(409, "upstream_not_locked", slot=REF_IMAGE_SLOT)
        prop_product, prop_ref = mine
        description = str(
            (prop_product.prompt_json or {}).get("intent")
            or (prop.seed_json or {}).get("description")
            or ""
        )
        found = await scale_character(session, prop, description)
        if found is None:
            raise PipelineError(409, "no_character", id=prop.id)
        character, character_product, character_ref = found
        invalidation = self.services.invalidation
        deps = [
            await invalidation.dependency(session, character_product.id, ""),
            await invalidation.dependency(session, prop_product.id, ""),
        ]
        blocks = [
            Block("比例参考", SCALE_GUIDE),
            Block("只有道具", ONLY_PROP),
            Block("人物", character.name),
            Block("道具", f"{prop.name}：{description}" if description else prop.name),
        ]
        if size := physical_text(prop_physical(prop, prop_product)):
            blocks.append(Block("真实尺寸和材质", size))
        return Inputs(
            blocks=blocks,
            deps=deps,
            context={
                "frame": await output_frame(session, product.series_id),
                "refs": [character_ref["sha256"], prop_ref["sha256"]],
                "character": character.name,
            },
        )

    async def run(self, ctx: RunContext, inputs: Inputs) -> VersionDraft:
        frame = inputs.context["frame"]
        prompt = prompt_text(ctx.compiled, inputs.blocks)

        async def flow(model: str, reason: str | None) -> list[MediaCall]:
            req = self.image_request(
                prompt,
                n=1,
                size=frame_size(frame, self.where_of(model)),
                aspect=frame["aspect"],
                seed=ctx.seed,
                task="scale",
                refs=list(inputs.context["refs"]),
            )
            return [
                await self.media_call(
                    ctx, req, None, model=model, fallback=False, fallback_reason=reason
                )
            ]

        calls, reason = await self.run_flow(ctx, flow)
        files = [
            file_entry("scale", f.sha256, f.mime, w=f.w, h=f.h, idx=0) for f in calls[0].files[:1]
        ]
        payload = {"character": inputs.context["character"], "from": inputs.context["refs"]}
        return self.media_draft(ctx, inputs, payload, files, calls, prompt, fallback_reason=reason)

    def estimate(self, inputs: Inputs, compiled: str, model: str) -> Estimate:
        frame = inputs.context["frame"]
        req = self.image_request(
            compiled,
            n=1,
            size=frame_size(frame, self.where_of(model)),
            aspect=frame["aspect"],
            seed=None,
            task="scale",
        )
        return self.services.registry.get(model).estimate(req)
