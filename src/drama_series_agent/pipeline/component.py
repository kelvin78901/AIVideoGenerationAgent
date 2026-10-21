"""Pipeline components (SPEC 5): each makes versions of one product slot.

A component says what it reads (``inputs``: titled data blocks for the prompt and the upstream
slices it depends on), what JSON it must return (``output_schema``) and how that becomes the
version's payload (``build_payload``). The default ``run`` makes one call: the compiled layer
the user saw plus the data blocks, JSON output, Pydantic validation, and one more try with the
errors when validation fails (SPEC 5.1); a second failure fails the run and keeps the raw
answer as a blob. Components that need several calls (a long novel in chunks) override ``run``
and use ``call_json``, whose validated answers are cached by request so a retried or resumed
job does not pay twice.

All model calls go through ``router.call()`` (hard rule 1).
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, ClassVar

from pydantic import BaseModel, ValidationError
from sqlmodel.ext.asyncio.session import AsyncSession

from drama_series_agent.core.db import Database
from drama_series_agent.core.models_db import LlmCache, Product, ProductVersion
from drama_series_agent.core.storage import BlobStore
from drama_series_agent.modelhub.adapters.base import CallContext, Estimate, ModelRequest
from drama_series_agent.modelhub.adapters.mock import Responder
from drama_series_agent.modelhub.registry import Registry
from drama_series_agent.modelhub.router import Router
from drama_series_agent.pipeline.drafts import DependencyDraft, VersionDraft
from drama_series_agent.pipeline.hashing import canonical_json
from drama_series_agent.pipeline.invalidation import Invalidation
from drama_series_agent.prompts.compiler import Block, PromptCompiler

Progress = Callable[[dict[str, Any]], Awaitable[None]]


class ComponentError(Exception):
    """A run that cannot produce a version; ``code`` + ``params`` reach the UI."""

    def __init__(self, code: str, **params: Any) -> None:
        super().__init__(code)
        self.code = code
        self.params = params


@dataclass
class Services:
    db: Database
    router: Router
    registry: Registry
    compiler: PromptCompiler
    store: BlobStore
    invalidation: Invalidation


@dataclass
class Inputs:
    blocks: list[Block]
    deps: list[DependencyDraft] = field(default_factory=list)
    # Spending is counted per episode (budget, model_call.episode_id).
    episode_id: str | None = None
    # Anything ``build_payload`` needs that is not in the prompt (paragraph offsets, ids …).
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunContext:
    product: Product
    mode: str  # run / rerun / switch
    model_key: str
    seed: int
    intent: str
    compiled: str
    compiled_overridden: bool
    lang: str = "zh-CN"
    job_id: str | None = None
    attempt: int = 1
    base_version: ProductVersion | None = None
    progress: Progress | None = None
    # The user agreed to this fallback (``notify: ask``): ``model_key`` is it, logged as one.
    fallback_reason: str | None = None
    # A call outside a job the user agreed to pay up to this much for (over the per-call cap).
    confirmed_usd: float | None = None


@dataclass
class CallResult:
    data: BaseModel
    model_key: str
    where: str
    cost_usd: float
    fallback_reason: str | None  # error / timeout when the router fell back
    cached: bool = False


def request_key(model_key: str, req: ModelRequest, schema: type[BaseModel]) -> str:
    raw = canonical_json(
        {
            "model": model_key,
            "messages": req.messages,
            "seed": req.seed,
            "max_tokens": req.max_tokens,
            "schema": schema.__name__,
        }
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)


def parse_json(parsed: Any, text: str, schema: type[BaseModel]) -> tuple[BaseModel | None, str]:
    """Validate a model's answer; returns (data, "") or (None, the errors to send back)."""
    data = parsed
    if data is None:
        m = _FENCE.match(text)
        try:
            data = json.loads(m.group(1) if m else text)
        except json.JSONDecodeError as exc:
            return None, f"不是合法的 JSON（{exc.msg}，第 {exc.lineno} 行）"
    try:
        return schema.model_validate(data), ""
    except ValidationError as exc:
        problems = [
            f"{'.'.join(str(p) for p in e['loc']) or '(根)'}: {e['msg']}" for e in exc.errors()[:8]
        ]
        return None, "；".join(problems)


def version_fallback(code: str | None) -> str | None:
    """``model_call`` keeps the error code; a version only says error or timeout."""
    if code is None:
        return None
    return "timeout" if code == "timeout" else "error"


