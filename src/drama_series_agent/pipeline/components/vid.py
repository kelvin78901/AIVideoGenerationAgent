"""视频生成 (SPEC 5 ``vid``, M5): a shot's takes. Every shot has one video product (owner
``shot``, slot ``video``); each take is a version (一次出 ``candidates`` 条 = that many versions
in one job, seeds ``seed``, ``seed + 1`` …), nothing is adopted until the user picks one.

- **Only after 分镜确认** (409 ``storyboard_not_confirmed``).
- **The first frame**: the shot's locked keyframe (409 ``keyframe_not_locked``); a continuous
  shot starts from the last frame of the take adopted for the shot it continues (409
  ``upstream_not_adopted``).
- **References**: the shot's locked pictures as 关键帧 sends them, as many as the model takes.
- **Sound by ``audio_mode``** (Kelvin 2026-10-26): ``tts`` (先配音再对口型) sends the shot's dubbed
  lines as one track (``dialogue_audio``; every spoken line needs its adopted audio, 409
  ``line_audio_missing``); ``native`` (原生同步) sends the speakers' locked voice samples as
  timbre references (``ref_audio``, S1, S2 … in speaking order) and goes to a local model
  whose workflow takes them (``h3-r2v``, ``model_for``); ``none`` asks for no sound.
- **Length** is the shot's (``pipeline/timing.py``); the adapter fits it to its model's range.
- **The prompt**: the compiled layer is the description; for H3 it goes into H3's own layout
  (``templates/vid/h3_i2v.j2``, ``h3_r2v.j2``: the first-frame line or the six reference
  sections, ``(S1) says: <d>[Chinese] …</d>``, no score); other models get it with the data
  blocks. **A local H3 take is rewritten first** into MiniMax's official layout (English, beat by
  beat, references as ``<Subject N>``; ``prompts/h3_format.py``) by the writing model of the
  ``vprompt`` route, checked, asked again once with what is wrong, and not made when it still
  does not conform (``prompt_not_conformant``; M5 step 14b). The H3 API rewrites with its own
  Context-IR instead.
- **Every take loses its first 0.3 s** (H3's garbled opening sound, SPEC 5.1) and keeps a poster
  (its first frame) and its last frame (the next continuous shot starts there).

The version depends on the shot's settings (the plan's ``shot:<id>`` slice), the lines it films,
the first frame (the keyframe, or the continued shot's take), the dubbed lines it sends and the
voices and pictures it sent.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from typing import Any

from loguru import logger
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from drama_series_agent.core.config import Resolved, get_config
from drama_series_agent.core.models_db import (
    Episode,
    LlmCache,
    OutputSpecRow,
    Product,
    ProductVersion,
    ScriptLine,
    Shot,
)
from drama_series_agent.core.storage import BlobStore
from drama_series_agent.episodes.service import gate_confirmed, script_product
from drama_series_agent.media.audio import dialogue_track
from drama_series_agent.media.video import VideoError, VideoInfo, frame, probe, trim_head
from drama_series_agent.modelhub.adapters.base import Estimate, ModelError, ModelRequest
from drama_series_agent.modelhub.adapters.mock import Responder
from drama_series_agent.modelhub.router import BudgetExceeded, NeedsConfirm
from drama_series_agent.pipeline.component import ComponentError, Inputs, RunContext
from drama_series_agent.pipeline.components.dub import LINE_AUDIO_SLOT, voice_of
from drama_series_agent.pipeline.components.kf import (
    FRAMING,
    MOVE,
    _references,
    blocking_text,
    local_workflow,
    pick_refs,
    ref_limit,
)
from drama_series_agent.pipeline.components.media import (
    MediaCall,
    MediaComponent,
    frame_size,
    locked_ref,
    output_frame,
    prompt_text,
)
from drama_series_agent.pipeline.components.plan import plan_product, shot_slice
from drama_series_agent.pipeline.drafts import DependencyDraft, VersionDraft, file_entry
from drama_series_agent.pipeline.errors import PipelineError
from drama_series_agent.pipeline.generate import load_rules
from drama_series_agent.pipeline.hashing import canonical_json
from drama_series_agent.pipeline.invalidation import Invalidation
from drama_series_agent.pipeline.runs import item_of
from drama_series_agent.pipeline.timing import PRE_ROLL_S, line_seconds, shot_duration
from drama_series_agent.prompts import h3_format
from drama_series_agent.prompts.compiler import Block
from drama_series_agent.script import ops as script_ops
from drama_series_agent.shots import ops
from drama_series_agent.shots.service import KEYFRAME_SLOT, STORYBOARD_GATE, VIDEO_SLOT
from drama_series_agent.spec.dims import dims

LANGUAGE = {"zh-CN": "Chinese", "en": "English"}
DEFAULT_SOUND = "Natural ambient sound of the scene, matching what is on screen."
VPROMPT = "vprompt"  # the route of the H3 prompt rewrite (config/components.yaml)
REWRITE_TRIES = 2
FIX_PROMPT = (
    "This does not follow the official H3 layout yet. Fix every point and answer with the "
    "whole prompt again, nothing else:"
)


def shot_label(episode: Episode | None, shots: list[dict[str, Any]], shot_id: str) -> str:
    n = next((i for i, s in enumerate(shots, 1) if s["id"] == shot_id), 0)
    return f"{episode.idx if episode is not None else 0}-{n:02d}"


async def _shot_product(session: AsyncSession, shot_id: str, slot: str) -> Product | None:
    rows = await session.exec(
        select(Product).where(
            Product.owner_type == "shot", Product.owner_id == shot_id, Product.slot == slot
        )
    )
    return rows.first()


async def _line_audio(
    session: AsyncSession, line_ids: list[str]
) -> dict[str, tuple[Product, dict[str, Any]]]:
    """Each dubbed line's product and the audio file of its adopted take."""
    products = (
        await session.exec(
            select(Product).where(
                Product.owner_type == "line",
                col(Product.owner_id).in_(line_ids),
                Product.slot == LINE_AUDIO_SLOT,
                col(Product.adopted_version_id).is_not(None),
            )
        )
    ).all()
    out: dict[str, tuple[Product, dict[str, Any]]] = {}
    for p in products:
        v = await session.get(ProductVersion, p.adopted_version_id)
        f = next((f for f in v.files_json if f.get("role") == "audio"), None) if v else None
        if f is not None:
            out[p.owner_id] = (p, f)
    return out


