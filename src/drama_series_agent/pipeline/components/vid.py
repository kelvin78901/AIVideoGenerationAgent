"""视频生成 (SPEC 5 ``vid``, M5): a shot's takes. Every shot has one video product (owner
``shot``, slot ``video``); each take is a version (一次出 ``candidates`` 条 = that many versions
in one job, seeds ``seed``, ``seed + 1`` …), nothing is adopted until the user picks one.

- **Only after 分镜确认** (409 ``storyboard_not_confirmed``).
- **The first frame**: the shot's locked keyframe (409 ``keyframe_not_locked``); a continuous
  shot starts from the last frame of the take adopted for the shot it continues (409
  ``upstream_not_adopted``). **A local H3 take of a continuous shot is guided instead** with
  the end of that take's clip, ``TAIL_FRAMES`` frames and their sound at frame 0 (the
  workflow's ``tail_clip``, M5 step 15e: 末尾片段续写, steadier than the last frame alone in
  run9), asked that many frames longer and cut back by them; the API fallback, which takes no
  clip, starts from the last frame as before.
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
- **A take's window** (``payload.window``, M5 step 15i): where the edit should cut it, past
  H3's still opening and keeping a spoken line whole; the take itself is kept whole.
- **Every take loses its first 0.3 s** (H3's garbled opening sound, SPEC 5.1), or the tail
  frames it was guided with, and keeps a poster (its first frame) and its last frame (the next
  continuous shot starts there).

The version depends on the shot's settings (the plan's ``shot:<id>`` slice), the lines it films,
the first frame (the keyframe, or the continued shot's take), the dubbed lines it sends and the
voices and pictures it sent.
"""

from __future__ import annotations

