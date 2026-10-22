"""台词配音 (SPEC 5 ``dub``; M3): every spoken line in its character's locked voice.

- One product per line with a speaker (slot ``line_audio``, owner ``line:<id>``), made when the
  line is first dubbed (``assets/dub.py``). A line the script drops retires its product
  (``script/service.py``): it is never stale, and it comes back with the line.
- It depends on the line (the script's ``line:<id>`` slice: what is said, how, by whom) and on
  the voice's locked hash, so rewording the line or locking another voice makes it 「待更新」,
  and 「确认并同步」 dubs it again. Every run is adopted: the audio follows the line and the
  voice, and earlier takes stay in the history.
- The speaker's voice must be locked first (409 ``voice_not_locked``, with its name).
- The emotion is the one set on the product by hand, else the tone's (``config/voice.yaml``
  ``tones``), else calm.
- An API voice (``voice_id``) is spoken by T2A in that emotion (whisper on 2.6 HD); a local
  voice, or the router's fallback, by IndexTTS with the voice's sample as the speaker and the
  emotion's variant as its reference. The request carries both, so one call can fall back.
- The clip is levelled like every voice sample; its length is the line's (``pipeline/timing.py``).
"""

from __future__ import annotations

from typing import Any

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from drama_series_agent.core.config import get_config
from drama_series_agent.core.models_db import Asset, AssetUse, Product, ProductVersion, ScriptLine
from drama_series_agent.episodes.service import script_product
from drama_series_agent.modelhub.adapters.base import Estimate, ModelRequest
from drama_series_agent.pipeline.component import Inputs, RunContext
from drama_series_agent.pipeline.components.media import MediaComponent
from drama_series_agent.pipeline.components.voice import VOICE_SLOT
from drama_series_agent.pipeline.drafts import VersionDraft
from drama_series_agent.pipeline.errors import PipelineError
from drama_series_agent.prompts.compiler import Block

LINE_AUDIO_SLOT = "line_audio"
SPEAKING = ("dialogue", "vo")


def pick_voice(line: ScriptLine, voices: list[Asset], uses: list[AssetUse]) -> Asset | None:
    """The voice that speaks ``line``: the one whose appearances hold the line, else the one
    made for its character."""
    speaker = next((u.asset_id for u in uses if line.id in u.line_ids_json), None)
    return next((a for a in voices if a.id == speaker), None) or next(
        (a for a in voices if line.character_id and a.bible_id == line.character_id), None
    )


async def series_voices(
    session: AsyncSession, series_id: str
) -> tuple[list[Asset], list[AssetUse], dict[str, Product]]:
    """The series' voices, their appearances and their products (by asset id)."""
    voices = list(
        (
            await session.exec(
                select(Asset).where(
                    Asset.series_id == series_id,
                    Asset.kind == "voice",
                    col(Asset.retired).is_(False),
                )
            )
        ).all()
    )
    ids = [a.id for a in voices]
    uses = list((await session.exec(select(AssetUse).where(col(AssetUse.asset_id).in_(ids)))).all())
    products = {
        p.owner_id: p
        for p in (
            await session.exec(
                select(Product).where(
                    Product.owner_type == "asset",
                    col(Product.owner_id).in_(ids),
                    Product.slot == VOICE_SLOT,
                )
            )
        ).all()
    }
    return voices, uses, products


async def voice_of(session: AsyncSession, line: ScriptLine) -> tuple[Asset, Product] | None:
    voices, uses, products = await series_voices(session, line.series_id)
    asset = pick_voice(line, voices, uses)
    product = products.get(asset.id) if asset is not None else None
    return (asset, product) if asset is not None and product is not None else None


class DubComponent(MediaComponent):
    id = "dub"
    slot = LINE_AUDIO_SLOT
    owner_type = "line"
    adopt_every_run = True

    async def inputs(self, session: AsyncSession, product: Product) -> Inputs:
        line = await session.get(ScriptLine, product.owner_id)
        if line is None or line.retired or line.type not in SPEAKING:
            raise PipelineError(404, "line_not_found", id=product.owner_id)
        found = await voice_of(session, line)
        if found is None:
            raise PipelineError(409, "no_voice", name=line.character_name or "")
        asset, voice = found
        if not voice.locked_hash or not voice.adopted_version_id:
            raise PipelineError(409, "voice_not_locked", id=asset.id, name=asset.name)
        v = await session.get(ProductVersion, voice.adopted_version_id)
        script = await script_product(session, line.episode_id)
        if v is None or script is None:
            raise PipelineError(409, "voice_not_locked", id=asset.id, name=asset.name)
        invalidation = self.services.invalidation
        deps = [
            await invalidation.dependency(session, script.id, f"line:{line.id}"),
            await invalidation.dependency(session, voice.id, ""),
        ]
        cfg = get_config().voice
        emotion = (product.settings_json or {}).get("emotion") or cfg.emotion_of(line.tone)
        files = v.files_json
        anchor = next((f for f in files if f.get("role") == "anchor"), None)
        variant = next(
            (f for f in files if f.get("role") == "variant" and f.get("emotion") == emotion),
            None,
        )
        return Inputs(
            blocks=[Block("台词", line.text), Block("语气", line.tone or "")],
            deps=deps,
            episode_id=line.episode_id,
            context={
                "text": line.text,
                "emotion": emotion,
                "voice_id": (v.payload_json or {}).get("voice_id"),
                "anchor": anchor["sha256"] if anchor else None,
                "variant": variant["sha256"] if variant else None,
            },
        )

    async def run(self, ctx: RunContext, inputs: Inputs) -> VersionDraft:
        model, req = self._request(inputs, ctx.model_key, ctx.seed)
        call = await self.media_call(
            ctx, req, inputs.episode_id, model=model, fallback_reason=ctx.fallback_reason
        )
        if not call.files:
            raise PipelineError(502, "no_audio")
        f = await self.audio_file(call, "audio")
        payload = {"emotion": inputs.context["emotion"], "duration_s": f["duration_s"]}
        return self.media_draft(ctx, inputs, payload, [f], [call], inputs.context["text"])

    def estimate(self, inputs: Inputs, compiled: str, model: str) -> Estimate:
        use, req = self._request(inputs, model, None)
        return self.services.registry.get(use).estimate(req)

    def _request(self, inputs: Inputs, model: str, seed: int | None) -> tuple[str, ModelRequest]:
        """The model that speaks the line and the request: T2A for an API voice, else the local
        model; the speaker's sample and emotion reference ride along for a local fallback."""
        c = inputs.context
        cfg = get_config().voice
        if not c["voice_id"] and self.where_of(model) == "api":
            model = cfg.local_final  # a local voice has no id an API knows
        emotion = next((e for e in cfg.emotions if e.id == c["emotion"]), None)
        params: dict[str, Any] = {}
        if c["voice_id"] and model.startswith("minimax/") and emotion is not None:
            how = dict(emotion.minimax)
            model = str(how.pop("model", model))
            params.update(how)
        store = self.services.store
        for name, sha in (("speaker", c["anchor"]), ("emotion_ref", c["variant"])):
            if sha:
                params[name] = sha
                params[f"{name}_path"] = str(store.path_for(sha))
        if c["voice_id"]:
            params["voice_id"] = c["voice_id"]
        if emotion is not None:
            params["emotion_text"] = emotion.instruct
        return model, ModelRequest(
            kind="tts",
            prompt=c["text"],
            seed=seed,
            params=params,
            meta={"component": self.id, "task": "run"},
        )