async def gather(session: AsyncSession, invalidation: Invalidation, product: Product) -> Inputs:
    """What a shot's takes are made from, and the slices that were read."""
    row = await session.get(Shot, product.owner_id)
    plan = await plan_product(session, row.episode_id) if row is not None else None
    adopted = (
        await session.get(ProductVersion, plan.adopted_version_id)
        if plan is not None and plan.adopted_version_id
        else None
    )
    shot = ops.find_shot(adopted.payload_json, product.owner_id) if adopted else None
    if row is None or plan is None or adopted is None or shot is None or product.retired:
        raise PipelineError(404, "shot_not_found", id=product.owner_id)
    episode_id = row.episode_id
    if not await gate_confirmed(session, STORYBOARD_GATE, episode_id):
        raise PipelineError(409, "storyboard_not_confirmed", id=episode_id)
    episode = await session.get(Episode, episode_id)
    shots = ops.shots_of(adopted.payload_json)
    deps = [await invalidation.dependency(session, plan.id, shot_slice(row.id))]

    # The first frame.
    if shot["shot_type"] == "continuous" and shot.get("tail_from"):
        upstream = await _shot_product(session, str(shot["tail_from"]), VIDEO_SLOT)
        take = (
            await session.get(ProductVersion, upstream.adopted_version_id)
            if upstream is not None and upstream.adopted_version_id
            else None
        )
        last = _file(take, "last_frame")
        if upstream is None or last is None:
            label = shot_label(episode, shots, str(shot["tail_from"]))
            raise PipelineError(409, "upstream_not_adopted", id=label)
        deps.append(await invalidation.dependency(session, upstream.id))
        first = str(last["sha256"])
        first_desc = ""
    else:
        keyframe = await _shot_product(session, row.id, KEYFRAME_SLOT)
        ref = await locked_ref(session, keyframe) if keyframe is not None else None
        if keyframe is None or ref is None:
            raise PipelineError(409, "keyframe_not_locked", id=shot_label(episode, shots, row.id))
        deps.append(await invalidation.dependency(session, keyframe.id))
        first = str(ref["sha256"])
        first_desc = str((keyframe.prompt_json or {}).get("intent") or "")

    # The lines it films, in script order.
    script = await script_product(session, episode_id)
    written = (
        await session.get(ProductVersion, script.adopted_version_id)
        if script is not None and script.adopted_version_id
        else None
    )
    scene = script_ops.find_scene(written.payload_json, shot["scene_id"]) if written else None
    ids = [str(x) for x in shot.get("line_ids") or []]
    rows = {
        x.id: x
        for x in (await session.exec(select(ScriptLine).where(col(ScriptLine.id).in_(ids)))).all()
    }
    lines = [rows[i] for i in ids if i in rows and not rows[i].retired]
    if script is not None:
        for x in lines:
            deps.append(await invalidation.dependency(session, script.id, f"line:{x.id}"))
    spoken = [x for x in lines if x.type in ops.SPEAKING]
    action = [x for x in lines if x.type not in ops.SPEAKING]

    # Who speaks: S1, S2 … in speaking order.
    speakers: dict[str, int] = {}
    for x in spoken:
        speakers.setdefault(x.character_id or x.character_name or x.id, len(speakers) + 1)

    audio = await _line_audio(session, [x.id for x in spoken])
    mode = str(shot.get("audio_mode") or "native")
    dub: list[dict[str, Any]] = []
    if mode == "tts" and spoken:
        missing = [x for x in spoken if x.id not in audio]
        if missing:
            raise PipelineError(409, "line_audio_missing", count=len(missing))
        for x in spoken:
            p, f = audio[x.id]
            deps.append(await invalidation.dependency(session, p.id))
            dub.append({"sha256": f["sha256"]})
    voices: list[dict[str, Any]] = []
    if mode == "native":
        seen: set[str] = set()
        for x in spoken:
            key = x.character_id or x.character_name or x.id
            found = await voice_of(session, x)
            if key in seen or found is None:
                continue
            asset, voice = found
            v = (
                await session.get(ProductVersion, voice.adopted_version_id)
                if voice.locked_hash and voice.adopted_version_id
                else None
            )
            anchor = _file(v, "anchor")
            if anchor is None:
                continue
            seen.add(key)
            h = await invalidation.current_hash(session, voice.id)
            voices.append(
                {
                    "sx": speakers[key],
                    "who": x.character_name or asset.name,
                    "sha256": anchor["sha256"],
                    "product_id": voice.id,
                    "hash": h,
                }
            )

    dialogue = [
        {
            "sx": speakers[x.character_id or x.character_name or x.id],
            "who": x.character_name or "",
            "text": x.text,
            "vo": x.type == "vo",
        }
        for x in spoken
    ]

    def secs(kind: str) -> list[float]:
        return [
            line_seconds(x.text, x.duration_s, _secs(audio, x.id)) for x in spoken if x.type == kind
        ]

    seconds = shot_duration(
        secs("dialogue"),
        secs("vo"),
        shot.get("duration_s"),
        shot.get("manual_s"),
    ).seconds

    refs, unlocked, texts = await _references(session, invalidation, shot.get("asset_ids") or [])
    frame_ = await output_frame(session, product.series_id)
    spec = await session.get(OutputSpecRow, product.series_id)
    frame_["fps"] = str(spec.fps if spec is not None else get_config().spec.defaults.get("fps", 24))
    framing = FRAMING.get(shot["framing"], shot["framing"])
    move = MOVE.get(shot["camera_move"], shot["camera_move"])
    look: list[str] = [f"{framing}，{move}"]
    if scene is not None and scene.get("heading"):
        look.append(str(scene["heading"]))
    if shot.get("blocking"):
        named = {r["name"] for r in refs} | set(unlocked) | {t["name"] for t in texts}
        in_shot = set(shot.get("asset_ids") or []) | named
        look.append(blocking_text(list(shot["blocking"]), in_shot))
    look += [str(x.text) for x in action]
    blocks = [Block("画幅", f"{frame_['aspect']}，{seconds:g} 秒"), Block("镜头", "；".join(look))]
    if dialogue:
        blocks.append(
            Block("台词", "\n".join(f"S{d['sx']} {d['who']}：{d['text']}" for d in dialogue))
        )
    sound = shot.get("sound")
    if sound:
        blocks.append(Block("声音", str(sound)))
    return Inputs(
        blocks=blocks,
        deps=deps,
        episode_id=episode_id,
        context={
            "frame": frame_,
            "first_frame": first,
            "first_desc": first_desc,
            "refs": refs,
            "unlocked": unlocked,
            "texts": texts,
            "audio_mode": mode,
            "dialogue": dialogue,
            "dub": dub,
            "voices": voices,
            "seconds": seconds,
            "look": look,
            "sound": sound,
        },
    )


