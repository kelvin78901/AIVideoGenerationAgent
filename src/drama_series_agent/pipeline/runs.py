"""Running a product (SPEC 7.4): 重跑 / 不满意换一个 / 改提示词, as ``product.run`` jobs.

- **run / rerun**: the component's configured route (``primary_model``), a new seed.
- **switch**: the next model in ``alt_order`` after the one that made the version on screen,
  or the one the user picked; the compiled layer is always rebuilt for the target model.
- A hand-edited compiled layer is kept by a plain rerun (DECISIONS M0.5 第 4 步).

The prompt the run uses is saved on the product (what PromptEditor shows next) and copied into
the job's params, so editing the prompt while the job waits does not change that run.
"""

from __future__ import annotations

import asyncio
import random
from typing import Any, Literal

from sqlmodel.ext.asyncio.session import AsyncSession

from drama_series_agent.core.config import Resolved
from drama_series_agent.core.events import EventBus, EventType
from drama_series_agent.core.jobs import TERMINAL, JobContext, JobError, JobQueue
from drama_series_agent.core.models_db import Job, Product, ProductVersion, Series
from drama_series_agent.modelhub.adapters.base import ModelError
from drama_series_agent.modelhub.router import Router
from drama_series_agent.pipeline.component import (
    Component,
    ComponentError,
    ComponentRegistry,
    RunContext,
)
from drama_series_agent.pipeline.errors import PipelineError
from drama_series_agent.pipeline.products import ProductService, require_product
from drama_series_agent.pipeline.schema import EstimateOut, ProductOut, PromptOut

PRODUCT_RUN = "product.run"
Mode = Literal["run", "rerun", "switch"]


def item_of(product: Product) -> str | None:
    """Per-item config (SPEC 7.1) applies to shots and assets."""
    return (
        f"{product.owner_type}:{product.owner_id}"
        if product.owner_type in ("shot", "asset")
        else None
    )


def next_alternative(settings: Resolved, base: str) -> str | None:
    """「不满意换一个」: the model after ``base`` in ``alt_order`` (wrapping), never ``base``."""
    order = [m for m in settings.values.get("alt_order") or [] if isinstance(m, str)]
    if base in order:
        i = order.index(base)
        order = order[i + 1 :] + order[:i]
    return next((m for m in order if m != base), None)


