"""2K 精修 of a take (M6 step 6, ``up``; plan E1): a take made larger with its detail filled in,
nothing else changed. A new version of the shot's video product (origin ``upscale``, parent =
the take, ``stage = final``), checked by QA like every take.

- **What it runs on**: the video product (``RunService.start(component_id="up")``, as a
  picture's 放大 runs ``iup`` on a keyframe), ``params.up_version_id`` the take. The product's
  own prompt is left alone; a run makes one version.
- **How large**: the delivery size of the output spec, at its frame rate (hard rule 10). A take
  already that large is refused (409 ``upscale_not_needed``: an API take is made at it).
- **Locally** SeedVR2 7B (``workflows/seedvr2-up``) falling back to FlashVSR
  (``workflows/flashvsr-up``), both from the take as stored (trimmed) and kept as long; the
  sound is the take's own, put back by stream copy whatever the workflow returns (音轨原样).
- **The API** (H3 Regenerate-2K) only takes a local H3 draft: it is 「用 API 出终版」
  (``VidComponent._final``), made from the untrimmed draft and its request. Another take on an
  API route is refused (409 ``upscale_unavailable``, ``not_regenerable``). Topaz has no adapter.
- **Adopted** after QA when the take it came from is the adopted one, it passed and the product
  is not locked (Kelvin 2026-11-14, ``pipeline/qa_policy.py:adopt_finished``); otherwise a
  candidate. ``params.finish`` says what it finished and from which take.
- It keeps the take's dependencies: what makes the take outdated makes this one outdated.
"""

from __future__ import annotations

from typing import Any, ClassVar

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from drama_series_agent.core.config import Resolved
from drama_series_agent.core.models_db import Dependency, Product, ProductVersion
from drama_series_agent.media.video import VideoError, with_sound_of
from drama_series_agent.modelhub.adapters.base import Estimate, ModelRequest
from drama_series_agent.modelhub.adapters.mock import Responder
from drama_series_agent.pipeline import takecheck
from drama_series_agent.pipeline.component import (
    ComponentError,
    Inputs,
    ModelChoice,
    RunContext,
)
from drama_series_agent.pipeline.components.media import MediaCall
from drama_series_agent.pipeline.components.vid import VidComponent, clip_files, is_h3, take_asks
from drama_series_agent.pipeline.drafts import DependencyDraft, VersionDraft
from drama_series_agent.pipeline.errors import PipelineError
from drama_series_agent.pipeline.qa_policy import FINISH
from drama_series_agent.spec.dims import Dims, dims

UPSCALE = "upscale"


def take_video(v: ProductVersion) -> dict[str, Any] | None:
    return next((f for f in v.files_json if f.get("role") == "video"), None)


def regenerable(v: ProductVersion) -> bool:
    """A local H3 draft Regenerate-2K can make again (its untrimmed clip and request kept)."""
    return (
        v.where == "local"
        and is_h3(v.model_key or "")
        and any(f.get("role") == "raw" for f in v.files_json)
        and bool((v.params_json or {}).get("request"))
        and any(f.get("role") == "prompt" for f in v.files_json)
    )