def _file(version: ProductVersion | None, role: str) -> dict[str, Any] | None:
    if version is None:
        return None
    return next((f for f in version.files_json if f.get("role") == role), None)


def _secs(audio: dict[str, tuple[Product, dict[str, Any]]], line_id: str) -> float | None:
    found = audio.get(line_id)
    d = found[1].get("duration_s") if found else None
    return float(d) if isinstance(d, int | float) else None


def _strip_fences(text: str) -> str:
    """The prompt without a Markdown fence a model may wrap it in."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else ""
        t = t.rsplit("```", 1)[0]
    return t.strip()


def _mock_rewrite(req: ModelRequest) -> str:
    """Mock mode: a prompt that passes the official-layout check, built from the facts."""
    facts = json.loads(str((req.messages or [{}])[1].get("content") or "{}"))
    return h3_format.mock_prompt(h3_format.Facts.from_json(facts))


def is_h3(model: str) -> bool:
    return "h3" in model.split("/", 1)[-1]


def _sent(params: dict[str, Any]) -> dict[str, Any]:
    """A take's request as a final resends it (the pictures and audio by sha256)."""
    return {k: v for k, v in params.items() if k not in ("n", "task", "width", "height")}


async def clip_files(
    store: BlobStore, sha256: str, *, raw: bool
) -> tuple[list[dict[str, Any]], VideoInfo]:
    """A take as stored: the head cut off, its poster and last frame; a local draft keeps the
    untrimmed clip too (``raw``: what Regenerate-2K takes). The demo seed makes its takes so."""
    try:
        original = store.path_for(sha256).read_bytes()
        clip = await trim_head(original)
        info = await probe(clip)
        poster, last = await frame(clip, "first"), await frame(clip, "last")
        whole = await probe(original) if raw else None
    except VideoError as exc:
        raise ComponentError(exc.code) from exc
    files = [
        file_entry(
            "video",
            store.put_bytes(clip),
            "video/mp4",
            w=info.w,
            h=info.h,
            duration_s=round(info.duration_s, 3),
        ),
        file_entry("poster", store.put_bytes(poster), "image/png", w=info.w, h=info.h),
        file_entry("last_frame", store.put_bytes(last), "image/png", w=info.w, h=info.h),
    ]
    if whole is not None:
        files.append(
            file_entry(
                "raw",
                sha256,
                "video/mp4",
                w=whole.w,
                h=whole.h,
                duration_s=round(whole.duration_s, 3),
            )
        )
    return files, info