class RunService:
    def __init__(
        self,
        components: ComponentRegistry,
        products: ProductService,
        jobs: JobQueue,
        bus: EventBus,
    ) -> None:
        self.components = components
        self.products = products
        self.jobs = jobs
        self.bus = bus
        self.services = components.services
        products.describer = self.describe
        jobs.register(PRODUCT_RUN, self._handle)

    # ------------------------------------------------------------------ helpers

    def _component(self, component_id: str) -> Component:
        comp = self.components.get(component_id)
        if comp is None:
            raise PipelineError(409, "component_not_ready", id=component_id)
        return comp

    async def _primary(self, settings: Resolved) -> str:
        try:
            return Router.primary_model(settings)
        except ModelError as exc:
            raise PipelineError(409, exc.code) from None

    def _known(self, model: str) -> None:
        try:
            self.services.registry.spec(model)
        except ModelError:
            raise PipelineError(422, "unknown_model", key=model) from None

    async def _lang(self, session: AsyncSession, series_id: str) -> str:
        series = await session.get(Series, series_id)
        return series.ui_lang if series is not None else "zh-CN"

    def _compile(self, component_id: str, intent: str, model: str) -> str:
        try:
            return self.services.compiler.compile(component_id, intent, model)
        except KeyError:
            raise PipelineError(409, "component_not_ready", id=component_id) from None

    async def _active_job(self, session: AsyncSession, product: Product) -> Job | None:
        if not product.running_job_id:
            return None
        job = await session.get(Job, product.running_job_id)
        return job if job is not None and job.state not in TERMINAL else None

    # ------------------------------------------------------------------ reads

    async def describe(self, product: Product) -> tuple[PromptOut | None, EstimateOut | None]:
        """The default prompt of a product that never ran, and the next run's estimate."""
        compiler = self.services.compiler
        if not compiler.has(product.component_id):
            return None, None
        settings = await self.services.router.settings(product.component_id, item_of(product))
        try:
            model = Router.primary_model(settings)
        except ModelError:
            return None, None
        prompt = None
        async with self.services.db.session() as session:
            lang = await self._lang(session, product.series_id)
            if product.prompt_json:
                compiled = str(product.prompt_json.get("compiled", ""))
            else:
                intent = compiler.default_intent(product.component_id, lang)
                compiled = compiler.compile(product.component_id, intent, model)
                prompt = PromptOut(
                    intent=intent, compiled=compiled, compiled_overridden=False, model_key=model
                )
            comp = self.components.get(product.component_id)
            if comp is None:
                return prompt, None
            try:
                est = await comp.estimate(session, product, compiled, model)
            except (LookupError, PipelineError, ComponentError):
                return prompt, None  # upstream not ready yet: no price to show
        spec = self.services.registry.spec(model)
        return prompt, EstimateOut(
            model_key=model, where=spec.where, cost_usd=round(est.cost_usd, 4), seconds=est.seconds
        )

    # ------------------------------------------------------------------ commands

    async def start(
        self,
        product_id: str,
        mode: Mode,
        *,
        model: str | None = None,
        intent: str | None = None,
        compiled: str | None = None,
        count: int = 1,
    ) -> Job:
        router = self.services.router
        async with self.services.db.session() as session:
            p = await require_product(session, product_id)
            if await self._active_job(session, p) is not None:
                raise PipelineError(409, "product_busy", id=p.id)
            comp = self._component(p.component_id)
            current = (
                await session.get(ProductVersion, p.current_version_id)
                if p.current_version_id
                else None
            )
            lang = await self._lang(session, p.series_id)
        settings = await router.settings(comp.id, item_of(p))
        if mode == "switch":
            base = current.model_key if current and current.model_key else None
            base = base or await self._primary(settings)
            target = model or next_alternative(settings, base)
            if target is None:
                raise PipelineError(409, "no_alternative", id=p.id)
        else:
            target = model or await self._primary(settings)
        self._known(target)

        saved = PromptOut.model_validate(p.prompt_json) if p.prompt_json else None
        # A plain rerun keeps a hand-edited compiled layer; a new intent or another model
        # compiles afresh (DECISIONS M0.5 第 4 步).
        keep = mode != "switch" and intent is None and compiled is None
        kept = saved.compiled if keep and saved is not None and saved.compiled_overridden else None
        if intent is None:
            intent = saved.intent if saved else self.services.compiler.default_intent(comp.id, lang)
        overridden = compiled is not None or kept is not None
        compiled = compiled if compiled is not None else kept
        if compiled is None:
            compiled = self._compile(comp.id, intent, target)
        prompt = PromptOut(
            intent=intent, compiled=compiled, compiled_overridden=overridden, model_key=target
        )
        await self.products.set_prompt(p.id, prompt.model_dump())

        async with self.services.db.session() as session:
            estimate = await comp.estimate(session, p, compiled, target)
        spec = self.services.registry.spec(target)
        queue = "gpu" if spec.where == "local" else f"api:{spec.provider_id}"
        job = await self.jobs.enqueue(
            PRODUCT_RUN,
            queue,
            {
                "product_id": p.id,
                "mode": mode,
                "model_key": target,
                "seed": random.randrange(1, 2**31),
                "base_version_id": current.id if current else None,
                "count": count,
                "intent": intent,
                "compiled": compiled,
                "compiled_overridden": overridden,
            },
            series_id=p.series_id,
            product_id=p.id,
            component_id=comp.id,
            est_cost_usd=round(estimate.cost_usd, 6),
        )
        await self.products.start_run(p.id, job.id)
        return job

    async def save_prompt(self, product_id: str, intent: str, compiled: str | None) -> ProductOut:
        """「只保存」: ``compiled`` None = compile from the intent for the saved / route model."""
        async with self.services.db.session() as session:
            p = await require_product(session, product_id)
        comp_id = p.component_id
        model = str((p.prompt_json or {}).get("model_key") or "")
        if not model:
            settings = await self.services.router.settings(comp_id, item_of(p))
            model = await self._primary(settings)
        text = compiled if compiled is not None else self._compile(comp_id, intent, model)
        prompt = PromptOut(
            intent=intent, compiled=text, compiled_overridden=compiled is not None, model_key=model
        )
        await self.products.set_prompt(p.id, prompt.model_dump())
        return await self.products.get(p.id)

    async def compile_preview(
        self, product_id: str, intent: str, model: str | None
    ) -> dict[str, str]:
        async with self.services.db.session() as session:
            p = await require_product(session, product_id)
        if model is None:
            model = str((p.prompt_json or {}).get("model_key") or "")
        if not model:
            settings = await self.services.router.settings(p.component_id, item_of(p))
            model = await self._primary(settings)
        self._known(model)
        return {"compiled": self._compile(p.component_id, intent, model), "model_key": model}

    # ------------------------------------------------------------------ the job

    async def _handle(self, jctx: JobContext) -> dict[str, Any]:
        job, params = jctx.job, jctx.params
        product_id = str(params["product_id"])
        try:
            result = await self._execute(jctx, product_id)
        except asyncio.CancelledError:
            await asyncio.shield(self.products.finish_run(product_id, ok=None))
            raise
        except (ComponentError, PipelineError) as exc:
            await self._failed(product_id, exc.code)
            raise JobError(exc.code, dict(exc.params)) from exc
        except ModelError as exc:
            if exc.retryable and job.attempt < job.max_attempts:
                raise JobError(exc.code, {"message": str(exc)}, retryable=True) from exc
            await self._failed(product_id, exc.code)
            raise JobError(exc.code, {"message": str(exc)}) from exc
        await self.products.finish_run(product_id, ok=True)
        return result

    async def _execute(self, jctx: JobContext, product_id: str) -> dict[str, Any]:
        job, params = jctx.job, jctx.params
        async with self.services.db.session() as session:
            p = await require_product(session, product_id)
            comp = self._component(p.component_id)
            base_id = params.get("base_version_id")
            base = await session.get(ProductVersion, base_id) if base_id else None
            lang = await self._lang(session, p.series_id)
            inputs = await comp.inputs(session, p)
        mode: str = str(params.get("mode", "run"))
        model = str(params["model_key"])
        last = None
        for i in range(int(params.get("count", 1))):
            ctx = RunContext(
                product=p,
                mode=mode,
                model_key=model,
                seed=int(params["seed"]) + i,
                intent=str(params.get("intent", "")),
                compiled=str(params.get("compiled", "")),
                compiled_overridden=bool(params.get("compiled_overridden", False)),
                lang=lang,
                job_id=job.id,
                attempt=job.attempt,
                base_version=base,
                progress=jctx.progress,
            )
            draft = await comp.run(ctx, inputs)
            origin = "fallback" if draft.fallback_reason else mode
            last = await self.products.append(
                p.id, draft, origin=origin, parent_version_id=base.id if base else None
            )
        assert last is not None
        spec = self.services.registry.spec(last.model_key or model)
        await self.bus.publish(
            EventType.TOAST,
            {
                "level": "success",
                "code": "version_created",
                "params": {"n": last.n, "model": spec.display},
            },
        )
        return {"version_id": last.id, "n": last.n, "model_key": last.model_key}

    async def _failed(self, product_id: str, code: str) -> None:
        await self.products.finish_run(product_id, ok=False)
        await self.bus.publish(
            EventType.TOAST, {"level": "error", "code": "run_failed", "params": {"error": code}}
        )
