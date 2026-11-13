"""以这张为底重画 (M5.5 step 13, ``redraw``): one picture of a version drawn again from itself,
as a new version of the same product (origin ``redraw``).

- **What it works on**: a keyframe candidate, a reference picture (candidate or the locked one),
  one of a character's six views, an uploaded picture of any of these. It runs on that product
  (``RunService.start(component_id="redraw")``): the product's own prompt is left alone, the
  request's instruction is this run's intent.
- **改动幅度** ``strength`` (0.1–1.0): locally FLUX 3 Klein starts from the picture and samples
  with ``denoise = strength`` (``workflows/flux3-klein-redraw``); Qwen-Image-Edit and the APIs
  (Nano Banana 2.1, GPT Image 2) have no number for it, so it is said in words, the picture
  being reference 1.
- **The new version**: a keyframe or reference picture gets one candidate (not adopted, the
  user picks as before); a views set gets that view replaced, the others copied, adopted like
  every views version. It keeps the dependencies of the version it came from: what made that
  one outdated makes this one outdated.
"""

from __future__ import annotations

from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from drama_series_agent.core.models_db import Dependency, Product, ProductVersion, Shot
from drama_series_agent.modelhub.adapters.base import Estimate
from drama_series_agent.pipeline.component import ComponentError, Inputs, RunContext
from drama_series_agent.pipeline.components.media import (
    MediaCall,
    MediaComponent,
    frame_size,
    output_frame,
    prompt_text,
)
from drama_series_agent.pipeline.drafts import DependencyDraft, VersionDraft, file_entry
from drama_series_agent.pipeline.errors import PipelineError
from drama_series_agent.prompts.compiler import Block
from drama_series_agent.spec.dims import Dims

KEYFRAME, REF_IMAGE, REF_VIEWS = "keyframe", "ref_image", "ref_views"
REDRAW_SLOTS = (KEYFRAME, REF_IMAGE, REF_VIEWS)
DEFAULT_STRENGTH = 0.5
ASPECTS = {"1:1": 1.0, "16:9": 16 / 9, "9:16": 9 / 16, "4:3": 4 / 3, "3:4": 3 / 4}


def strength_words(strength: float) -> str:
    """改动幅度 in words, for the models that take no number for it."""
    if strength < 0.35:
        return "只做细微的改动：构图、人物、光线都不变，只改要求的那一点"
    if strength < 0.7:
        return "改动适中：按要求改，其余尽量保持参考图 1 的样子"
    return "可以大改：按要求重新画，人物的长相和服装、场景的样子仍和参考图 1 一致"


def nearest_aspect(w: int, h: int) -> str:
    ratio = w / h if h else 1.0
    return min(ASPECTS, key=lambda a: abs(ASPECTS[a] - ratio))


def picked_file(v: ProductVersion, slot: str, idx: int) -> dict[str, Any] | None:
    """The picture ``idx`` of a version: a view's number for a views set, else a candidate's
    (a locked version holds one ``ref``)."""
    files = [f for f in v.files_json if f.get("role") != "prompt"]
    if slot == REF_VIEWS:
        return next((f for f in files if f.get("role") == "view" and f.get("idx") == idx), None)
    found = next((f for f in files if f.get("role") == "candidate" and f.get("idx") == idx), None)
    if found is None and idx == 0:
        found = next((f for f in files if f.get("role") in ("ref", "candidate")), None)
    return found


