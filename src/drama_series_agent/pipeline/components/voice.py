"""音色 (SPEC 5 ``voice``; M3): one voice per speaking character, which every line of theirs is
dubbed with. How it is auditioned and finished is ``config/voice.yaml``.

1. **「重跑」 = free auditions** (``stage: draft``): three drafts, each the description plus a
   tendency (偏低沉 / 更清亮 / 带一点沙哑), reading the character's first lines. Locally
   Qwen3-TTS designs a voice from words: one clip per line (``role: candidate``, ``idx`` the
   draft, ``line`` the line). On an API model (no local TTS here) a draft is a MiniMax voice
   design: one trial clip of the lines, its ``voice_id`` kept on the candidate.
2. **「用 MiniMax 出终版」** (``where: api`` + ``params.source_version_id / source_idx``,
   ``stage: final``): the picked draft becomes a MiniMax voice (designed now, or the draft's own
   ``voice_id``) and T2A speaks the character's first line in each emotion of the config. The
   design's flat $3 is billed on the first synthesis with the voice (``charge_design``), which
   is when MiniMax charges it: three API auditions that are never finished cost characters only.
   The calls run with ``fallback=False``; if one fails, the whole final is made locally instead
   (``run_flow``), so a voice never mixes models. Each call is cached by request, so a retried
   job neither designs nor pays again.
3. **「本地」 source** (or that fallback): the anchor is the picked draft itself and the variants
   come from ``local_final`` (IndexTTS) with the emotion in words; free.

Every clip is levelled (``media/audio.py``) before it is stored. A final's files are the anchor
clips (``role: anchor``) and one ``role: variant`` per emotion (``emotion``), each with its
waveform; its payload ``{provider, voice_id, emotions, label}``. Only a final can be locked
(``AssetService.lock``), as a whole.
"""

from __future__ import annotations

from typing import Any

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from drama_series_agent.core.config import VoiceConfig, get_config
from drama_series_agent.core.models_db import (
    Asset,
    AssetUse,
    Episode,
    Product,
    ProductVersion,
    Scene,
    ScriptLine,
)
from drama_series_agent.media.audio import prepare_clip
from drama_series_agent.modelhub.adapters.base import Estimate, ModelRequest
from drama_series_agent.pipeline.component import ComponentError, Inputs, RunContext
from drama_series_agent.pipeline.components.media import MediaCall, MediaComponent, prompt_text
from drama_series_agent.pipeline.drafts import VersionDraft, file_entry
from drama_series_agent.pipeline.errors import PipelineError
from drama_series_agent.prompts.compiler import Block

VOICE_SLOT = "voice"
DESIGN = "voice_design"


async def audition_lines(session: AsyncSession, asset_id: str, n: int) -> list[dict[str, Any]]:
    """The first ``n`` lines a voice speaks, in script order (episode, scene, line)."""
    uses = (await session.exec(select(AssetUse).where(AssetUse.asset_id == asset_id))).all()
    ids = [i for u in uses for i in u.line_ids_json]
    if not ids:
        return []
    live = col(ScriptLine.retired).is_(False)
    lines = (await session.exec(select(ScriptLine).where(col(ScriptLine.id).in_(ids), live))).all()
    scenes = {
        s.id: s.idx
        for s in (
            await session.exec(select(Scene).where(col(Scene.id).in_({x.scene_id for x in lines})))
        ).all()
    }
    episodes = {
        e.id: e.idx
        for e in (
            await session.exec(
                select(Episode).where(col(Episode.id).in_({x.episode_id for x in lines}))
            )
        ).all()
    }
    spoken = [x for x in lines if x.text.strip()]
    spoken.sort(key=lambda x: (episodes.get(x.episode_id, 0), scenes.get(x.scene_id, 0), x.idx))
    return [{"id": x.id, "text": x.text, "tone": x.tone or ""} for x in spoken[:n]]


