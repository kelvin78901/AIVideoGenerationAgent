"""What the components that make pictures and audio share (M3: ``img``, ``views``; then
``text``, ``voice``, ``dub``).

- **Size** comes from the series' output spec only (hard rule 10): a local draft is made at the
  draft tier (short side 768), an API run at the delivery tier (1080p / 2K). Adapters map it to
  what their model supports.
- **One call** (``media_call``) goes through ``router.call()`` like every call (hard rule 1); its
  stored files (and its JSON, e.g. a designed voice's id) are cached by request (in
  ``llm_cache``), so a retried or resumed job does not pay twice for what it already has.
- **A flow of calls** (three views, a voice's design and its variants) calls with
  ``fallback=False`` and falls back as a whole (``run_flow``), so the pieces of one version
  never come from different models.
- **The version** keeps the full prompt sent as a ``prompt`` file, like the writing components.
"""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import asdict, dataclass
from typing import Any, ClassVar, TypeVar

from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from drama_series_agent.core.config import get_config
from drama_series_agent.core.models_db import (
    Asset,
    LlmCache,
    OutputSpecRow,
    Product,
    ProductVersion,
)
from drama_series_agent.modelhub.adapters.base import ModelError, ModelRequest
from drama_series_agent.modelhub.router import BudgetExceeded, NeedsConfirm, Router, StoredFile
from drama_series_agent.pipeline.component import (
    Component,
    ComponentError,
    Inputs,
    RunContext,
    version_fallback,
)
from drama_series_agent.pipeline.drafts import VersionDraft, file_entry
from drama_series_agent.pipeline.hashing import canonical_json
from drama_series_agent.pipeline.runs import item_of
from drama_series_agent.prompts.compiler import Block
from drama_series_agent.spec.dims import Aspect, Dims, dims

T = TypeVar("T")


@dataclass
class MediaCall:
    files: list[StoredFile]
    model_key: str
    where: str
    cost_usd: float
    fallback_reason: str | None = None  # error / timeout when the router fell back
    cached: bool = False
    data: Any = None  # the call's JSON (a voice design's ``voice_id``)


async def output_frame(session: AsyncSession, series_id: str) -> dict[str, str]:
    """The series' aspect and delivery tier (the spec defaults before a spec exists)."""
    row = await session.get(OutputSpecRow, series_id)
    defaults = get_config().spec.defaults
    return {
        "aspect": str(row.aspect if row is not None else defaults.get("aspect", "9:16")),
        "delivery": str(row.delivery if row is not None else defaults.get("delivery", "1080p")),
    }


def frame_size(frame: dict[str, str], where: str) -> Dims:
    """A local draft at the draft tier, an API run at the delivery tier (hard rule 10)."""
    aspect: Aspect = frame["aspect"]  # type: ignore[assignment]
    return dims(aspect, "draft" if where == "local" else frame["delivery"])  # type: ignore[arg-type]


def prompt_text(compiled: str, blocks: Sequence[Block]) -> str:
    """One prompt for a picture or voice model: the instructions, then the data blocks."""
    data = "\n\n".join(f"[{b.title}]\n{b.text.strip()}" for b in blocks)
    return f"{compiled.strip()}\n\n{data}" if data else compiled.strip()


def ref_file(version: ProductVersion) -> dict[str, Any] | None:
    """The file a locked version holds (``role: ref``; a lone candidate otherwise)."""
    files = [f for f in version.files_json if f.get("role") != "prompt"]
    refs = [f for f in files if f.get("role") == "ref"]
    found = refs or files
    return found[0] if found else None


async def locked_ref(session: AsyncSession, product: Product) -> dict[str, Any] | None:
    """The picture a locked product holds; None while it is not locked."""
    if not product.locked_hash or not product.adopted_version_id:
        return None
    v = await session.get(ProductVersion, product.adopted_version_id)
    return ref_file(v) if v is not None else None


