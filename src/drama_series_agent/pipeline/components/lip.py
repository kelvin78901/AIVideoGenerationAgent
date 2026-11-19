"""口型修复 of a take (M6 step 7a, ``lip``; plan E2): the mouths redrawn to the shot's dubbed
lines, nothing else changed. A new version of the shot's video product (origin ``lipsync``,
parent = the take, the take's stage), checked by QA like every take.

- **What it runs on**: the video product (``RunService.start(component_id="lip")``, as 2K 精修
  runs ``up``), ``params.lip_version_id`` the take (a take, or one finished from it).
- **The sound**: the shot's on-screen lines' adopted dubs one after another
  (``media/audio.py:dialogue_track``), from where they start in the take as stored (the
  take's request put them at ``PRE_ROLL_S``; the stored take lost its head), silence to its
  end. A 原生同步 take gets the dub too (PLAN 模式 C); its own sound is gone. A shot with no
  line said on screen is refused (409 ``lipsync_no_dialogue``), a line not dubbed yet too
  (409 ``line_audio_missing``). The track is laid on the result whatever the model returns.
- **Models**: the route's (API sync lipsync-2-pro; locally LatentSync, step 7b), one
  ``ModelRequest(kind="lipsync")``: ``video_in`` / ``audio_in`` by sha256.
- **Adopted** after QA as 2K 精修 is (``pipeline/qa_policy.py:adopt_finished``); a repair QA
  asked for (``params.auto``: ``auto_lip``) is a candidate the policy judges (``qa_policy.decide``).
- It keeps the take's dependencies and adds the dubs'.
"""

from __future__ import annotations

from typing import ClassVar

from drama_series_agent.core.models_db import ProductVersion
from drama_series_agent.media.audio import dialogue_track
from drama_series_agent.media.video import VideoError, with_track
from drama_series_agent.modelhub.adapters.base import Estimate, ModelRequest
from drama_series_agent.pipeline import takecheck
from drama_series_agent.pipeline.component import ComponentError, Inputs, RunContext
from drama_series_agent.pipeline.components.media import MediaCall
from drama_series_agent.pipeline.components.up import UpComponent, take_video
from drama_series_agent.pipeline.components.vid import clip_files, head_s, take_asks
from drama_series_agent.pipeline.drafts import DependencyDraft, VersionDraft
from drama_series_agent.pipeline.errors import PipelineError
from drama_series_agent.pipeline.qa_policy import FINISH, LIPSYNC, is_finished
from drama_series_agent.pipeline.timing import PRE_ROLL_S


class LipComponent(UpComponent):
    id = "lip"
    slot = "lip"
    origin: ClassVar[str | None] = LIPSYNC

    def _check(self, take: ProductVersion, inputs: Inputs, model: str) -> None:
        if take_video(take) is None:
            raise PipelineError(409, "not_a_take", id=take.id)
        lip = inputs.context.get("lip") or {}
        if int(lip.get("missing") or 0):
            raise PipelineError(409, "line_audio_missing", count=int(lip["missing"]))
        if not lip.get("lines"):
            raise PipelineError(409, "lipsync_no_dialogue", id=take.id)

    async def _made_from(self, take: ProductVersion) -> ProductVersion:
        """The take a finished one (2K, an earlier repair) was made from: its request says
        what the stored clip lost at its head."""
        v = take
        async with self.services.db.session() as session:
            for _ in range(8):
                if not is_finished(v):
                    break
                up = await session.get(ProductVersion, str(v.params_json[FINISH]["version_id"]))
                if up is None:
                    break
                v = up
        return v

    async def run(self, ctx: RunContext, inputs: Inputs) -> VersionDraft:
        take = await self._take_of(ctx.product, inputs.params)
        self._check(take, inputs, ctx.model_key)
        video = take_video(take)
        assert video is not None
        store = self.services.store
        fps = float(inputs.context["frame"]["fps"])
        duration = float(video.get("duration_s") or inputs.context["seconds"])
        first = await self._made_from(take)
        lead = max(0.0, PRE_ROLL_S - head_s((first.params_json or {}).get("request") or {}, fps))
        lines = list(inputs.context["lip"]["lines"])
        clips = [store.path_for(str(x["sha256"])).read_bytes() for x in lines]
        track = dialogue_track(clips, duration, lead)
        audio_in = store.put_bytes(track)

        async def flow(model: str, reason: str | None) -> MediaCall:
            req = ModelRequest(
                kind="lipsync",
                prompt="",
                seed=ctx.seed,
                params={
                    "video_in": str(video["sha256"]),
                    "audio_in": audio_in,
                    "width": int(video.get("w") or 0),
                    "height": int(video.get("h") or 0),
                    "fps": int(fps),
                    "duration_s": duration,
                    "with_audio": True,
                },
                meta={"component": self.id, "task": LIPSYNC},
            )
            return await self.media_call(
                ctx, req, inputs.episode_id, model=model, fallback=False, fallback_reason=reason
            )

        call, reason = await self.run_flow(ctx, flow)
        out = next((f for f in call.files if f.mime.startswith("video/")), None)
        if out is None:
            raise ComponentError("no_video")
        try:
            clip = await with_track(store.path_for(out.sha256).read_bytes(), track)
        except VideoError as exc:
            raise ComponentError(exc.code) from exc
        files, info = await clip_files(store, store.put_bytes(clip), raw=False, head=0.0)
        payload = {
            **take.payload_json,
            "duration_s": round(info.duration_s, 3),
            "lip": {"lines": len(lines), "lead_s": round(lead, 3)},
        }
        for key in ("prompt_ir", "check", "sheet_times"):
            payload.pop(key, None)
        files = await self._sheet(files, payload)
        async with self.services.db.session() as session:
            dubs = [
                await self.services.invalidation.dependency(session, str(x["product_id"]))
                for x in lines
            ]
        kept = await self._kept_deps(take)
        inputs.deps = [*kept, *_new(dubs, kept)]
        finish = {"kind": LIPSYNC, "version_id": take.id}
        draft = self.media_draft(
            ctx, inputs, payload, files, [call], "", stage=take.stage, fallback_reason=reason,
            params={"call_id": call.call_id, FINISH: finish},
        )  # fmt: skip
        draft.seed = ctx.seed
        return draft

    def estimate(self, inputs: Inputs, compiled: str, model: str) -> Estimate:
        """The model's price and time for the shot's length (sync bills the frames made), and
        QA's look at it."""
        frame_ = inputs.context["frame"]
        req = ModelRequest(
            kind="lipsync",
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


def _new(deps: list[DependencyDraft], kept: list[DependencyDraft]) -> list[DependencyDraft]:
    seen = {(d.upstream_product_id, d.slice) for d in kept}
    return [d for d in deps if (d.upstream_product_id, d.slice) not in seen]