class Component(ABC):
    id: ClassVar[str]
    slot: ClassVar[str]
    owner_type: ClassVar[str]
    max_tokens: ClassVar[int] = 4000

    def __init__(self, services: Services) -> None:
        self.services = services

    # ------------------------------------------------------------------ to implement

    @abstractmethod
    async def inputs(self, session: AsyncSession, product: Product) -> Inputs:
        """Read the adopted upstream payloads (never the mirror tables) and say what was read."""

    @abstractmethod
    def output_schema(self) -> type[BaseModel]: ...

    async def build_payload(
        self, output: BaseModel, inputs: Inputs, ctx: RunContext
    ) -> dict[str, Any]:
        return output.model_dump(mode="json")

    def mock_responders(self) -> dict[str, Responder]:
        """(task → responder) for Mock mode; registered with the model registry."""
        return {}

    # ------------------------------------------------------------------ run

    async def run(self, ctx: RunContext, inputs: Inputs) -> VersionDraft:
        messages = self.services.compiler.messages(ctx.compiled, inputs.blocks)
        result = await self.call_json(ctx, messages, self.output_schema(), inputs.episode_id)
        payload = await self.build_payload(result.data, inputs, ctx)
        return self.draft(ctx, inputs, payload, [result], messages)

    def draft(
        self,
        ctx: RunContext,
        inputs: Inputs,
        payload: dict[str, Any],
        results: Sequence[CallResult],
        sent: Sequence[dict[str, Any]],
    ) -> VersionDraft:
        """A version from a run's calls: cost summed, the full prompt kept as a ``prompt`` file."""
        text = PromptCompiler.full_text(sent).encode("utf-8")
        sha = self.services.store.put_bytes(text)
        last = results[-1]
        reasons = [r.fallback_reason for r in results if r.fallback_reason]
        return VersionDraft(
            payload=payload,
            files=[
                {
                    "role": "prompt",
                    "path": f"blobs/{sha}",
                    "sha256": sha,
                    "mime": "text/plain; charset=utf-8",
                    "duration_s": None,
                    "w": None,
                    "h": None,
                }
            ],
            intent=ctx.intent,
            compiled=ctx.compiled,
            compiled_overridden=ctx.compiled_overridden,
            model_key=last.model_key,
            where=last.where,
            seed=ctx.seed,
            params={"mode": ctx.mode, "calls": len(results)},
            cost_usd=round(sum(r.cost_usd for r in results), 6),
            job_id=ctx.job_id,
            fallback_reason=reasons[0] if reasons else None,
            dependencies=list(inputs.deps),
        )

    def request(
        self,
        messages: Sequence[dict[str, Any]],
        seed: int | None,
        task: str = "run",
        max_tokens: int | None = None,
    ) -> ModelRequest:
        return ModelRequest(
            kind="llm",
            messages=list(messages),
            json_mode=True,
            max_tokens=max_tokens or self.max_tokens,
            seed=seed,
            params={"stream": True},
            meta={"component": self.id, "task": task},
        )

    async def call_json(
        self,
        ctx: RunContext,
        messages: Sequence[dict[str, Any]],
        schema: type[BaseModel],
        episode_id: str | None = None,
        *,
        task: str = "run",
        max_tokens: int | None = None,
    ) -> CallResult:
        """One validated JSON answer: cached, else asked (and asked again once with errors)."""
        req = self.request(messages, ctx.seed, task, max_tokens)
        key = request_key(ctx.model_key, req, schema)
        cached = await self._cache_get(key, schema)
        if cached is not None:
            where = self.services.registry.spec(ctx.model_key).where
            return CallResult(cached, ctx.model_key, where, 0.0, None, cached=True)

        cost = 0.0
        model = ctx.model_key
        reason: str | None = None
        text = ""
        errors = ""
        for _ in range(2):
            routed = await self.services.router.call(
                self.id,
                req,
                self._call_ctx(ctx, episode_id),
                model=model,
                fallback_reason=ctx.fallback_reason,
            )
            cost += routed.cost_usd
            model = routed.model_key  # a retry stays on the model that answered
            reason = reason or version_fallback(routed.fallback_reason)
            text = routed.text or ""
            data, errors = parse_json(routed.json, text, schema)
            if data is not None:
                await self._cache_put(key, model, data)
                return CallResult(data, model, routed.where, cost, reason)
            req = self.request(
                [
                    *req.messages,  # type: ignore[misc]
                    {"role": "assistant", "content": text},
                    {"role": "user", "content": self.services.compiler.fix_json(errors)},
                ],
                ctx.seed,
                task,
                max_tokens,
            )
        raw = self.services.store.put_bytes(text.encode("utf-8"))
        raise ComponentError("invalid_output", raw=raw, errors=errors[:500])

    def estimate(self, inputs: Inputs, compiled: str, model: str) -> Estimate:
        """What the next run costs on ``model``: one request by default (an upper bound, as
        the answer is priced at ``max_tokens``)."""
        messages = self.services.compiler.messages(compiled, inputs.blocks)
        return self.services.registry.get(model).estimate(self.request(messages, None))

    # ------------------------------------------------------------------ helpers

    def _call_ctx(self, ctx: RunContext, episode_id: str | None) -> CallContext:
        chars = 0
        last = 0.0

        async def on_delta(piece: str) -> None:
            nonlocal chars, last
            chars += len(piece)
            now = time.monotonic()
            if ctx.progress is not None and now - last >= 1.0:
                last = now
                await ctx.progress({"chars": chars})

        return CallContext(
            component_id=self.id,
            series_id=ctx.product.series_id,
            episode_id=episode_id,
            product_id=ctx.product.id,
            job_id=ctx.job_id,
            attempt=ctx.attempt,
            is_switch=ctx.mode == "switch",
            confirmed_usd=ctx.confirmed_usd,
            on_delta=on_delta,
        )

    async def _cache_get(self, key: str, schema: type[BaseModel]) -> BaseModel | None:
        async with self.services.db.session() as session:
            row = await session.get(LlmCache, key)
        if row is None:
            return None
        try:
            return schema.model_validate(row.value_json)
        except ValidationError:
            return None

    async def _cache_put(self, key: str, model: str, data: BaseModel) -> None:
        async with self.services.db.session() as session:
            if await session.get(LlmCache, key) is None:
                session.add(
                    LlmCache(key=key, model_key=model, value_json=data.model_dump(mode="json"))
                )
                await session.commit()


class ComponentRegistry:
    def __init__(self, services: Services) -> None:
        self.services = services
        self._components: dict[str, Component] = {}

    def add(self, component: Component) -> Component:
        self._components[component.id] = component
        for task, responder in component.mock_responders().items():
            self.services.registry.add_mock_responder(component.id, task, responder)
        return component

    def get(self, component_id: str) -> Component | None:
        return self._components.get(component_id)

    def all(self) -> list[Component]:
        return list(self._components.values())