class MediaComponent(Component):
    """A component whose versions are files (pictures, audio)."""

    # The asset's own product (参考图, 画面文字, 音色): its description is the intent layer.
    intent_from_asset: ClassVar[bool] = False

    async def default_intent(self, session: AsyncSession, product: Product, lang: str) -> str:
        if self.intent_from_asset and product.owner_type == "asset":
            asset = await session.get(Asset, product.owner_id)
            if asset is not None:
                return str((asset.seed_json or {}).get("description") or "")
        return await super().default_intent(session, product, lang)

    def output_schema(self) -> type[BaseModel]:
        raise NotImplementedError("pictures and audio, not JSON")

    def candidates(self) -> int:
        try:
            n = get_config().components.component(self.id).candidates
        except KeyError:
            n = None
        return n or 1

    def where_of(self, model: str) -> str:
        return self.services.registry.spec(model).where

    def image_request(
        self,
        prompt: str,
        *,
        n: int,
        size: Dims,
        aspect: str,
        seed: int | None,
        task: str,
        refs: Sequence[str] = (),
        extra: dict[str, Any] | None = None,
    ) -> ModelRequest:
        """``refs``: sha256 of the reference pictures (the blob store has them)."""
        params: dict[str, Any] = {
            "n": n,
            "width": size.w,
            "height": size.h,
            "aspect": aspect,
            "task": task,
            **(extra or {}),
        }
        if refs:
            params["refs"] = list(refs)
        return ModelRequest(
            kind="image",
            prompt=prompt,
            seed=seed,
            params=params,
            meta={"component": self.id, "task": task},
        )

    async def media_call(
        self,
        ctx: RunContext,
        req: ModelRequest,
        episode_id: str | None,
        *,
        model: str,
        fallback: bool = True,
        fallback_reason: str | None = None,
    ) -> MediaCall:
        """One call, its stored files cached by request (a retry does not pay again)."""
        key = _media_key(model, req)
        async with self.services.db.session() as session:
            row = await session.get(LlmCache, key)
        if row is not None:
            files = [StoredFile(**f) for f in row.value_json.get("files") or []]
            if all(self.services.store.exists(f.sha256) for f in files):
                where = self.services.registry.spec(row.model_key).where
                data = row.value_json.get("json")
                return MediaCall(files, row.model_key, where, 0.0, cached=True, data=data)
        routed = await self.services.router.call(
            self.id,
            req,
            self._call_ctx(ctx, episode_id),
            model=model,
            fallback_reason=fallback_reason,
            fallback=fallback,
        )
        async with self.services.db.session() as session:
            if await session.get(LlmCache, key) is None:
                value = {"files": [asdict(f) for f in routed.files], "json": routed.json}
                session.add(LlmCache(key=key, model_key=routed.model_key, value_json=value))
                await session.commit()
        return MediaCall(
            routed.files,
            routed.model_key,
            routed.where,
            routed.cost_usd,
            version_fallback(routed.fallback_reason),
            data=routed.json,
        )

    async def source_candidate(
        self, product: Product, params: dict[str, Any]
    ) -> tuple[ProductVersion, int] | None:
        """The draft an API final starts from (``params.source_version_id / source_idx``)."""
        version_id = params.get("source_version_id")
        if not version_id:
            return None
        idx = int(params.get("source_idx") or 0)
        async with self.services.db.session() as session:
            v = await session.get(ProductVersion, str(version_id))
        if v is None or v.product_id != product.id:
            raise ComponentError("version_not_found", id=version_id)
        if not any(f.get("role") == "candidate" and f.get("idx") == idx for f in v.files_json):
            raise ComponentError("no_such_candidate", id=v.id, idx=idx)
        return v, idx

    async def run_flow(
        self, ctx: RunContext, flow: Callable[[str, str | None], Awaitable[T]]
    ) -> tuple[T, str | None]:
        """Run ``flow(model, fallback_reason)`` on the run's model; if a step fails, run the
        whole flow again on the component's fallback (or ask first, ``notify: ask``).
        Returns the result and the fallback reason (None when the first model made it)."""
        if ctx.fallback_reason is not None:  # the user agreed to this fallback already
            return await flow(ctx.model_key, ctx.fallback_reason), ctx.fallback_reason
        try:
            return await flow(ctx.model_key, None), None
        except BudgetExceeded:
            raise
        except ModelError as exc:
            router = self.services.router
            settings = await router.settings(self.id, item_of(ctx.product))
            trigger = "timeout" if exc.code == "timeout" else "error"
            target = Router.fallback_model(settings, [ctx.model_key], trigger)
            known = {s.key for s in self.services.registry.specs()}
            if target is None or target not in known:
                raise
            if settings.values["fallback"].get("notify") == "ask" and ctx.job_id is not None:
                raise NeedsConfirm(ctx.model_key, target, exc.code) from exc
            return await flow(target, exc.code), version_fallback(exc.code)

    def media_draft(
        self,
        ctx: RunContext,
        inputs: Inputs,
        payload: dict[str, Any],
        files: list[dict[str, Any]],
        calls: Sequence[MediaCall],
        prompt: str,
        *,
        stage: str | None = None,
        fallback_reason: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> VersionDraft:
        """A version from a run's calls: its files, cost summed, the prompt as a file."""
        sha = self.services.store.put_bytes(prompt.encode("utf-8"))
        last = calls[-1]
        reasons = [c.fallback_reason for c in calls if c.fallback_reason]
        return VersionDraft(
            payload=payload,
            files=[*files, file_entry("prompt", sha, "text/plain; charset=utf-8")],
            intent=ctx.intent,
            compiled=ctx.compiled,
            compiled_overridden=ctx.compiled_overridden,
            model_key=last.model_key,
            where=last.where,
            seed=ctx.seed,
            params={"mode": ctx.mode, "calls": len(calls), **(params or {})},
            cost_usd=round(sum(c.cost_usd for c in calls), 6),
            job_id=ctx.job_id,
            fallback_reason=fallback_reason or (reasons[0] if reasons else None),
            stage=stage,
            dependencies=list(inputs.deps),
        )


def _media_key(model: str, req: ModelRequest) -> str:
    raw = canonical_json(
        {
            "model": model,
            "prompt": req.prompt,
            "params": req.params,
            "seed": req.seed,
            "task": req.meta.get("task"),
        }
    )
    return "media:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def candidate_files(call: MediaCall, role: str = "candidate") -> list[dict[str, Any]]:
    """``files[]`` entries for a call's pictures, numbered from 0 (``idx``)."""
    return [
        file_entry(role, f.sha256, f.mime, w=f.w, h=f.h, duration_s=f.duration_s, idx=i)
        for i, f in enumerate(call.files)
    ]
