"""参考图 (SPEC 5 ``img``): candidate pictures of a character, scene or prop, one of which the
user locks as the reference every shot uses.

- A run makes ``candidates`` pictures (4) in one version, ``files[]`` ``role: candidate`` with
  ``idx``. Nothing is adopted until the user locks one (``auto_adopt = False``).
- **Hybrid** (SPEC 7.7): 「重跑」 is the local draft (``stage: draft``). 「用 API 出终版」 is a run
  with ``where: api`` and ``params.source_version_id / source_idx``: one picture on the API
  model with that draft as its reference (``stage: final``), whose parent is the draft.
- **References only come from locked assets**: a prop's picture takes the locked reference of
  each character its description names (「戴在林晚左手腕上」), and depends on it, so locking
  another picture of that character makes the prop 「待更新」. Scenes and characters take none
  (a scene is drawn empty).
- The size comes from the output spec (``media.frame_size``).

The description is the prompt's intent layer; the product does not depend on the script or the
bible, so editing the script never redraws a reference (M3 plan).
"""

from __future__ import annotations

from typing import Any

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from drama_series_agent.core.models_db import Asset, Product, ProductVersion
from drama_series_agent.modelhub.adapters.base import Estimate
from drama_series_agent.pipeline.component import ComponentError, Inputs, RunContext
from drama_series_agent.pipeline.components.media import (
    MediaComponent,
    candidate_files,
    frame_size,
    locked_ref,
    output_frame,
    prompt_text,
    ref_file,
)
from drama_series_agent.pipeline.drafts import DependencyDraft, VersionDraft
from drama_series_agent.pipeline.errors import PipelineError
from drama_series_agent.prompts.compiler import Block

REF_IMAGE_SLOT = "ref_image"
KIND_GUIDE = {
    "character": "人物全身，正面站姿，双臂自然下垂；五官、发型和整套衣着都看得清。",
    "scene": "只画空景，不要出现人物；交代空间结构、光线和天气。",
    "prop": "道具单独放在干净的浅色背景上，居中，看得清材质和细节。",
}
FINAL_NOTE = "以参考图里的草稿为准，画得更精细：构图、样子和颜色都不要改。"


async def locked_characters(session: AsyncSession, series_id: str) -> list[dict[str, Any]]:
    """The series' characters with a locked reference: name, product, file, hash."""
    rows = await session.exec(
        select(Asset, Product).where(
            Asset.series_id == series_id,
            Asset.kind == "character",
            col(Asset.retired).is_(False),
            Product.owner_type == "asset",
            Product.owner_id == Asset.id,
            Product.slot == REF_IMAGE_SLOT,
        )
    )
    out = []
    for asset, product in rows.all():
        ref = await locked_ref(session, product)
        if ref is not None:
            out.append({"name": asset.name, "product_id": product.id, "sha256": ref["sha256"]})
    return out


class ImgComponent(MediaComponent):
    id = "img"
    slot = REF_IMAGE_SLOT
    owner_type = "asset"
    auto_adopt = False
    intent_from_asset = True

    async def inputs(self, session: AsyncSession, product: Product) -> Inputs:
        asset = await session.get(Asset, product.owner_id)
        if asset is None or asset.retired:
            raise PipelineError(404, "asset_not_found", id=product.owner_id)
        frame = await output_frame(session, product.series_id)
        characters = []
        if asset.kind == "prop":
            for c in await locked_characters(session, product.series_id):
                c["hash"] = await self.services.invalidation.current_hash(
                    session, c["product_id"], ""
                )
                characters.append(c)
        return Inputs(
            blocks=[
                Block("类别", KIND_GUIDE.get(asset.kind, "")),
                Block("画幅", frame["aspect"]),
            ],
            context={"kind": asset.kind, "frame": frame, "characters": characters},
        )

    # ------------------------------------------------------------------ run

    async def run(self, ctx: RunContext, inputs: Inputs) -> VersionDraft:
        source = await self._source(ctx.product, inputs.params)
        refs, deps, blocks = self._refs(ctx.intent, inputs, source)
        frame = inputs.context["frame"]
        where = self.where_of(ctx.model_key)
        prompt = prompt_text(ctx.compiled, blocks)
        req = self.image_request(
            prompt,
            n=1 if source else self.candidates(),
            size=frame_size(frame, where),
            aspect=frame["aspect"],
            seed=ctx.seed,
            task="final" if source else "ref",
            refs=[r["sha256"] for r in refs],
        )
        call = await self.media_call(
            ctx, req, None, model=ctx.model_key, fallback_reason=ctx.fallback_reason
        )
        if not call.files:
            raise ComponentError("no_images")
        files = candidate_files(call)
        payload: dict[str, Any] = {
            "candidates": [{} for _ in files],
            "aspect": frame["aspect"],
            "refs": [r["name"] for r in refs],
        }
        stage = "final" if source else "draft" if call.where == "local" else None
        draft = self.media_draft(ctx, inputs, payload, files, [call], prompt, stage=stage)
        draft.dependencies = [*draft.dependencies, *deps]
        if source:
            draft.params["source"] = {"version_id": source[0].id, "idx": source[1]}
        return draft

    def estimate(self, inputs: Inputs, compiled: str, model: str) -> Estimate:
        source = bool(inputs.params.get("source_version_id"))
        frame = inputs.context["frame"]
        req = self.image_request(
            compiled,
            n=1 if source else self.candidates(),
            size=frame_size(frame, self.where_of(model)),
            aspect=frame["aspect"],
            seed=None,
            task="final" if source else "ref",
        )
        return self.services.registry.get(model).estimate(req)

    # ------------------------------------------------------------------ internals

    async def _source(
        self, product: Product, params: dict[str, Any]
    ) -> tuple[ProductVersion, int] | None:
        """The draft an API final starts from (``params.source_version_id / source_idx``)."""
        version_id = params.get("source_version_id")
        if not version_id:
            return None
        idx = int(params.get("source_idx") or 0)
        async with self.services.db.session() as session:
            v = await session.get(ProductVersion, str(version_id))
        if v is None or v.product_id != product.id:
            raise ComponentError("version_not_found", id=version_id)
        if not any(f.get("role") == "candidate" and f.get("idx") == idx for f in v.files_json):
            raise ComponentError("no_such_candidate", id=v.id, idx=idx)
        return v, idx

    @staticmethod
    def _refs(
        intent: str, inputs: Inputs, source: tuple[ProductVersion, int] | None
    ) -> tuple[list[dict[str, Any]], list[DependencyDraft], list[Block]]:
        """The reference pictures (the draft first), what they make it depend on, and the
        blocks that say what each one is."""
        refs: list[dict[str, Any]] = []
        deps: list[DependencyDraft] = []
        blocks = list(inputs.blocks)
        if source is not None:
            v, idx = source
            f = next(
                (x for x in v.files_json if x.get("role") == "candidate" and x.get("idx") == idx),
                None,
            ) or ref_file(v)
            if f is not None:
                refs.append({"name": "草稿", "sha256": f["sha256"]})
                blocks.append(Block("草稿", FINAL_NOTE))
        named = [c for c in inputs.context.get("characters") or [] if c["name"] in intent]
        for c in named:
            refs.append(c)
            if c.get("hash"):
                deps.append(DependencyDraft(c["product_id"], c["hash"], ""))
        if named:
            names = "、".join(c["name"] for c in named)
            blocks.append(Block("参考图", f"{names}：已锁定的角色参考图，样子要和它一致。"))
        return refs, deps, blocks