import hashlib
import json
import math
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
from drama_series_agent.media.audio import dialogue_track, joined_sample
from drama_series_agent.media.video import (
    TAIL_AUDIO_FRAMES,
    TAIL_FRAMES,
    TRIM_HEAD_S,
    VideoError,
    VideoInfo,
    contact_sheet,
    frame,
    probe,
    scene_cuts,
    tail_clip,
    trim_head,
    usable_window,
)
from drama_series_agent.modelhub.adapters.base import (
    CallContext,
    Estimate,
    ModelError,
    ModelRequest,
)
from drama_series_agent.modelhub.adapters.mock import Responder
from drama_series_agent.modelhub.router import BudgetExceeded, NeedsConfirm
from drama_series_agent.pipeline import takecheck, vlook, vselect
from drama_series_agent.pipeline.component import (
    ComponentError,
    Inputs,
    ModelChoice,
    RunContext,
)
from drama_series_agent.pipeline.components.dub import LINE_AUDIO_SLOT, voice_of
from drama_series_agent.pipeline.components.kf import (
    FRAMING,
    MOVE,
    PROPS_NOTE,
    _references,
    asset_rows,
    blocking_text,
    in_frame,
    local_workflow,
    pick_refs,
    props_text,
    ref_limit,
    scene_light,
    states_text,
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
from drama_series_agent.shots import contract as contracts
from drama_series_agent.shots import ops
from drama_series_agent.shots.service import (
    KEYFRAME_SLOT,
    STORYBOARD_GATE,
    VIDEO_SLOT,
    own_picture,
    prop_names,
    scene_place,
)
from drama_series_agent.spec.dims import dims

LANGUAGE = {"zh-CN": "Chinese", "en": "English"}
# 镜头契约 (M5.5): the action budget and how an overlaid line is said, in the draft.
BEATS = "最多 {n} 个动作；改变状态的动作（开门、放下东西）只做一次，不撤销再重做，犹豫要演出来"
INSERT_BEATS = "插入镜头：只许微动（光线变化、一滴水、镜头极轻的漂移），东西本身不发生任何事"
OVERLAY_HOW = {"inner": "内心独白", "offscreen": "画外音"}
DEFAULT_SOUND = "Natural ambient sound of the scene, matching what is on screen."
VPROMPT = "vprompt"  # the route of the H3 prompt rewrite (config/components.yaml)
REWRITE_TRIES = 2
FIX_PROMPT = (
    "This does not follow the official H3 layout yet. Fix every point and answer with the "
    "whole prompt again, nothing else:"
)


def take_asks(context: dict[str, Any]) -> dict[str, Any]:
    """What a take is checked for (``templates/vid/take_check.j2``), from its shot."""
    return {
        "kind": context.get("kind") or "performance",
        "beats": int(context.get("beats", 2)),
        "light": context.get("light"),
        "place": context.get("place"),
        "end": list(context.get("end") or []),
        "texts": [t for t in context.get("texts") or [] if t.get("method") == "model"],
        "inner": list(
            dict.fromkeys(
                str(o["who"])
                for o in context.get("overlay") or []
                if o.get("how") == "inner" and o.get("who")
            )
        ),
    }


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
    own = None  # the user's picture description (``own_picture``): then no action lines
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
        # A local H3 take is guided with the end of that take's clip (``_request``): the clip
        # as H3 made it when there is one (step 15m: one lossy pass fewer; the end is the same).
        clip = _file(take, "raw") or _file(take, "video")
        tail = str(clip["sha256"]) if clip is not None else None
    else:
        tail = None
        keyframe = await _shot_product(session, row.id, KEYFRAME_SLOT)
        ref = await locked_ref(session, keyframe) if keyframe is not None else None
        if keyframe is None or ref is None:
            raise PipelineError(409, "keyframe_not_locked", id=shot_label(episode, shots, row.id))
        deps.append(await invalidation.dependency(session, keyframe.id))
        first = str(ref["sha256"])
        # What the keyframe was asked to show; a look at the picture replaces it (``vlook``).
        first_desc = str((keyframe.prompt_json or {}).get("intent") or shot.get("intent") or "")
        own = own_picture(keyframe, shot)

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
    # 镜头契约 (M5.5): a continuous shot without a start of its own starts where the shot it
    # follows ends, so that shot's plan settings are read too.
    assets = await asset_rows(session, list(shot.get("asset_ids") or []))
    contract = contracts.effective(
        shot,
        [contracts.SpokenLine(x.id, n, x.type, x.tone or "") for n, x in enumerate(lines, 1)],
        {a.id: a.kind for a in assets.values()},
        {s["id"]: s for s in shots},
        await prop_names(session, product.series_id),
    )
    # The props the scene puts in the picture too (``props_linked``), and the shots that gave
    # the props their states.
    ids = in_frame(shot, contract)
    assets = await asset_rows(session, ids)
    for source in sorted(set(contract["props_from"].values())):
        deps.append(await invalidation.dependency(session, plan.id, shot_slice(source)))
    if contract["start_inherited"] and shot.get("tail_from"):
        tail_slice = shot_slice(str(shot["tail_from"]))
        deps.append(await invalidation.dependency(session, plan.id, tail_slice))
    # Only a line said on screen is made in the take. An inner voice or an off-screen line is
    # laid over the shot in the edit (M5 step 15p): a voice the take makes sounds said in the
    # room, and with the lips closed it reads as lips out of sync. The take is silent-lipped.
    voiced = [x for x in spoken if contracts.speaks_on_screen(contract, x.id)]
    overlaid = [x for x in spoken if not contracts.speaks_on_screen(contract, x.id)]

    # Who speaks: S1, S2 … in speaking order.
    speakers: dict[str, int] = {}
    for x in voiced:
        speakers.setdefault(x.character_id or x.character_name or x.id, len(speakers) + 1)

    audio = await _line_audio(session, [x.id for x in spoken])
    mode = str(shot.get("audio_mode") or "native")
    dub: list[dict[str, Any]] = []
    if mode == "tts" and voiced:
        missing = [x for x in voiced if x.id not in audio]
        if missing:
            raise PipelineError(409, "line_audio_missing", count=len(missing))
        for x in voiced:
            p, f = audio[x.id]
            deps.append(await invalidation.dependency(session, p.id))
            dub.append({"sha256": f["sha256"]})
    voices: list[dict[str, Any]] = []
    if mode == "native":
        seen: set[str] = set()
        for x in voiced:
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
            if anchor is None or v is None:
                continue
            # The voice's other clips (all in the same voice), for an API that wants a longer
            # sample than the anchor (``_voice_samples``).
            clips = [f for f in v.files_json if f.get("role") == "anchor"]
            clips += [f for f in v.files_json if f.get("role") == "variant"]
            seen.add(key)
            h = await invalidation.current_hash(session, voice.id)
            voices.append(
                {
                    "sx": speakers[key],
                    "who": x.character_name or asset.name,
                    "sha256": anchor["sha256"],
                    "clips": [
                        {"sha256": f["sha256"], "duration_s": f.get("duration_s")} for f in clips
                    ],
                    "product_id": voice.id,
                    "hash": h,
                }
            )

    dialogue = [
        {
            "sx": speakers[x.character_id or x.character_name or x.id],
            "who": x.character_name or "",
            "text": x.text,
            "vo": False,  # said on screen (an inner or off-screen line is not in the take)
        }
        for x in voiced
    ]
    overlay = [
        {
            "line_id": x.id,
            "who": x.character_name or "",
            "text": x.text,
            "how": contract["delivery"].get(x.id, "offscreen"),
            "sha256": audio[x.id][1]["sha256"] if x.id in audio else None,
        }
        for x in overlaid
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

    refs, unlocked, texts = await _references(session, invalidation, ids)
    refs = [r for r in refs if not r.get("scale")]  # 比例参考 is for the keyframe (M5.5)
    frame_ = await output_frame(session, product.series_id)
    spec = await session.get(OutputSpecRow, product.series_id)
    frame_["fps"] = str(spec.fps if spec is not None else get_config().spec.defaults.get("fps", 24))
    framing = FRAMING.get(shot["framing"], shot["framing"])
    move = MOVE.get(shot["camera_move"], shot["camera_move"])
    look: list[str] = [f"{framing}，{move}"]
    if scene is not None and scene.get("heading"):
        look.append(str(scene["heading"]))
    light = scene_light(scene)
    if light:
        look.append(light)
    if shot.get("blocking"):
        named = {r["name"] for r in refs} | set(unlocked) | {t["name"] for t in texts}
        in_shot = set(ids) | named
        look.append(blocking_text(list(shot["blocking"]), in_shot))
    if own is None:  # the script's action lines; a picture the user wrote replaces them
        look += [str(x.text) for x in action]
    blocks = [Block("画幅", f"{frame_['aspect']}，{seconds:g} 秒"), Block("镜头", "；".join(look))]
    if dialogue:
        blocks.append(
            Block("台词", "\n".join(f"S{d['sx']} {d['who']}：{d['text']}" for d in dialogue))
        )
    if overlay:
        blocks.append(
            Block(
                "画外",
                "内心独白 / 画外音，剪辑时另铺，这条片子里没有人说话、嘴闭着：\n"
                + "\n".join(
                    f"{o['who']}（{OVERLAY_HOW.get(o['how'], '画外音')}）：{o['text']}"
                    for o in overlay
                ),
            )
        )
    kind = str(contract["kind"])
    beats = int(contract["beats"])
    blocks.append(Block("动作", INSERT_BEATS if kind == "insert" else BEATS.format(n=beats)))
    if contract["start"]:
        blocks.append(Block("开始时", states_text(contract["start"])))
    if contract["end"]:
        blocks.append(Block("结束时", states_text(contract["end"])))
    if contract["props"] and props_text(contract["props"], assets):
        blocks.append(Block("道具", PROPS_NOTE + props_text(contract["props"], assets)))
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
            "tail_clip": tail,
            # 镜头契约 (M5.5; before it, 15o's 插入镜头: nobody in it and nothing said)
            "kind": kind,
            "light": light,
            "place": scene_place(str(scene["heading"])) if scene and scene.get("heading") else None,
            "beats": beats,
            "start": [f"{i['subject']}：{i['state']}" for i in contract["start"]],
            "end": [f"{i['subject']}：{i['state']}" for i in contract["end"]],
            "props": [x for x in props_text(contract["props"], assets).split("；") if x],
            "overlay": overlay,
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
            "shot": {"shot_type": shot["shot_type"], "framing": shot["framing"]},
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


def _select(ctx: RunContext) -> dict[str, Any]:
    return {"select": ctx.select} if ctx.select is not None else {}


def head_s(params: dict[str, Any], fps: float) -> float:
    """What a take loses at its start: the tail frames it was guided with (``tail_frames``),
    else ``TRIM_HEAD_S``."""
    frames = int(params.get("tail_frames") or 0)
    return round(frames / fps, 4) if frames else TRIM_HEAD_S


async def clip_files(
    store: BlobStore, sha256: str, *, raw: bool, head: float = TRIM_HEAD_S
) -> tuple[list[dict[str, Any]], VideoInfo]:
    """A take as stored: the head cut off (``head`` seconds), its poster and last frame; a local
    draft keeps the untrimmed clip too (``raw``: what Regenerate-2K takes). The demo seed makes
    its takes so."""
    try:
        original = store.path_for(sha256).read_bytes()
        clip = await trim_head(original, head)
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
        """「用 API 出终版」 goes to ``final_api`` (H3 Regenerate-2K)."""
        if inputs.params.get("source_version_id"):
            return self._final_model() or model
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
        """A final goes to ``final_api``; a take to the workflow 按镜头选工作流 picks
        (``pipeline/vselect.py``: the shot's own pick, the series' rules — a 原生同步 shot with
        voice samples goes to ``h3-r2v`` by default — the LLM's suggestion, the route)."""
        if inputs.params.get("source_version_id"):
            return ModelChoice(self.model_for(inputs, model, settings))
        call_ctx = CallContext(
            component_id=vselect.VSELECT,
            series_id=product.series_id,
            episode_id=inputs.episode_id,
            shot_id=product.owner_id,
            product_id=product.id,
        )
        chosen = await vselect.choose(
            self.services, inputs, model, settings, series_id=product.series_id, lang=lang,
            named=named, ask=ask, ctx=call_ctx,
        )  # fmt: skip
        return ModelChoice(chosen.model, chosen.select)

    # ------------------------------------------------------------------ run

    def mock_responders(self) -> dict[str, Responder]:
        return {
            "context_ir": lambda req: {"prompt": f"[Context-IR] {req.prompt or ''}"},
            "h3_prompt": _mock_rewrite,
            "select": vselect.mock_suggest,
            vlook.TASK: vlook.mock_look,
            takecheck.TASK: takecheck.mock_check,
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
        frame_ = inputs.context["frame"]
        head = head_s(take.req.params, float(frame_["fps"]))
        files, info = await self._clip_files(call, raw=call.where == "local", head=head)
        payload: dict[str, Any] = {
            "duration_s": round(info.duration_s, 3),
            "asked_s": inputs.context["seconds"],
            "window": await self._window(files, inputs),
            "cuts": await self._cuts(files),
            "resolution": "768p" if call.where == "local" else frame_["delivery"],
            "aspect": frame_["aspect"],
            "audio_mode": inputs.context["audio_mode"],
            "refs": [r["name"] for r in take.refs],
            "voices": [v["who"] for v in take.voices],
        }
        files = await self._check_take(ctx, inputs, files, payload)
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
            # What 「用 API 出终版」 resends (Regenerate-2K takes the draft's own inputs), and
            # why this workflow (按镜头选工作流; the Inspector shows it).
            params={"request": _sent(take.req.params), **_select(ctx)},
        )
        draft.dependencies = [*draft.dependencies, *take.deps]
        return draft

    async def _take(self, ctx: RunContext, inputs: Inputs, model: str, reason: str | None) -> Take:
        req, refs, deps, voices, r2v = await self._request(inputs, ctx.compiled, model, ctx)
        calls: list[MediaCall] = []
        rewrite: str | None = None
        if self._rewrites(model):
            # The rewrite is told what the first frame really shows (M5 step 15g).
            look = await vlook.describe(
                self.services,
                str(inputs.context["first_frame"]),
                item_of(ctx.product),
                replace(
                    self._call_ctx(ctx, inputs.episode_id), component_id=vlook.VLOOK, select=None
                ),
            )
            if look is not None:
                calls.append(
                    MediaCall([], look.model_key, look.where, look.cost_usd, cached=look.cached)
                )
            seen = look.text if look is not None else None
            facts = self._facts(inputs, req, refs, voices, r2v, ctx.lang, seen)
            facts.duration_s = self._rendered_s(req, model)
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
        params = {
            **sent,
            "width": size.w,
            "height": size.h,
            "duration_s": raw.get("duration_s") or sent.get("duration_s"),
            "video_in": raw["sha256"],
        }
        # A draft guided with the shot before's tail: the untrimmed clip starts with those
        # frames, so the final is cut back by them too; the API takes no clip guide.
        head = head_s(sent, float(frame_["fps"]))
        params.pop("tail_clip", None)
        params.pop("tail_frames", None)
        model = ctx.model_key or self._final_model()
        if sent.get("ref_audio") and model:
            # The draft's voice samples, joined when the API wants them longer.
            by_anchor = {v["sha256"]: v for v in inputs.context["voices"]}
            voices = [by_anchor.get(sha, {"sha256": sha, "who": ""}) for sha in sent["ref_audio"]]
            caps = self.services.registry.spec(model).caps.model_extra or {}
            params["ref_audio"] = self._voice_samples(voices, caps)
        req = ModelRequest(
            kind="upscale",
            prompt=prompt,
            seed=source.seed,
            params=params,
            meta={"component": self.id, "task": "final"},
        )
        call = await self.media_call(
            ctx, req, inputs.episode_id, model=ctx.model_key, fallback=False
        )
        files, info = await self._clip_files(call, raw=False, head=head)
        payload = {
            **source.payload_json,
            "duration_s": round(info.duration_s, 3),
            "resolution": "2k",
            "window": await self._window(files, inputs),
            "cuts": await self._cuts(files),
        }
        payload.pop("prompt_ir", None)
        files = await self._check_take(ctx, inputs, files, payload)
        draft = self.media_draft(ctx, inputs, payload, files, [call], prompt, stage="final")
        draft.params["source"] = {"version_id": source.id}
        return draft

    async def _clip_files(
        self, call: MediaCall, *, raw: bool, head: float
    ) -> tuple[list[dict[str, Any]], VideoInfo]:
        video = next((f for f in call.files if f.mime.startswith("video/")), None)
        if video is None:
            raise ComponentError("no_video")
        return await clip_files(self.services.store, video.sha256, raw=raw, head=head)

    async def _check_take(
        self,
        ctx: RunContext,
        inputs: Inputs,
        files: list[dict[str, Any]],
        payload: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """take 检查 (M5.5): the take's contact sheet looked at against its contract, and what
        its own measures say, into ``payload.check`` (only a warning); the sheet joins the take's
        files (``role: sheet``)."""
        items = takecheck.measured(payload)
        model = None
        video = next(f for f in files if f["role"] == "video")
        data = self.services.store.path_for(video["sha256"]).read_bytes()
        try:
            png, times = await contact_sheet(data)
        except VideoError as exc:
            logger.warning("no contact sheet for the take ({})", exc.code)
        else:
            sha = self.services.store.put_bytes(png)
            files = [*files, file_entry("sheet", sha, "image/png")]
            asks = {**take_asks(inputs.context), "times": times}
            call_ctx = self._call_ctx(ctx, inputs.episode_id)
            seen = await takecheck.look(self.services, sha, asks, item_of(ctx.product), call_ctx)
            if seen is not None:
                items, model = [*seen[0], *items], seen[1]
            payload["sheet_times"] = times
        payload["check"] = {"items": items, "ok": all(x["ok"] for x in items), "model": model}
        return files

    async def _cuts(self, files: list[dict[str, Any]]) -> list[float]:
        """Where the take seems to cut inside the clip (M5 step 15j; a take of one continuous
        shot should have none; M6 checks it)."""
        video = next(f for f in files if f["role"] == "video")
        data = self.services.store.path_for(video["sha256"]).read_bytes()
        try:
            return await scene_cuts(data)
        except VideoError as exc:
            raise ComponentError(exc.code) from exc

    async def _window(self, files: list[dict[str, Any]], inputs: Inputs) -> dict[str, float]:
        """Where the edit should take the take from and to (M5 step 15i): past the still
        opening, the spoken line whole (``media/video.py:usable_window``)."""
        video = next(f for f in files if f["role"] == "video")
        context = inputs.context
        spoken = bool(context["dialogue"]) and context["audio_mode"] != "none"
        data = self.services.store.path_for(video["sha256"]).read_bytes()
        try:
            w = await usable_window(data, float(context["seconds"]), spoken=spoken)
        except VideoError as exc:
            raise ComponentError(exc.code) from exc
        return {"in_s": w.in_s, "out_s": w.out_s}

    def _rendered_s(self, req: ModelRequest, model: str) -> float:
        """How long the video H3 renders really is (M5 step 15j): the seconds asked, held to
        the model's range (``caps.duration_s``, at least 5), rounded up to 17k + 5 frames
        (a 4 s shot is 124 frames, 5.17 s). The rewrite paces the action over this, not over
        the shot's seconds, or the action and the line land late and the edit cuts them."""
        caps = self.services.registry.spec(model).caps.model_extra or {}
        lo, hi = caps.get("duration_s") or (0, 1e9)
        fps = float(req.params.get("fps") or 24)
        seconds = min(max(float(req.params["duration_s"]), float(lo)), float(hi))
        frames = math.ceil(max(0.0, seconds * fps - 5) / 17) * 17 + 5
        return round(frames / fps, 2)

    def _guided(self, context: dict[str, Any], model: str) -> bool:
        """A continuous shot's take on a local workflow that takes the shot before's tail."""
        wf = local_workflow(self.services.registry, model) if context.get("tail_clip") else None
        return wf is not None and wf.has("tail_clip")

    async def _tail_params(self, context: dict[str, Any]) -> dict[str, Any]:
        """The shot before's last ``TAIL_FRAMES`` frames with their sound (``tail_clip``), and
        the take asked that many frames longer (they are cut off again when it is stored)."""
        store = self.services.store
        fps = float(context["frame"]["fps"])
        try:
            data = store.path_for(str(context["tail_clip"])).read_bytes()
            tail = await tail_clip(data, TAIL_FRAMES, fps, audio_frames=TAIL_AUDIO_FRAMES)
        except VideoError as exc:
            raise ComponentError(exc.code) from exc
        return {
            "tail_clip": store.put_bytes(tail),
            "tail_frames": TAIL_FRAMES,
            "duration_s": round(float(context["seconds"]) + TAIL_FRAMES / fps, 3),
        }

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
        seconds = float(inputs.context["seconds"])
        if self._guided(inputs.context, model):  # the tail frames are made again
            seconds += TAIL_FRAMES / float(frame_["fps"])
        req = ModelRequest(
            kind="video",
            prompt=compiled,
            params={
                "n": 1,
                "width": size.w,
                "height": size.h,
                "aspect": frame_["aspect"],
                "duration_s": seconds,
                "fps": int(frame_["fps"]),
            },
        )
        estimate = self.services.registry.get(model).estimate(req)
        ir = self._ir_model(model)
        if ir is not None:
            ask = ModelRequest(kind="llm_aux", prompt=compiled, params=req.params)
        elif self._rewrites(model) and (ir := self._route_model(VPROMPT)) is not None:
            # Priced as if asked twice (the second try carries the first answer and the fixes).
            system = self.services.compiler.render("vid/h3_rewrite_system.j2")
            ask = ModelRequest(
                kind="llm", prompt=f"{system}\n{compiled}\n{compiled}", max_tokens=6000
            )
        else:
            return estimate
        parts = [estimate, self.services.registry.get(ir).estimate(ask)]
        if self._rewrites(model):  # the first frame looked at once (cached afterwards)
            look = vlook.estimate(self.services, self._route_model(vlook.VLOOK))
            parts += [look] if look is not None else []
        asks = {**take_asks(inputs.context), "times": []}  # take 检查: the take looked at once
        check = takecheck.estimate(self.services, self._route_model(takecheck.TAKECHECK), asks)
        parts += [check] if check is not None else []
        return Estimate(
            cost_usd=sum(e.cost_usd for e in parts),
            seconds=sum(e.seconds for e in parts),
            priced=all(e.priced for e in parts),
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

    def _route_model(self, route_id: str) -> str | None:
        """A route's default model (``vprompt``'s writer, ``vlook``'s eyes), for estimates,
        which cannot read the series' own route."""
        try:
            route = get_config().components.component(route_id).balanced
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
        seen: str | None = None,
    ) -> h3_format.Facts:
        """What the rewriter is told: the take's layout, what is sent and the lines it speaks;
        the first frame as a vision model saw it (``seen``), else the plan's intent."""
        context = inputs.context
        language = LANGUAGE.get(lang, "Chinese")
        first = seen if seen is not None else str(context.get("first_desc", ""))
        pictures = [h3_format.Picture("first_frame", description=first)]
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
            shot_kind=str(context.get("kind") or "performance"),
            beats=int(context.get("beats", 2)),
            start=list(context.get("start") or []),
            end=list(context.get("end") or []),
            props=list(context.get("props") or []),
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
        call_ctx = replace(
            self._call_ctx(ctx, inputs.episode_id), component_id=VPROMPT, select=None
        )
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
            params["ref_audio"] = self._voice_samples(voices, extra)
        if self._guided(context, model):
            # 末尾片段续写 (M5 step 15e): the first frame stays for the API fallback and as
            # h3-r2v's <Picture 1>; h3-i2v drops its anchor when the tail is there.
            params.update(await self._tail_params(context))
        if spec.where == "local" and wf is not None and wf.meta.branches:
            settings = await self.services.router.settings(self.id, item_of(ctx.product))
            chosen = settings.values.get("branches")
            params["branches"] = wf.branch_states(chosen if isinstance(chosen, dict) else None)
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

    def _voice_samples(self, voices: list[dict[str, Any]], caps: dict[str, Any]) -> list[str]:
        """The voice samples sent: each voice's anchor, or, when the model wants longer audio
        (``caps.audio_s``, the H3 API's 2–15 s) than the anchor lasts, the voice's clips joined
        until long enough (``joined_sample``). Too short even then: stopped here, before
        anything is paid for."""
        span = caps.get("audio_s")
        if not span:
            return [str(v["sha256"]) for v in voices]
        floor, ceiling = float(span[0]), float(span[1])
        store = self.services.store
        out: list[str] = []
        for v in voices:
            clips = list(v.get("clips") or [{"sha256": v["sha256"], "duration_s": None}])
            first = clips[0].get("duration_s")
            if first is not None and floor <= float(first) <= ceiling:
                out.append(str(clips[0]["sha256"]))
                continue
            datas = [store.path_for(str(c["sha256"])).read_bytes() for c in clips]
            joined = joined_sample(datas, floor, ceiling)
            if joined is None:
                total = sum(float(c.get("duration_s") or 0) for c in clips)
                raise ComponentError(
                    "voice_sample_short", name=v["who"], seconds=round(total, 1), min_s=floor
                )
            out.append(store.put_bytes(joined))
        return out

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
        # 镜头契约 (M5.5): the action budget, how it starts and ends, the props as set.
        kind, beats = context.get("kind"), int(context.get("beats", 2))
        description += " " + (INSERT_BEATS if kind == "insert" else BEATS.format(n=beats)) + "。"
        for label, key in (
            ("开始时", "start"),
            ("结束时", "end"),
            ("道具（状态是摆好的，每样只有一件）", "props"),
        ):
            if context.get(key):
                description += f" {label}：" + "；".join(context[key]) + "。"
        overlay = context.get("overlay") or []
        if overlay:  # said in the edit (M5 step 15p): the take shows the mood, lips closed
            description += " 画外（剪辑时另铺，这条片子里没有人说话、嘴闭着）：" + "；".join(
                f"{o['who']}（{OVERLAY_HOW.get(str(o.get('how')), '画外音')}）：{o['text']}"
                for o in overlay
            )
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
