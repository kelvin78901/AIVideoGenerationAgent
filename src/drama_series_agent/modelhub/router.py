"""``router.call()``: the single entry point for every model call (hard rule 1).

For one call it: resolves the component's settings (factory → project → component → item),
picks the model, estimates the cost, asks the budget guard, runs the adapter with a timeout,
stores output files by content hash, writes one ``model_call`` row per attempt and publishes
``cost.updated``. On error or timeout it falls back once to ``fallback.to`` (or the next model
in ``alt_order``) when the component allows it.

Budget limits (per call / shot / episode → ``waiting_confirm``) arrive in M2; until then the
guard only exposes the hook. ``qa_fail`` fallback arrives with QA in M6.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from drama_series_agent.core.capabilities import Capabilities
from drama_series_agent.core.config import Resolved, StudioConfig, get_config
from drama_series_agent.core.db import Database
from drama_series_agent.core.events import EventBus, EventType
from drama_series_agent.core.models_db import ModelCall, utcnow
from drama_series_agent.core.overrides import resolve_component
from drama_series_agent.core.storage import BlobStore
from drama_series_agent.modelhub import calllog
from drama_series_agent.modelhub.adapters.base import (
    CallContext,
    Estimate,
    ModelError,
    ModelRequest,
    ModelResult,
    ModelSpec,
)
from drama_series_agent.modelhub.pricing import cost_usd
from drama_series_agent.modelhub.registry import Registry

DEFAULT_API_TIMEOUT_S = 600.0


class BudgetGuard(Protocol):
    async def check(
        self, spec: ModelSpec, estimate: Estimate, settings: Resolved, ctx: CallContext
    ) -> None:
        """Raise ``BudgetExceeded`` to stop the call before any money is spent."""


class BudgetExceeded(ModelError):
    def __init__(self, estimate_usd: float, limit_usd: float, scope: str) -> None:
        super().__init__("budget_exceeded", f"{estimate_usd:.4f} > {limit_usd:.4f} ({scope})")
        self.estimate_usd = estimate_usd
        self.limit_usd = limit_usd
        self.scope = scope


class NoBudget:
    async def check(
        self, spec: ModelSpec, estimate: Estimate, settings: Resolved, ctx: CallContext
    ) -> None:
        return None


@dataclass
class StoredFile:
    role: str
    sha256: str
    mime: str
    w: int | None = None
    h: int | None = None
    duration_s: float | None = None


@dataclass
class RoutedResult:
    result: ModelResult
    model_key: str
    where: str
    call_id: int
    cost_usd: float
    is_fallback: bool = False
    fallback_reason: str | None = None
    files: list[StoredFile] = field(default_factory=list)

    @property
    def text(self) -> str | None:
        return self.result.text

    @property
    def json(self) -> Any:
        return self.result.json


class Router:
    def __init__(
        self,
        db: Database,
        bus: EventBus,
        registry: Registry,
        *,
        store: BlobStore | None = None,
        budget: BudgetGuard | None = None,
        config: Callable[[], StudioConfig] = get_config,
        api_timeout_s: float = DEFAULT_API_TIMEOUT_S,
        capabilities: Callable[[], Awaitable[Capabilities | None]] | None = None,
    ) -> None:
        self.db = db
        self.bus = bus
        self.registry = registry
        self.store = store or BlobStore()
        self.budget = budget or NoBudget()
        self._config = config
        self.api_timeout_s = api_timeout_s
        # What this machine can run locally (the setup scan); None = route as configured.
        self._capabilities = capabilities

    async def settings(self, component_id: str, item: str | None = None) -> Resolved:
        caps = await self._capabilities() if self._capabilities is not None else None
        async with self.db.session() as session:
            return await resolve_component(
                session, component_id, item=item, config=self._config(), caps=caps
            )

    @staticmethod
    def primary_model(settings: Resolved, where: Literal["local", "api"] | None = None) -> str:
        values = settings.values
        if values["mode"] == "off" and where is None:
            raise ModelError("component_off")  # e.g. 全本地 for a component with no local model
        mode = where or values["mode"]
        if mode == "hybrid":
            mode = "local"  # hybrid = local draft; the API final is an explicit where="api" call
        key = values["local_model"] if mode == "local" else values["api_model"]
        if not key:
            key = values["api_model"] or values["local_model"]
        if not key:
            raise ModelError("no_model_configured")
        return str(key)

    @staticmethod
    def fallback_model(settings: Resolved, tried: list[str], reason: str) -> str | None:
        fb = settings.values["fallback"]
        if not fb.get("enabled") or reason not in fb.get("on", []):
            return None
        target = fb.get("to")
        if target and target not in tried:
            return str(target)
        return next((m for m in settings.values.get("alt_order") or [] if m not in tried), None)

    async def call(
        self,
        component_id: str,
        req: ModelRequest,
        ctx: CallContext | None = None,
        *,
        model: str | None = None,
        item: str | None = None,
        where: Literal["local", "api"] | None = None,
    ) -> RoutedResult:
        ctx = ctx or CallContext(component_id=component_id)
        settings = await self.settings(component_id, item)
        key = model or self.primary_model(settings, where)
        self.registry.spec(key)  # unknown models fail fast, without a fallback
        try:
            return await self._attempt(component_id, key, req, ctx, settings, fallback_reason=None)
        except BudgetExceeded:
            raise
        except ModelError as exc:
            trigger = "timeout" if exc.code == "timeout" else "error"
            # One hop only: walking the whole alt_order on a bad day could multiply the spend.
            fallback = self.fallback_model(settings, [key], trigger)
            if fallback is None or fallback not in {s.key for s in self.registry.specs()}:
                raise
            return await self._attempt(
                component_id, fallback, req, ctx, settings, fallback_reason=exc.code
            )

    async def _attempt(
        self,
        component_id: str,
        key: str,
        req: ModelRequest,
        ctx: CallContext,
        settings: Resolved,
        *,
        fallback_reason: str | None,
    ) -> RoutedResult:
        adapter = self.registry.get(key)
        spec = adapter.spec
        estimate = adapter.estimate(req)
        await self.budget.check(spec, estimate, settings, ctx)

        timeout_s = (
            float(settings.values["fallback"].get("timeout_s") or 600)
            if spec.where == "local"
            else self.api_timeout_s
        )
        row = ModelCall(
            series_id=ctx.series_id,
            episode_id=ctx.episode_id,
            scene_id=ctx.scene_id,
            shot_id=ctx.shot_id,
            component_id=component_id,
            product_id=ctx.product_id,
            version_id=ctx.version_id,
            job_id=ctx.job_id,
            provider_id=spec.provider_id,
            model_key=spec.key,
            where=spec.where,
            is_fallback=fallback_reason is not None,
            fallback_reason=fallback_reason,
            is_switch=ctx.is_switch,
            attempt=ctx.attempt,
            queued_at=utcnow(),
            unit_prices_json=spec.pricing.snapshot(),
            status="error",
            billed=False,
        )
        row.started_at = utcnow()
        try:
            async with asyncio.timeout(timeout_s):
                result = await adapter.run(req, ctx)
        except TimeoutError:
            await self._log_failure(row, "timeout", "timeout", billed=False)
            raise ModelError("timeout", f"{key} timed out after {timeout_s:.0f}s") from None
        except asyncio.CancelledError:
            await asyncio.shield(self._log_failure(row, "canceled", "canceled", billed=False))
            raise
        except ModelError as exc:
            await self._log_failure(row, "error", exc.code, billed=exc.billed)
            raise
        except Exception as exc:
            await self._log_failure(row, "error", "adapter_crash", billed=False)
            raise ModelError("adapter_crash", str(exc)[:300]) from exc

        files = [self._store(f) for f in result.files]
        usage = result.usage
        row.finished_at = utcnow()
        row.status = "success"
        row.billed = True
        row.tokens_in = usage.tokens_in
        row.tokens_out = usage.tokens_out
        row.images = usage.images
        row.output_seconds = usage.output_seconds
        row.chars = usage.chars
        row.input_seconds = usage.input_seconds
        row.cost_usd = cost_usd(
            spec.pricing,
            usage,
            resolution=req.params.get("resolution"),
            rates=self._config().providers.currency_rates,
        )
        saved = await calllog.record(self.db, row)
        assert saved.id is not None
        await self.bus.publish(
            EventType.COST_UPDATED,
            {
                "series_id": ctx.series_id,
                "episode_id": ctx.episode_id,
                "component_id": component_id,
                "model_key": spec.key,
                "cost_usd": saved.cost_usd,
                "call_id": saved.id,
            },
        )
        return RoutedResult(
            result=result,
            model_key=spec.key,
            where=spec.where,
            call_id=saved.id,
            cost_usd=saved.cost_usd,
            is_fallback=fallback_reason is not None,
            fallback_reason=fallback_reason,
            files=files,
        )

    async def _log_failure(self, row: ModelCall, status: str, code: str, *, billed: bool) -> None:
        row.finished_at = utcnow()
        row.status = status
        row.error_code = code
        row.billed = billed
        await calllog.record(self.db, row)

    def _store(self, f: Any) -> StoredFile:
        if f.data is not None:
            sha = self.store.put_bytes(f.data)
        elif f.path is not None:
            sha = self.store.put_file(f.path)
        else:
            raise ModelError("invalid_output", "output file without data or path")
        return StoredFile(
            role=f.role, sha256=sha, mime=f.mime, w=f.w, h=f.h, duration_s=f.duration_s
        )