class UpComponent(VidComponent):
    id = "up"
    # It runs on the shot's video product; none is ever made for it.
    slot = "up"
    owner_type = "version"
    auto_adopt = False
    cascade_rerun = False
    origin: ClassVar[str | None] = UPSCALE
    finishing: ClassVar[tuple[str, ...]] = ()

    async def default_intent(self, session: AsyncSession, product: Product, lang: str) -> str:
        return ""

    async def run_count(self, session: AsyncSession, product: Product) -> int:
        return 1

    def model_for(self, inputs: Inputs, model: str, settings: Resolved) -> str:
        return model

    async def choose_model(
        self,
        product: Product,
        inputs: Inputs,
        model: str,
        settings: Resolved,
        *,
        lang: str,
        named: bool,
        ask: bool,
    ) -> ModelChoice:
        """The route's model; when a run is asked for, the take is checked first (409s)."""
        if ask:
            take = await self._take_of(product, inputs.params)
            self._check(take, inputs, model)
        return ModelChoice(model)

    def mock_responders(self) -> dict[str, Responder]:
        return {}

    # ------------------------------------------------------------------ run

    def target(self, inputs: Inputs) -> Dims:
        frame_ = inputs.context["frame"]
        return dims(frame_["aspect"], frame_["delivery"])

    def _check(self, take: ProductVersion, inputs: Inputs, model: str) -> None:
        video = take_video(take)
        if video is None:
            raise PipelineError(409, "not_a_take", id=take.id)
        size = self.target(inputs)
        if int(video.get("w") or 0) >= size.w and int(video.get("h") or 0) >= size.h:
            raise PipelineError(409, "upscale_not_needed", id=take.id, w=size.w, h=size.h)
        if self.where_of(model) == "api" and not regenerable(take):
            raise PipelineError(409, "upscale_unavailable", reason="not_regenerable")

    async def _take_of(self, product: Product, params: dict[str, Any]) -> ProductVersion:
        version_id = str(params.get(f"{self.id}_version_id") or "")
        async with self.services.db.session() as session:
            v = await session.get(ProductVersion, version_id)
        if v is None or v.product_id != product.id:
            raise PipelineError(404, "version_not_found", id=version_id)
        return v

    async def _kept_deps(self, take: ProductVersion) -> list[DependencyDraft]:
        async with self.services.db.session() as session:
            rows = (
                await session.exec(select(Dependency).where(Dependency.version_id == take.id))
            ).all()
        return [DependencyDraft(d.upstream_product_id, d.upstream_hash, d.slice) for d in rows]

    async def run(self, ctx: RunContext, inputs: Inputs) -> VersionDraft:
        take = await self._take_of(ctx.product, inputs.params)
        self._check(take, inputs, ctx.model_key)
        finish = {"kind": UPSCALE, "version_id": take.id}
        if self.where_of(ctx.model_key) == "api":  # Regenerate-2K: 「用 API 出终版」
            draft = await self._final(ctx, inputs, take)
            draft.params[FINISH] = finish
            draft.dependencies = await self._kept_deps(take)
            return draft

        video = take_video(take)
        assert video is not None
        store = self.services.store
        source = store.path_for(str(video["sha256"])).read_bytes()
        size = self.target(inputs)
        fps = int(float(inputs.context["frame"]["fps"]))
        duration = float(video.get("duration_s") or inputs.context["seconds"])

        async def flow(model: str, reason: str | None) -> MediaCall:
            req = ModelRequest(
                kind="upscale",
                prompt="",
                seed=ctx.seed,
                params={
                    "video_in": str(video["sha256"]),
                    "width": size.w,
                    "height": size.h,
                    "fps": fps,
                    "duration_s": duration,
                },
                meta={"component": self.id, "task": UPSCALE},
            )
            return await self.media_call(
                ctx, req, inputs.episode_id, model=model, fallback=False, fallback_reason=reason
            )

        call, reason = await self.run_flow(ctx, flow)
        out = next((f for f in call.files if f.mime.startswith("video/")), None)
        if out is None:
            raise ComponentError("no_video")
        try:
            clip = await with_sound_of(store.path_for(out.sha256).read_bytes(), source)
        except VideoError as exc:
            raise ComponentError(exc.code) from exc
        files, info = await clip_files(store, store.put_bytes(clip), raw=False, head=0.0)
        payload = {
            **take.payload_json,
            "duration_s": round(info.duration_s, 3),
            "resolution": inputs.context["frame"]["delivery"],
        }
        for key in ("prompt_ir", "check", "sheet_times"):
            payload.pop(key, None)
        files = await self._sheet(files, payload)
        inputs.deps = await self._kept_deps(take)
        draft = self.media_draft(
            ctx, inputs, payload, files, [call], "", stage="final", fallback_reason=reason,
            params={"call_id": call.call_id, FINISH: finish},
        )  # fmt: skip
        draft.seed = ctx.seed
        return draft

    def estimate(self, inputs: Inputs, compiled: str, model: str) -> Estimate:
        """The model's price and time for the shot's length (Regenerate-2K bills the seconds
        sent; SeedVR2's time is ``caps.est_seconds_per_s`` × length), and QA's look at it."""
        size = self.target(inputs)
        frame_ = inputs.context["frame"]
        req = ModelRequest(
            kind="upscale",
            prompt=compiled,
            params={
                "duration_s": float(inputs.context["seconds"]),
                "width": size.w,
                "height": size.h,
                "fps": int(float(frame_["fps"])),
                "first_frame": "-",
            },
        )
        est = self.services.registry.get(model).estimate(req)
        asks = {**take_asks(inputs.context), "times": []}
        check = takecheck.estimate(self.services, self._route_model(takecheck.TAKECHECK), asks)
        parts = [est, *([check] if check is not None else [])]
        return Estimate(
            cost_usd=sum(e.cost_usd for e in parts),
            seconds=sum(e.seconds for e in parts),
            priced=all(e.priced for e in parts),
        )
