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
- The size comes from the output spec (``media.frame_size``), except for a kind whose aspect
  ``components.yaml`` fixes (``aspects``): scenes are drawn 16:9 whatever the spec, since
  Qwen-Image draws an empty place in 9:16 as a grid of panels (M4 step 9, Kelvin 2026-10-26).

The description is the prompt's intent layer; the product does not depend on the script or the
bible, so editing the script never redraws a reference (M3 plan).
"""

from __future__ import annotations

from typing import Any

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from drama_series_agent.assets.ops import physical_from, physical_text
from drama_series_agent.core.config import get_config
from drama_series_agent.core.models_db import Asset, Product, ProductVersion
from drama_series_agent.modelhub.adapters.base import CallContext, Estimate
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
from drama_series_agent.qa import ocr

REF_IMAGE_SLOT = "ref_image"
KIND_GUIDE = {
    "character": "人物全身，正面站姿，双臂自然下垂；五官、发型和整套衣着都看得清。",
    "scene": "只画空景，不要出现人物；一个视角、一张完整的照片，看得清空间、光线和天气。",
    # Not a studio product shot (M5 step 15o): run17's umbrella came out CG-clean and, with
    # nothing to measure it by, twice its size in the keyframes.
    "prop": (
        "道具单独一件、居中，实拍照片质感：真实材质、有使用痕迹，自然光，放在它平时会在的简单真实"
        "表面上（木桌、地面、墙边），不是棚拍产品图或 CG 渲染；旁边带一个大家熟悉大小的东西"
        "（手、门框、桌面）看得出它的真实尺寸；看得清材质和细节。"
    ),
}
FINAL_NOTE = "以参考图里的草稿为准，画得更精细：构图、样子和颜色都不要改。"
STYLE_GUIDE = {
    "handwritten": "手写：圆珠笔写在纸上，笔画自然，有一点倾斜和深浅变化。",
    "printed": "印刷：清楚的黑体或宋体，排得整齐。",
    "screen": "屏幕界面：手机或电脑的系统字体，清晰、发光，界面简洁。",
}
# 有字的道具 (M5.5): the writing is part of the prop, drawn on its own picture.
PROP_TEXT = "道具上的字，必须逐字一致"


def text_settings(asset: Asset, settings: dict[str, Any] | None) -> dict[str, str]:
    """The characters, how they are made and the lettering: the product's settings over what
    the analysis found."""
    seed = (asset.seed_json or {}).get("text") or {}
    mine = (settings or {}).get("text") or {}
    return {"exact": "", "method": "composite", "style": "printed", **seed, **mine}


def prop_text(asset: Asset, product: Product | None) -> dict[str, str] | None:
    """The writing on a prop (M5.5: the note's 「楼下便利店，等你到十二点。」), always drawn by
    the model; None when the prop has none."""
    if asset.kind != "prop":
        return None
    text = text_settings(asset, product.settings_json if product else None)
    return {**text, "method": "model"} if text["exact"].strip() else None


def prop_physical(asset: Asset, product: Product | None) -> dict[str, str] | None:
    """A prop's size, material and wear: what the user set on its picture (``settings``),
    else what the analysis found (M5.5)."""
    given = physical_from(((product.settings_json if product else None) or {}).get("physical"))
    return given or physical_from((asset.seed_json or {}).get("physical"))


def asset_aspect(kind: str, spec_aspect: str) -> str:
    """The aspect a reference picture of ``kind`` is drawn at: the one ``components.yaml``
    fixes for it, else the output spec's."""
    try:
        fixed = get_config().components.component("img").aspects
    except KeyError:
        fixed = {}
    return fixed.get(kind) or spec_aspect


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
        frame = {**frame, "aspect": asset_aspect(asset.kind, frame["aspect"])}
        characters = []
        if asset.kind == "prop":
            for c in await locked_characters(session, product.series_id):
                c["hash"] = await self.services.invalidation.current_hash(
                    session, c["product_id"], ""
                )
                characters.append(c)
        blocks = [Block("类别", KIND_GUIDE.get(asset.kind, "")), Block("画幅", frame["aspect"])]
        if asset.kind == "prop" and (size := physical_text(prop_physical(asset, product))):
            blocks.append(Block("真实尺寸和材质", size))
        context: dict[str, Any] = {"kind": asset.kind, "frame": frame, "characters": characters}
        if (text := prop_text(asset, product)) is not None:
            blocks += [
                Block(PROP_TEXT, f"「{text['exact']}」"),
                Block("字迹", STYLE_GUIDE.get(text["style"], "")),
            ]
            context["text"] = text
        return Inputs(blocks=blocks, context=context)

    # ------------------------------------------------------------------ run

    async def run(self, ctx: RunContext, inputs: Inputs) -> VersionDraft:
        source = await self.source_candidate(ctx.product, inputs.params)
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
            extra=self.picture_params(inputs),
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
        if (text := inputs.context.get("text")) is not None:
            # 画面文字 and a prop's writing: OCR reads each candidate back (only a warning).
            call_ctx = self._call_ctx(ctx, None)
            checked = []
            for f in draft.files:
                if f.get("role") == "candidate":
                    read = await ocr.read(
                        self.services.router, self.services.store, f["sha256"], call_ctx
                    )
                    checked.append(ocr.check(text["exact"], read, text["method"]))
            draft.payload = {**draft.payload, "candidates": checked, "text": text}
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
            extra=self.picture_params(inputs),
        )
        return self.services.registry.get(model).estimate(req)

    def picture_params(self, inputs: Inputs) -> dict[str, Any]:
        """Extra request params: the characters a model draws (画面文字, a prop's writing)."""
        text = inputs.context.get("text")
        return {"text": text["exact"]} if text and text["method"] == "model" else {}

    async def check_upload(
        self, asset: Asset, product: Product, sha256: str
    ) -> tuple[dict[str, Any], dict[str, str]]:
        """An uploaded picture's OCR against the text's settings now, and those settings."""
        text = prop_text(asset, product) or text_settings(asset, product.settings_json)
        ctx = CallContext(component_id=self.id, series_id=product.series_id, product_id=product.id)
        read = await ocr.read(self.services.router, self.services.store, sha256, ctx)
        return ocr.check(text["exact"], read, text["method"]), text

    # ------------------------------------------------------------------ internals

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