class VoiceComponent(MediaComponent):
    id = "voice"
    slot = VOICE_SLOT
    owner_type = "asset"
    auto_adopt = False
    intent_from_asset = True

    @property
    def config(self) -> VoiceConfig:
        return get_config().voice

    async def inputs(self, session: AsyncSession, product: Product) -> Inputs:
        asset = await session.get(Asset, product.owner_id)
        if asset is None or asset.retired or asset.kind != "voice":
            raise PipelineError(404, "asset_not_found", id=product.owner_id)
        cfg = self.config
        lines = await audition_lines(session, asset.id, cfg.lines) or [
            {"id": None, "text": cfg.sample_text, "tone": ""}
        ]
        method = ((product.settings_json or {}).get("voice") or {}).get("method") or "design"
        reads = "\n".join(f"{x['text']}（{x['tone']}）" if x["tone"] else x["text"] for x in lines)
        return Inputs(
            blocks=[Block("角色", asset.name), Block("试读", reads)],
            context={"lines": lines, "method": method},
        )

    # ------------------------------------------------------------------ run

    async def run(self, ctx: RunContext, inputs: Inputs) -> VersionDraft:
        if inputs.context["method"] == "clone":
            raise ComponentError("voice_clone_not_supported")
        source = await self.source_candidate(ctx.product, inputs.params)
        if source is None:
            return await self._drafts(ctx, inputs)
        return await self._final(ctx, inputs, *source)

    async def _drafts(self, ctx: RunContext, inputs: Inputs) -> VersionDraft:
        lines = inputs.context["lines"]
        local = self.where_of(ctx.model_key) == "local"
        files: list[dict[str, Any]] = []
        candidates: list[dict[str, Any]] = []
        calls: list[MediaCall] = []
        for i, draft in enumerate(self.config.drafts[: self.candidates()]):
            design = f"{ctx.intent.strip()}；{draft.hint}"
            entry: dict[str, Any] = {"label": draft.label, "design": design}
            if local:
                for j, line in enumerate(lines):
                    req = self._tts(line, task=f"draft:{i}:{j}", seed=ctx.seed, design=design)
                    call = await self._call(ctx, req, ctx.model_key, ctx.fallback_reason)
                    calls.append(call)
                    files.append(await self._clip(call, "candidate", idx=i, line=j))
            else:
                req = self._design(lines, design, task=f"draft:{i}", seed=ctx.seed)
                call = await self._call(ctx, req, ctx.model_key, ctx.fallback_reason)
                calls.append(call)
                files.append(await self._clip(call, "candidate", idx=i, line=None))
                entry["voice_id"] = (call.data or {}).get("voice_id")
            entry["waveform"] = next(f["waveform"] for f in files if f["idx"] == i)
            candidates.append(entry)
        prompt = prompt_text(ctx.compiled, inputs.blocks)
        return self.media_draft(
            ctx, inputs, {"candidates": candidates}, files, calls, prompt, stage="draft"
        )

    async def _final(
        self, ctx: RunContext, inputs: Inputs, source: ProductVersion, idx: int
    ) -> VersionDraft:
        candidates = (source.payload_json or {}).get("candidates") or []
        picked: dict[str, Any] = candidates[idx] if idx < len(candidates) else {}
        anchors = sorted(
            (f for f in source.files_json if f.get("role") == "candidate" and f.get("idx") == idx),
            key=lambda f: int(f.get("line") or 0),
        )
        local = inputs.context["method"] == "local" or self.where_of(ctx.model_key) == "local"

        async def flow(model: str, reason: str | None) -> tuple[list[Any], dict[str, Any]]:
            if self.where_of(model) == "local":
                return await self._local_final(ctx, inputs, model, reason, anchors)
            return await self._api_final(ctx, inputs, model, reason, picked, anchors)

        if local:
            model = self.config.local_final
            (calls, made), reason = await flow(model, None), None
        else:
            (calls, made), reason = await self.run_flow(ctx, flow)
        files, payload = made["files"], made["payload"]
        payload["label"] = picked.get("label")
        prompt = prompt_text(ctx.compiled, inputs.blocks)
        draft = self.media_draft(
            ctx, inputs, payload, files, calls, prompt, stage="final", fallback_reason=reason
        )
        draft.params["source"] = {"version_id": source.id, "idx": idx}
        return draft

    async def _api_final(
        self,
        ctx: RunContext,
        inputs: Inputs,
        model: str,
        reason: str | None,
        picked: dict[str, Any],
        anchors: list[dict[str, Any]],
    ) -> tuple[list[Any], dict[str, Any]]:
        """MiniMax: the voice (designed now unless the draft is one), then every emotion."""
        lines = inputs.context["lines"]
        calls: list[MediaCall] = []
        files: list[dict[str, Any]] = []
        voice_id = picked.get("voice_id")
        if voice_id:
            files += [{**f, "role": "anchor", "idx": None} for f in anchors]
        else:
            design = str(picked.get("design") or ctx.intent)
            call = await self._call(
                ctx, self._design(lines, design, task="design", seed=ctx.seed), model, reason
            )
            calls.append(call)
            voice_id = (call.data or {}).get("voice_id")
            if not voice_id:
                raise ComponentError("voice_design_failed")
            files.append(await self._clip(call, "anchor", idx=None, line=None))
        for k, emotion in enumerate(self.config.emotions):
            how = dict(emotion.minimax) if model.startswith("minimax/") else {}
            use = str(how.pop("model", model))
            req = self._tts(
                lines[0],
                task=f"variant:{emotion.id}",
                seed=ctx.seed,
                voice_id=voice_id,
                charge_design=k == 0,
                **how,
            )
            call = await self._call(ctx, req, use, reason)
            calls.append(call)
            files.append(await self._clip(call, "variant", idx=k, line=0, emotion=emotion.id))
        payload = {"provider": model.split("/", 1)[0], "voice_id": voice_id}
        return calls, {"files": files, "payload": self._with_emotions(payload)}

    async def _local_final(
        self,
        ctx: RunContext,
        inputs: Inputs,
        model: str,
        reason: str | None,
        anchors: list[dict[str, Any]],
    ) -> tuple[list[Any], dict[str, Any]]:
        """Free: the draft is the anchor; the variants speak in its voice, with the emotion in
        words."""
        if not anchors:
            raise ComponentError("voice_no_anchor")
        speaker = anchors[0]["sha256"]
        files = [{**f, "role": "anchor", "idx": None} for f in anchors]
        calls: list[MediaCall] = []
        for k, emotion in enumerate(self.config.emotions):
            req = self._tts(
                inputs.context["lines"][0],
                task=f"variant:{emotion.id}",
                seed=ctx.seed,
                speaker=speaker,
                speaker_path=str(self.services.store.path_for(speaker)),
                emotion_text=emotion.instruct,
            )
            call = await self._call(ctx, req, model, reason)
            calls.append(call)
            files.append(await self._clip(call, "variant", idx=k, line=0, emotion=emotion.id))
        payload = {"provider": "local", "voice_id": None}
        return calls, {"files": files, "payload": self._with_emotions(payload)}

    def estimate(self, inputs: Inputs, compiled: str, model: str) -> Estimate:
        """Drafts: one clip per draft and line (one design per draft on an API model). A final:
        the design and every emotion, the design's flat price included."""
        lines = inputs.context["lines"]
        reqs: list[tuple[str, ModelRequest]] = []
        if not inputs.params.get("source_version_id"):
            for i, draft in enumerate(self.config.drafts[: self.candidates()]):
                if self.where_of(model) == "local":
                    reqs += [
                        (model, self._tts(x, task=f"draft:{i}:{j}", seed=None, design=draft.hint))
                        for j, x in enumerate(lines)
                    ]
                else:
                    reqs.append((model, self._design(lines, draft.hint, task="draft", seed=None)))
        elif inputs.context["method"] == "local" or self.where_of(model) == "local":
            local = self.config.local_final
            reqs += [
                (local, self._tts(lines[0], task=e.id, seed=None)) for e in self.config.emotions
            ]
        else:
            reqs.append((model, self._design(lines, compiled, task="design", seed=None)))
            for k, e in enumerate(self.config.emotions):
                how = dict(e.minimax) if model.startswith("minimax/") else {}
                use = str(how.pop("model", model))
                req = self._tts(lines[0], task=e.id, seed=None, charge_design=k == 0, **how)
                reqs.append((use, req))
        total, seconds, priced = 0.0, 0.0, True
        for key, req in reqs:
            est = self.services.registry.get(key).estimate(req)
            total += est.cost_usd
            seconds += est.seconds
            priced = priced and est.priced
        return Estimate(cost_usd=round(total, 6), seconds=seconds, priced=priced)

    # ------------------------------------------------------------------ internals

    def _with_emotions(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {**payload, "emotions": [e.id for e in self.config.emotions]}

    def _tts(
        self, line: dict[str, Any], *, task: str, seed: int | None, **params: Any
    ) -> ModelRequest:
        """Speak one line (a design in words, a voice id or a speaker clip in ``params``)."""
        if line.get("tone"):
            params = {"tone": line["tone"], **params}
        return ModelRequest(
            kind="tts",
            prompt=str(line["text"]),
            seed=seed,
            params={k: v for k, v in params.items() if v is not None and v is not False},
            meta={"component": self.id, "task": task},
        )

    def _design(
        self, lines: list[dict[str, Any]], design: str, *, task: str, seed: int | None
    ) -> ModelRequest:
        """A voice from words; its trial clip reads the lines."""
        return ModelRequest(
            kind=DESIGN,
            prompt="\n".join(str(x["text"]) for x in lines),
            seed=seed,
            params={"design": design},
            meta={"component": self.id, "task": task},
        )

    async def _call(
        self, ctx: RunContext, req: ModelRequest, model: str, reason: str | None
    ) -> MediaCall:
        call = await self.media_call(
            ctx, req, None, model=model, fallback=False, fallback_reason=reason
        )
        if not call.files:
            raise ComponentError("no_audio")
        return call

    async def _clip(self, call: MediaCall, role: str, **extra: Any) -> dict[str, Any]:
        """The call's clip, levelled and stored, as a ``files[]`` entry with its waveform."""
        raw = self.services.store.path_for(call.files[0].sha256).read_bytes()
        clip = await prepare_clip(raw)
        sha = self.services.store.put_bytes(clip.data)
        return file_entry(
            role, sha, "audio/wav", duration_s=clip.duration_s, waveform=clip.waveform, **extra
        )
