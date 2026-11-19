"""视频局部修复 of a take (M6 step 8b, ``vinpaint``; plan E3): what the user painted over on the
take's first frame taken out of the whole take, the rest of the picture and the sound kept. A
new version of the shot's video product (origin ``inpaint``, parent = the take, the take's
stage), checked by QA like every take.

- **What it is for**: removing something or cleaning up a flaw (Kelvin 2026-11-18, after the
  local check, DECISIONS「M6 第 8a 步」): Wan VACE 14B with CausVid at 4 steps fills the masked
  part from its surroundings well and draws a new thing badly. The instruction is optional
  (what the masked part should show, sent to the model as it is); without one the part is
  filled from what is around it.
- **What it runs on**: the video product (``RunService.start(component_id="vinpaint")``, as
  2K 精修 runs ``up``), ``params.vinpaint_version_id`` the take (or one finished from it),
  ``params.vinpaint_mask`` the mask at the take's size (``media/image.py:mask_for``: grayscale,
  white = change), one mask for every frame. A camera that moves brings other things into it;
  they are drawn again too.
- **Only locally**: Wan VACE 14B (``workflows/vace-inpaint``), at the take's own size (edges
  made multiples of 16) and frame rate, as many frames as the take has; what is outside the
  mask is the take's own picture (the workflow pastes it back), the sound is the take's, put
  back by stream copy. No API model: on a machine that cannot run it the request is refused
  with the reason (``inpaint_unavailable``), and the catalog greys the button out with it.
- **Adopted** after QA as 2K 精修 is (``pipeline/qa_policy.py:adopt_finished``).
- It keeps the take's dependencies.
"""

from __future__ import annotations

from typing import Any, ClassVar

from drama_series_agent.core.capabilities import Capabilities
from drama_series_agent.core.config import StudioConfig
from drama_series_agent.core.models_db import ProductVersion
from drama_series_agent.core.storage import BlobStore
from drama_series_agent.media.image import BadMask, mask_for
from drama_series_agent.media.video import VideoError, frame_count, with_sound_of
from drama_series_agent.modelhub.adapters.base import Estimate, ModelRequest
from drama_series_agent.modelhub.catalog import catalog
from drama_series_agent.pipeline import takecheck
from drama_series_agent.pipeline.component import ComponentError, Inputs, RunContext
from drama_series_agent.pipeline.components.media import MediaCall
from drama_series_agent.pipeline.components.up import UpComponent, take_video
from drama_series_agent.pipeline.components.vid import clip_files, take_asks
from drama_series_agent.pipeline.drafts import VersionDraft
from drama_series_agent.pipeline.errors import PipelineError
from drama_series_agent.pipeline.qa_policy import FINISH

INPAINT = "inpaint"  # its origin and ``finish.kind``, as a picture's 局部修复
MULTIPLE = 16  # Wan's edges


class VinpaintComponent(UpComponent):
    id = "vinpaint"
    slot = "vinpaint"
    origin: ClassVar[str | None] = INPAINT

    def _check(self, take: ProductVersion, inputs: Inputs, model: str) -> None:
        if take_video(take) is None:
            raise PipelineError(409, "not_a_take", id=take.id)

    async def run(self, ctx: RunContext, inputs: Inputs) -> VersionDraft:
        take = await self._take_of(ctx.product, inputs.params)
        self._check(take, inputs, ctx.model_key)
        video = take_video(take)
        assert video is not None
        store = self.services.store
        path = store.path_for(str(video["sha256"]))
        source = path.read_bytes()
        try:
            frames = await frame_count(path)
        except VideoError as exc:
            raise ComponentError(exc.code) from exc
        w, h = int(video.get("w") or 0), int(video.get("h") or 0)
        fps = float(inputs.context["frame"]["fps"])
        duration = float(video.get("duration_s") or inputs.context["seconds"])
        mask = str(inputs.params["vinpaint_mask"])

        async def flow(model: str, reason: str | None) -> MediaCall:
            req = ModelRequest(
                kind="vinpaint",
                prompt=ctx.intent.strip(),
                seed=ctx.seed,
                params={
                    "video_in": str(video["sha256"]),
                    "mask": mask,
                    "width": w // MULTIPLE * MULTIPLE,
                    "height": h // MULTIPLE * MULTIPLE,
                    "frames": frames,
                    "fps": int(fps),
                    "duration_s": duration,
                    "with_audio": True,
                },
                meta={"component": self.id, "task": INPAINT},
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
            "inpaint": {"mask": mask, "share": inputs.params.get("vinpaint_share")},
        }
        for key in ("prompt_ir", "check", "sheet_times"):
            payload.pop(key, None)
        files = await self._sheet(files, payload)
        inputs.deps = await self._kept_deps(take)
        finish = {"kind": INPAINT, "version_id": take.id}
        draft = self.media_draft(
            ctx, inputs, payload, files, [call], ctx.intent.strip(), stage=take.stage,
            fallback_reason=reason, params={"call_id": call.call_id, FINISH: finish},
        )  # fmt: skip
        draft.seed = ctx.seed
        return draft

    def estimate(self, inputs: Inputs, compiled: str, model: str) -> Estimate:
        """The model's time for the shot's length (``caps.est_seconds_per_s``; free locally),
        and QA's look at it."""
        frame_ = inputs.context["frame"]
        req = ModelRequest(
            kind="vinpaint",
            prompt=compiled,
            params={
                "duration_s": float(inputs.context["seconds"]),
                "fps": int(float(frame_["fps"])),
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


async def vinpaint_params(
    store: BlobStore, take: ProductVersion, mask: bytes, version_id: str
) -> dict[str, Any]:
    """The run's params for painting over the take ``take``: the mask at the take's size
    (grayscale, white = change), in the store. 422 ``bad_mask`` (another shape, nothing
    painted), 409 ``not_a_take``."""
    video = take_video(take)
    if video is None:
        raise PipelineError(409, "not_a_take", id=take.id)
    try:
        made = await mask_for(mask, int(video.get("w") or 0), int(video.get("h") or 0))
    except BadMask as exc:
        raise PipelineError(422, "bad_mask", reason=str(exc)) from None
    return {
        "vinpaint_version_id": version_id,
        "vinpaint_mask": store.put_bytes(made.gray),
        "vinpaint_share": round(made.share, 4),
    }


def refuse_if_unavailable(cfg: StudioConfig, caps: Capabilities | None) -> None:
    """409 ``inpaint_unavailable`` with the catalog's reason (``machine_cuda``, or
    ``machine_missing`` with a count) when this machine cannot run it."""
    comp = next((c for c in catalog(cfg, caps).components if c.id == VinpaintComponent.id), None)
    if comp is None or comp.api_models or "local" not in comp.unavailable:
        return
    reason = comp.unavailable["local"]
    raise PipelineError(409, "inpaint_unavailable", reason=reason.code, **reason.params)