class RedrawComponent(MediaComponent):
    id = "redraw"
    # It runs on the products of other components (``RunService.start(component_id=…)``);
    # none is ever made for it.
    slot = "redraw"
    owner_type = "version"
    auto_adopt = False
    cascade_rerun = False

    async def inputs(self, session: AsyncSession, product: Product) -> Inputs:
        if product.slot not in REDRAW_SLOTS:
            raise PipelineError(422, "redraw_not_supported", slot=product.slot)
        episode_id = None
        if product.owner_type == "shot":
            shot = await session.get(Shot, product.owner_id)
            episode_id = shot.episode_id if shot is not None else None
        return Inputs(
            blocks=[],
            episode_id=episode_id,
            context={"frame": await output_frame(session, product.series_id), "slot": product.slot},
        )

    async def _source(
        self, product: Product, params: dict[str, Any]
    ) -> tuple[ProductVersion, dict[str, Any], list[DependencyDraft]]:
        version_id = str(params.get(f"{self.id}_version_id") or "")
        idx = int(params.get(f"{self.id}_idx") or 0)
        async with self.services.db.session() as session:
            v = await session.get(ProductVersion, version_id)
            if v is None or v.product_id != product.id:
                raise PipelineError(404, "version_not_found", id=version_id)
            deps = (
                await session.exec(select(Dependency).where(Dependency.version_id == v.id))
            ).all()
        f = picked_file(v, product.slot, idx)
        if f is None:
            raise PipelineError(404, "file_not_found", id=version_id, idx=idx)
        kept = [DependencyDraft(d.upstream_product_id, d.upstream_hash, d.slice) for d in deps]
        return v, f, kept

    def _size(self, inputs: Inputs, f: dict[str, Any], where: str) -> tuple[Dims, str]:
        frame = inputs.context["frame"]
        if inputs.context["slot"] == REF_IMAGE:  # a reference keeps its own shape
            w, h = int(f.get("w") or 1024), int(f.get("h") or 1024)
            return Dims(w=w, h=h), nearest_aspect(w, h)
        return frame_size(frame, where), str(frame["aspect"])

    # What a redraw sends and records; ``inpaint`` (M5.5 step 14) says its own.
    def _base(self, params: dict[str, Any], sha: str) -> str:
        """The picture the model starts from."""
        return sha

    def _extra(self, params: dict[str, Any], base: str) -> dict[str, Any]:
        return {"base_image": base, "denoise": self._strength(params)}

    def _blocks(self, params: dict[str, Any]) -> list[Block]:
        return [Block("改动幅度", strength_words(self._strength(params)))]

    def _record(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"strength": self._strength(params)}

    @staticmethod
    def _strength(params: dict[str, Any]) -> float:
        return float(params.get("strength") or DEFAULT_STRENGTH)

    async def run(self, ctx: RunContext, inputs: Inputs) -> VersionDraft:
        params = inputs.params
        v, f, kept = await self._source(ctx.product, params)
        inputs.deps = kept
        sha = str(f["sha256"])
        base = self._base(params, sha)
        prompt = prompt_text(ctx.compiled, self._blocks(params))

        async def flow(model: str, reason: str | None) -> list[MediaCall]:
            size, aspect = self._size(inputs, f, self.where_of(model))
            req = self.image_request(
                prompt, n=1, size=size, aspect=aspect, seed=ctx.seed, task=self.id,
                refs=[base], extra=self._extra(params, base),
            )  # fmt: skip
            return [
                await self.media_call(
                    ctx, req, inputs.episode_id, model=model, fallback=False,
                    fallback_reason=reason,
                )
            ]  # fmt: skip

        calls, reason = await self.run_flow(ctx, flow)
        out = calls[0].files[:1]
        if not out:
            raise ComponentError("no_images")
        got = out[0]
        record = {
            "version_id": v.id,
            "idx": int(params.get(f"{self.id}_idx") or 0),
            "from": sha,
            **self._record(params),
        }
        if inputs.context["slot"] == REF_VIEWS:
            view = f.get("view")
            files = [
                file_entry("view", got.sha256, got.mime, w=got.w, h=got.h, idx=x["idx"], view=view)
                if x.get("view") == view
                else dict(x)
                for x in v.files_json
                if x.get("role") == "view"
            ]
            payload = dict(v.payload_json)
            uploaded = [u for u in payload.get("uploaded", []) if u != view]
            payload.pop("uploaded", None)
            payload.pop("redraw", None)
            payload.pop("inpaint", None)
            if uploaded:
                payload["uploaded"] = uploaded
        else:
            files = [file_entry("candidate", got.sha256, got.mime, w=got.w, h=got.h, idx=0)]
            payload = {"candidates": [{}]}
            if "aspect" in v.payload_json:
                payload["aspect"] = v.payload_json["aspect"]
        payload[self.id] = record
        draft = self.media_draft(
            ctx, inputs, payload, files, calls, prompt, fallback_reason=reason,
            params={self.id: record},
        )  # fmt: skip
        if inputs.context["slot"] == KEYFRAME:
            draft.stage = "draft" if calls[0].where == "local" else None
        return draft

    def estimate(self, inputs: Inputs, compiled: str, model: str) -> Estimate:
        frame = inputs.context["frame"]
        req = self.image_request(
            compiled,
            n=1,
            size=frame_size(frame, self.where_of(model)),
            aspect=frame["aspect"],
            seed=None,
            task=self.id,
            refs=["-"],
        )
        return self.services.registry.get(model).estimate(req)


async def redraw_target(
    session: AsyncSession, version_id: str, idx: int, what: str = "redraw"
) -> tuple[Product, dict[str, Any]]:
    """The product a redraw (or an inpaint, ``what``) of picture ``idx`` of ``version_id`` makes
    a version of, and that picture's file entry; 404 when there is no such picture, 422
    ``{what}_not_supported`` for a product it does not take, 409 once it is locked."""
    v = await session.get(ProductVersion, version_id)
    p = await session.get(Product, v.product_id) if v is not None else None
    if v is None or p is None or p.retired:
        raise PipelineError(404, "version_not_found", id=version_id)
    if p.slot not in REDRAW_SLOTS:
        raise PipelineError(422, f"{what}_not_supported", slot=p.slot)
    if p.locked_hash:
        raise PipelineError(409, "product_locked", id=p.id)
    f = picked_file(v, p.slot, idx)
    if f is None:
        raise PipelineError(404, "file_not_found", id=version_id, idx=idx)
    return p, f