@dataclass
class Take:
    req: ModelRequest
    calls: list[MediaCall]
    refs: list[dict[str, Any]]
    deps: list[DependencyDraft]
    voices: list[dict[str, Any]]
    rewritten: str | None
    rewrite: str | None = None  # the writing model that put the prompt in the official layout


class VidComponent(MediaComponent):
    id = "vid"
    slot = VIDEO_SLOT
    owner_type = "shot"
    auto_adopt = False

    async def default_intent(self, session: AsyncSession, product: Product, lang: str) -> str:
        """The keyframe's description (the user's words there), else the plan's."""
        keyframe = await _shot_product(session, product.owner_id, KEYFRAME_SLOT)
        intent = ((keyframe.prompt_json if keyframe else None) or {}).get("intent")
        if intent:
            return str(intent)
        shot = await session.get(Shot, product.owner_id)
        return shot.intent if shot is not None else ""

    async def inputs(self, session: AsyncSession, product: Product) -> Inputs:
        return await gather(session, self.services.invalidation, product)

    async def run_count(self, session: AsyncSession, product: Product) -> int:
        """The first run makes the series' ``takes_per_shot`` (``candidates``, 2, unless the
        generate rules say otherwise); 「再出一条」 one."""
        if product.current_version_id is not None:
            return 1
        return (await load_rules(session, product.series_id)).takes_per_shot

    def model_for(self, inputs: Inputs, model: str, settings: Resolved) -> str:
        """「用 API 出终版」 goes to ``final_api`` (H3 Regenerate-2K). A 原生同步 shot with voice
        samples goes to a local model whose workflow takes them (``h3-r2v``); the others stay
        where the route put them."""
        if inputs.params.get("source_version_id"):
            return self._final_model() or model
        if inputs.context.get("audio_mode") != "native" or not inputs.context.get("voices"):
            return model
        wf = local_workflow(self.services.registry, model)
        if wf is None or wf.has("ref_audio"):
            return model
        try:
            local = get_config().components.component(self.id).local
        except KeyError:
            return model
        for other in local:
            alt = local_workflow(self.services.registry, other)
            if other not in settings.unavailable and alt is not None and alt.has("ref_audio"):
                return other
        return model

    # ------------------------------------------------------------------ run

    def mock_responders(self) -> dict[str, Responder]:
        return {
            "context_ir": lambda req: {"prompt": f"[Context-IR] {req.prompt or ''}"},
            "h3_prompt": _mock_rewrite,
        }

    async def run(self, ctx: RunContext, inputs: Inputs) -> VersionDraft:
        source = await self._source_take(ctx.product, inputs.params)
        if source is not None:
            return await self._final(ctx, inputs, source)

        async def flow(model: str, reason: str | None) -> Take:
            return await self._take(ctx, inputs, model, reason)

        # A local take that fails or times out is made again on the fallback (the H3 API), its
        # request built for that model (SPEC 7.3).
        take, reason = await self.run_flow(ctx, flow)
        call = take.calls[-1]
        files, info = await self._clip_files(call, raw=call.where == "local")
        frame_ = inputs.context["frame"]
        payload: dict[str, Any] = {
            "duration_s": round(info.duration_s, 3),
            "asked_s": inputs.context["seconds"],
            "resolution": "768p" if call.where == "local" else frame_["delivery"],
            "aspect": frame_["aspect"],
            "audio_mode": inputs.context["audio_mode"],
            "refs": [r["name"] for r in take.refs],
            "voices": [v["who"] for v in take.voices],
        }
        if take.rewritten is not None:
            payload["prompt_ir"] = bool(take.rewritten)
        if take.rewrite is not None:
            payload["prompt_rewrite"] = take.rewrite
        stage = "draft" if call.where == "local" else None
        draft = self.media_draft(
            ctx,
            inputs,
            payload,
            files,
            take.calls,
            take.req.prompt or "",
            stage=stage,
            fallback_reason=reason,
            # What 「用 API 出终版」 resends (Regenerate-2K takes the draft's own inputs).
            params={"request": _sent(take.req.params)},
        )
        draft.dependencies = [*draft.dependencies, *take.deps]
        return draft

    async def _take(self, ctx: RunContext, inputs: Inputs, model: str, reason: str | None) -> Take:
        req, refs, deps, voices, r2v = await self._request(inputs, ctx.compiled, model, ctx)
        calls: list[MediaCall] = []
        rewrite: str | None = None
        if self._rewrites(model):
            facts = self._facts(inputs, req, refs, voices, r2v, ctx.lang)
            prompt, rewrite_call = await self._rewrite(ctx, inputs, facts)
            calls.append(rewrite_call)
            rewrite = rewrite_call.model_key
            req = req.model_copy(update={"prompt": prompt})
        rewritten, ir_call = await self._context_ir(ctx, inputs, req, model)
        if ir_call is not None:
            calls.append(ir_call)
        if rewritten:
            req = req.model_copy(update={"prompt": rewritten})
        call = await self.media_call(
            ctx, req, inputs.episode_id, model=model, fallback=False, fallback_reason=reason
        )
        calls.append(call)
        return Take(req, calls, refs, deps, voices, rewritten, rewrite)

    async def _final(self, ctx: RunContext, inputs: Inputs, source: ProductVersion) -> VersionDraft:
        """「用 API 出终版」: the picked local H3 draft regenerated at 2K (Regenerate-2K) from its
        own inputs and the prompt it was made with, the untrimmed clip as ``video_in``; trimmed
        like a take. No fallback: a failed final leaves the draft as it is."""
        raw = next((f for f in source.files_json if f.get("role") == "raw"), None)
        sent = (source.params_json or {}).get("request")
        prompt_file = next((f for f in source.files_json if f.get("role") == "prompt"), None)
        if (
            source.where != "local"
            or not is_h3(source.model_key or "")
            or raw is None
            or not sent
            or prompt_file is None
        ):
            raise ComponentError("draft_not_regenerable", id=source.id)
        store = self.services.store
        prompt = store.path_for(prompt_file["sha256"]).read_text(encoding="utf-8")
        frame_ = inputs.context["frame"]
        size = dims(frame_["aspect"], "2k")
        req = ModelRequest(
            kind="upscale",
            prompt=prompt,
            seed=source.seed,
            params={
                **sent,
                "width": size.w,
                "height": size.h,
                "duration_s": raw.get("duration_s") or sent.get("duration_s"),
                "video_in": raw["sha256"],
            },
            meta={"component": self.id, "task": "final"},
        )
        call = await self.media_call(
            ctx, req, inputs.episode_id, model=ctx.model_key, fallback=False
        )
        files, info = await self._clip_files(call, raw=False)
        payload = {
            **source.payload_json,
            "duration_s": round(info.duration_s, 3),
            "resolution": "2k",
        }
        payload.pop("prompt_ir", None)
        draft = self.media_draft(ctx, inputs, payload, files, [call], prompt, stage="final")
        draft.params["source"] = {"version_id": source.id}
        return draft

    async def _clip_files(
        self, call: MediaCall, *, raw: bool
    ) -> tuple[list[dict[str, Any]], VideoInfo]:
        video = next((f for f in call.files if f.mime.startswith("video/")), None)
        if video is None:
            raise ComponentError("no_video")
        return await clip_files(self.services.store, video.sha256, raw=raw)

    async def _source_take(self, product: Product, params: dict[str, Any]) -> ProductVersion | None:
        """The take an API final starts from (``params.source_version_id``)."""
        version_id = params.get("source_version_id")
        if not version_id:
            return None
        async with self.services.db.session() as session:
            v = await session.get(ProductVersion, str(version_id))
        if v is None or v.product_id != product.id:
            raise ComponentError("version_not_found", id=version_id)
        return v

    def _final_model(self) -> str | None:
        try:
            return get_config().components.component(self.id).final_api
        except KeyError:
            return None

    def estimate(self, inputs: Inputs, compiled: str, model: str) -> Estimate:
        frame_ = inputs.context["frame"]
        final = self._final_model() if inputs.params.get("source_version_id") else None
        if final is not None:  # 「用 API 出终版」: Regenerate-2K of the take's length
            req = ModelRequest(
                kind="upscale",
                prompt=compiled,
                params={"duration_s": inputs.context["seconds"], "first_frame": "-"},
            )
            return self.services.registry.get(final).estimate(req)
        size = frame_size(frame_, self.where_of(model))
        req = ModelRequest(
            kind="video",
            prompt=compiled,
            params={
                "n": 1,
                "width": size.w,
                "height": size.h,
                "aspect": frame_["aspect"],
                "duration_s": inputs.context["seconds"],
                "fps": int(frame_["fps"]),
            },
        )
        estimate = self.services.registry.get(model).estimate(req)
        ir = self._ir_model(model)
        if ir is not None:
            ask = ModelRequest(kind="llm_aux", prompt=compiled, params=req.params)
        elif self._rewrites(model) and (ir := self._rewrite_model()) is not None:
            # Priced as if asked twice (the second try carries the first answer and the fixes).
            system = self.services.compiler.render("vid/h3_rewrite_system.j2")
            ask = ModelRequest(
                kind="llm", prompt=f"{system}\n{compiled}\n{compiled}", max_tokens=6000
            )
        else:
            return estimate
        rewrite = self.services.registry.get(ir).estimate(ask)
        return Estimate(
            cost_usd=estimate.cost_usd + rewrite.cost_usd,
            seconds=estimate.seconds + rewrite.seconds,
            priced=estimate.priced and rewrite.priced,
        )

    # ------------------------------------------------------------------ internals

    def _ir_model(self, model: str) -> str | None:
        """The prompt rewriter an API model asks for (``caps.prompt_ir``: H3's Context-IR)."""
        spec = self.services.registry.spec(model)
        ir = (spec.caps.model_extra or {}).get("prompt_ir") if spec.where == "api" else None
        return str(ir) if ir else None

    async def _context_ir(
        self, ctx: RunContext, inputs: Inputs, req: ModelRequest, model: str
    ) -> tuple[str | None, MediaCall | None]:
        """H3 API runs: the official rewriter turns our layout (Chinese description in H3's
        fields) into the English prompt its guide asks for, seeing the same pictures and audio.
        None when the model has no rewriter; "" when it failed (the run goes on with ours)."""
        ir = self._ir_model(model)
        if ir is None:
            return None, None
        ask = ModelRequest(
            kind="llm_aux",
            prompt=req.prompt,
            json_mode=True,
            params={k: v for k, v in req.params.items() if k not in ("n", "task")},
            meta={"component": self.id, "task": "context_ir"},
        )
        try:
            call = await self.media_call(ctx, ask, inputs.episode_id, model=ir, fallback=False)
        except (BudgetExceeded, NeedsConfirm):
            raise
        except ModelError as exc:
            logger.warning("Context-IR failed ({}); the take uses our prompt", exc.code)
            return "", None
        return str((call.data or {}).get("prompt") or "").strip(), call

    def _rewrite_model(self) -> str | None:
        """The ``vprompt`` route's default writing model (for estimates, which cannot read the
        series' own route)."""
        try:
            route = get_config().components.component(VPROMPT).balanced
        except KeyError:
            return None
        key = route.local if route.mode == "local" else route.api
        known = {s.key for s in self.services.registry.specs()}
        return key if key in known else None

    def _rewrites(self, model: str) -> bool:
        """A local H3 take is rewritten into the official layout (the API has Context-IR)."""
        return is_h3(model) and self.where_of(model) == "local"

    def _facts(
        self,
        inputs: Inputs,
        req: ModelRequest,
        refs: list[dict[str, Any]],
        voices: list[dict[str, Any]],
        r2v: bool,
        lang: str,
    ) -> h3_format.Facts:
        """What the rewriter is told: the take's layout, what is sent and the lines it speaks."""
        context = inputs.context
        language = LANGUAGE.get(lang, "Chinese")
        pictures = [h3_format.Picture("first_frame", description=context.get("first_desc", ""))]
        if r2v:
            pictures += [
                h3_format.Picture("reference", r["name"], r["kind"], r.get("desc", ""))
                for r in refs
            ]
        audios = [h3_format.Audio("voice", f"S{v['sx']}", v["who"]) for v in voices] if r2v else []
        if r2v and context["dub"]:
            audios.append(h3_format.Audio("dialogue_track"))
        audio_of = {v["sx"]: i for i, v in enumerate(voices, 1)} if r2v else {}
        lines = (
            []
            if context["audio_mode"] == "none"
            else [
                h3_format.Line(
                    f"S{d['sx']}", d["who"], d["text"], language, d["vo"], audio_of.get(d["sx"])
                )
                for d in context["dialogue"]
            ]
        )
        return h3_format.Facts(
            mode="ref2va" if r2v else "i2va",
            duration_s=float(context["seconds"]),
            aspect=str(context["frame"]["aspect"]),
            draft=req.prompt or "",
            pictures=pictures,
            audios=audios,
            dialogue=lines,
            sound="N/A" if context["audio_mode"] == "none" else str(context.get("sound") or ""),
        )

    def _rewrite_request(self, messages: list[dict[str, Any]]) -> ModelRequest:
        return ModelRequest(
            kind="llm",
            messages=messages,
            max_tokens=3000,
            meta={"component": self.id, "task": "h3_prompt"},
        )

    def _rewrite_messages(self, facts: h3_format.Facts) -> list[dict[str, Any]]:
        system = self.services.compiler.render("vid/h3_rewrite_system.j2")
        user = json.dumps(facts.as_json(), ensure_ascii=False, indent=1)
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]

    async def _rewrite(
        self, ctx: RunContext, inputs: Inputs, facts: h3_format.Facts
    ) -> tuple[str, MediaCall]:
        """The take's prompt in MiniMax's official layout, from the ``vprompt`` route's writing
        model: checked, asked again once with what is wrong; cached by request, so the takes of
        one run (other seeds) share it. Raises ``prompt_not_conformant`` when it never fits."""
        router = self.services.router
        settings = await router.settings(VPROMPT, item_of(ctx.product))
        model = router.primary_model(settings)
        messages = self._rewrite_messages(facts)
        key = (
            "h3_prompt:"
            + hashlib.sha256(
                canonical_json({"model": model, "messages": messages}).encode("utf-8")
            ).hexdigest()
        )
        async with self.services.db.session() as session:
            row = await session.get(LlmCache, key)
        if row is not None:
            where = self.services.registry.spec(row.model_key).where
            return str(row.value_json["prompt"]), MediaCall(
                [], row.model_key, where, 0.0, cached=True
            )
        call_ctx = replace(self._call_ctx(ctx, inputs.episode_id), component_id=VPROMPT)
        cost = 0.0
        problems: list[str] = []
        text = ""
        for _ in range(REWRITE_TRIES):
            routed = await router.call(
                VPROMPT, self._rewrite_request(messages), call_ctx, model=model
            )
            cost += routed.cost_usd
            model = routed.model_key  # asked again on the model that answered
            text = _strip_fences(routed.text or "")
            problems = h3_format.check(text, facts)
            if not problems:
                async with self.services.db.session() as session:
                    if await session.get(LlmCache, key) is None:
                        session.add(LlmCache(key=key, model_key=model, value_json={"prompt": text}))
                        await session.commit()
                return text, MediaCall([], model, routed.where, cost)
            messages = [
                *messages,
                {"role": "assistant", "content": text},
                {
                    "role": "user",
                    "content": FIX_PROMPT + "".join(f"\n- {p}" for p in problems),
                },
            ]
        raw = self.services.store.put_bytes(text.encode("utf-8"))
        raise ComponentError("prompt_not_conformant", raw=raw, errors="; ".join(problems)[:500])

    async def _request(
        self, inputs: Inputs, compiled: str, model: str, ctx: RunContext
    ) -> tuple[
        ModelRequest, list[dict[str, Any]], list[DependencyDraft], list[dict[str, Any]], bool
    ]:
        """The take's request, the pictures and voices it sends, what they make it depend on,
        and whether it is H3's reference-to-video layout."""
        context = inputs.context
        spec = self.services.registry.spec(model)
        wf = local_workflow(self.services.registry, model)
        extra = spec.caps.model_extra or {}
        api_h3 = spec.where == "api" and is_h3(model)
        if api_h3:
            # H3 API: audio goes in reference mode only (first frames and references do not
            # mix), so voices or the dubbed lines make it reference-to-video, the first frame
            # <Picture 1>; without audio it is image-to-video and takes no other pictures.
            native = context["audio_mode"] == "native"
            voices = list(context["voices"])[: int(extra.get("max_audios", 3))] if native else []
            r2v = bool(voices or context["dub"])
            limit: int | None = int(extra.get("max_images", 9)) - 1 if r2v else 0
        else:
            r2v = wf is not None and wf.has("ref_audio")
            limit = ref_limit(spec.caps.max_refs, spec.where, spec.workflow)
            if spec.where == "local" and wf is not None and not wf.has("ref_image"):
                limit = 0
            voices = list(context["voices"]) if r2v else []
            voices = voices[: len(wf.bindings("ref_audio"))] if wf is not None and r2v else voices
        refs, deps, blocks = pick_refs(inputs, None, limit)
        deps += [DependencyDraft(v["product_id"], v["hash"], "") for v in voices if v.get("hash")]
        frame_ = context["frame"]
        size = frame_size(frame_, spec.where)
        params: dict[str, Any] = {
            "n": 1,
            "width": size.w,
            "height": size.h,
            "aspect": frame_["aspect"],
            "duration_s": context["seconds"],
            "fps": int(frame_["fps"]),
            "first_frame": context["first_frame"],
            "with_audio": context["audio_mode"] != "none",
            "task": "take",
        }
        if refs:
            params["refs"] = [r["sha256"] for r in refs]
        if voices:
            params["ref_audio"] = [v["sha256"] for v in voices]
        if context["dub"]:
            clips = [self.services.store.path_for(d["sha256"]).read_bytes() for d in context["dub"]]
            track = dialogue_track(clips, float(context["seconds"]), PRE_ROLL_S)
            params["dialogue_audio"] = self.services.store.put_bytes(track)
        prompt = (
            self._h3_prompt(compiled, context, refs, voices, ctx.lang, r2v)
            if is_h3(model)
            else prompt_text(compiled, blocks)
        )
        req = ModelRequest(
            kind="video",
            prompt=prompt,
            seed=ctx.seed,
            params=params,
            meta={"component": self.id, "task": "take"},
        )
        return req, refs, deps, voices, r2v

    def _h3_prompt(
        self,
        compiled: str,
        context: dict[str, Any],
        refs: list[dict[str, Any]],
        voices: list[dict[str, Any]],
        lang: str,
        r2v: bool,
    ) -> str:
        """The compiled layer in H3's layout (I2V's first-frame line, or the six reference
        sections when voice samples go along)."""
        said = [ln.strip() for ln in compiled.splitlines() if ln.strip() and not ln.startswith("#")]
        description = " ".join([*said, *context["look"]])
        audio_of = {v["sx"]: i for i, v in enumerate(voices, 1)}
        dialogue = [{**d, "audio": audio_of.get(d["sx"])} for d in context["dialogue"]]
        none = context["audio_mode"] == "none"
        return self.services.compiler.render(
            "vid/h3_r2v.j2" if r2v else "vid/h3_i2v.j2",
            description=description,
            dialogue=[] if none else dialogue,
            voices=voices,
            dub=r2v and bool(context["dub"]),
            refs=refs,
            language=LANGUAGE.get(lang, "Chinese"),
            soundscape="N/A" if none else (context.get("sound") or DEFAULT_SOUND),
        )
