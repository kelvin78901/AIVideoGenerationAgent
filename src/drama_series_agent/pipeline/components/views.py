"""补视图 (M3 ``views``): once a character's reference is locked, its side view, back view and
four expressions, drawn from that picture.

- **One expression a picture** (Kelvin 2026-10-21): a 2×2 sheet of expressions came back as
  three or six small faces, warped (hands in mouths, seams) on the four-step model; one
  head-and-shoulders face filling the frame keeps its pixels. Expressions are asked for
  restrained, not exaggerated, which is also what keeps faces from warping.

- Runs by itself after the lock (``AssetService.lock``) and every run is adopted
  (``adopt_every_run``): the views follow the locked picture, they are not chosen.
- Depends on the locked reference (its picture's hash), so locking another picture makes the
  views 「待更新」 and the next lock draws them again.
- One call per view with the locked picture as the reference, ``fallback=False``; if one fails
  the set is drawn again on the fallback model (``run_flow``), so a set never mixes models.
- Locally it is the editing model (Qwen-Image-Edit), not the one that draws the references,
  on the official 40 steps at cfg 4.0 (``comfy/qwen-image-edit-hq``, Kelvin 2026-10-21): the
  four-step LoRA left skin plastic and edges soft, and ignores negative prompts. Each view
  goes with a negative prompt (``negative_for``).
"""

from __future__ import annotations

from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from drama_series_agent.core.models_db import Asset, Product
from drama_series_agent.modelhub.adapters.base import Estimate
from drama_series_agent.pipeline.component import Inputs, RunContext
from drama_series_agent.pipeline.components.img import REF_IMAGE_SLOT
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

REF_VIEWS_SLOT = "ref_views"
FACE = "正面头肩特写，只画这一个人、这一张脸，单幅画面不拼图"
VIEWS = {
    "side": (
        "侧面：标准正侧面，人物的脸和身体都转向画面左侧 90°，只看得到一只眼睛，平视前方，全身站姿。"
    ),
    "back": "背面：人物完全背对镜头，头和身体都不转，全身站姿，看得清发型和衣服背后。",
    "calm": f"表情 · 平静：{FACE}，表情平静自然。",
    "smile": f"表情 · 微笑：{FACE}，自然的微笑。",
    "angry": (
        f"表情 · 愤怒：{FACE}，压着火的怒意：眉头紧锁、嘴唇紧闭、眼神发冷，克制不夸张，五官不变形。"
    ),
    "sad": f"表情 · 难过：{FACE}，难过：眼神低垂、嘴角微微下沉、神情落寞，克制不夸张，五官不变形。",
}
# Negative prompts: on the 40-step model (cfg 4.0) the prompt is followed in earnest, 「生气」 came
# back as bared teeth and 「难过」 as crying (Kelvin 2026-10-21); models that take no negative
# prompt (the APIs, the 4-step LoRA at cfg 1.0) ignore it.
NEGATIVE = "低画质，模糊，畸形，五官变形，拼图，分格，水印，文字"
NEGATIVE_EXTRA = {
    "side": "正脸，3/4 侧脸，两只眼睛，仰头",
    "back": "侧脸，回头，转身",
    "angry": "龇牙，露齿，张嘴，皱鼻子，狰狞，夸张表情",
    "sad": "哭泣，眼泪，张嘴，五官扭曲，夸张表情",
}


def negative_for(view: str) -> str:
    extra = NEGATIVE_EXTRA.get(view)
    return f"{NEGATIVE}，{extra}" if extra else NEGATIVE


async def ref_image_product(session: AsyncSession, asset_id: str) -> Product | None:
    query = select(Product).where(
        Product.owner_type == "asset", Product.owner_id == asset_id, Product.slot == REF_IMAGE_SLOT
    )
    return (await session.exec(query)).first()


class ViewsComponent(MediaComponent):
    id = "views"
    slot = REF_VIEWS_SLOT
    owner_type = "asset"
    # The views follow the locked picture; they are never chosen, so each run is adopted.
    adopt_every_run = True

    async def inputs(self, session: AsyncSession, product: Product) -> Inputs:
        asset = await session.get(Asset, product.owner_id)
        if asset is None or asset.retired or asset.kind != "character":
            raise PipelineError(404, "asset_not_found", id=product.owner_id)
        ref_product = await ref_image_product(session, asset.id)
        ref = await locked_ref(session, ref_product) if ref_product is not None else None
        if ref_product is None or ref is None:
            raise PipelineError(409, "upstream_not_locked", slot=REF_IMAGE_SLOT)
        dep = await self.services.invalidation.dependency(session, ref_product.id, "")
        return Inputs(
            blocks=[Block("人物", asset.name)],
            deps=[dep],
            context={"frame": await output_frame(session, product.series_id), "ref": ref},
        )

    async def run(self, ctx: RunContext, inputs: Inputs) -> VersionDraft:
        frame = inputs.context["frame"]
        ref = inputs.context["ref"]["sha256"]
        prompts = {
            view: prompt_text(ctx.compiled, [*inputs.blocks, Block("视图", text)])
            for view, text in VIEWS.items()
        }

        async def flow(model: str, reason: str | None) -> list[MediaCall]:
            size = frame_size(frame, self.where_of(model))
            calls = []
            for view, prompt in prompts.items():
                req = self.image_request(
                    prompt,
                    n=1,
                    size=size,
                    aspect=frame["aspect"],
                    seed=ctx.seed,
                    task=f"views:{view}",
                    refs=[ref],
                    extra={"negative": negative_for(view)},
                )
                calls.append(
                    await self.media_call(
                        ctx, req, None, model=model, fallback=False, fallback_reason=reason
                    )
                )
            return calls

        calls, reason = await self.run_flow(ctx, flow)
        files: list[dict[str, Any]] = []
        for i, (view, call) in enumerate(zip(VIEWS, calls, strict=True)):
            for f in call.files[:1]:
                files.append(file_entry("view", f.sha256, f.mime, w=f.w, h=f.h, idx=i, view=view))
        payload = {
            "views": list(VIEWS),
            "from": ref,
            "negative": {view: negative_for(view) for view in VIEWS},
        }
        sent = "\n\n---\n\n".join(prompts.values())
        return self.media_draft(ctx, inputs, payload, files, calls, sent, fallback_reason=reason)

    def estimate(self, inputs: Inputs, compiled: str, model: str) -> Estimate:
        frame = inputs.context["frame"]
        req = self.image_request(
            compiled,
            n=len(VIEWS),
            size=frame_size(frame, self.where_of(model)),
            aspect=frame["aspect"],
            seed=None,
            task="views",
        )
        return self.services.registry.get(model).estimate(req)
