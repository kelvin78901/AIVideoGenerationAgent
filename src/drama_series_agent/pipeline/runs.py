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
from dataclasses import replace
from typing import Any, Literal

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from drama_series_agent.core.config import Resolved, get_config
from drama_series_agent.core.events import EventBus, EventType
from drama_series_agent.core.jobs import (
    TERMINAL,
    JobContext,
    JobError,
    JobNeedsConfirm,
    JobQueue,
)
from drama_series_agent.core.models_db import Episode, Job, Product, ProductVersion, Series
from drama_series_agent.modelhub.adapters.base import ModelError
from drama_series_agent.modelhub.budget import Budget, cap_of
from drama_series_agent.modelhub.router import NeedsConfirm, Router
from drama_series_agent.pipeline.component import (
    Component,
    ComponentError,
    ComponentRegistry,
    Inputs,
    RunContext,
)
from drama_series_agent.pipeline.errors import PipelineError
from drama_series_agent.pipeline.generate import load_rules
from drama_series_agent.pipeline.products import ProductService, require_product
from drama_series_agent.pipeline.schema import EstimateOut, ProductOut, PromptOut

PRODUCT_RUN = "product.run"
Mode = Literal["run", "rerun", "switch"]
Where = Literal["local", "api"]


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
        budget: Budget,
    ) -> None:
        self.components = components
        self.products = products
        self.jobs = jobs
        self.bus = bus
        self.budget = budget
        self.services = components.services
        products.describer = self.describe
        jobs.register(PRODUCT_RUN, self._handle)

    # ------------------------------------------------------------------ helpers

    def _component(self, component_id: str) -> Component:
        comp = self.components.get(component_id)
        if comp is None:
            raise PipelineError(409, "component_not_ready", id=component_id)
        return comp

    async def _primary(self, settings: Resolved, where: Where | None = None) -> str:
        try:
            return Router.primary_model(settings, where)
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

    # ------------------------------------------------------------------ series products

    async def ensure_series_products(self, series_id: str) -> None:
        """The series-level products (设定提取 …) exist once the series has a novel, and each
        episode's (剧本化) once it is in the adopted plan (a plan made before the component)."""
        for comp in self.components.all():
            if comp.owner_type == "series":
                await self.products.ensure(
                    series_id=series_id,
                    owner_type="series",
                    owner_id=series_id,
                    slot=comp.slot,
                    component_id=comp.id,
                )
        per_episode = [c for c in self.components.all() if c.owner_type == "episode"]
        if not per_episode:
            return
        async with self.services.db.session() as session:
            query = select(Episode.id).where(
                Episode.series_id == series_id, col(Episode.retired).is_(False)
            )
            episode_ids = list((await session.exec(query)).all())
        for episode_id in episode_ids:
            for comp in per_episode:
                await self.products.ensure(
                    series_id=series_id,
                    owner_type="episode",
                    owner_id=episode_id,
                    slot=comp.slot,
                    component_id=comp.id,
                )

    async def ensure_all_series_products(self) -> None:
        """At startup: series whose novel was imported before a component existed."""
        async with self.services.db.session() as session:
            query = select(Product.series_id).where(Product.slot == "novel")
            series_ids = list((await session.exec(query)).all())
        for series_id in series_ids:
            await self.ensure_series_products(series_id)

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
        intent: str | None = None
        comp = self.components.get(product.component_id)
        async with self.services.db.session() as session:
            lang = await self._lang(session, product.series_id)
            try:
                inputs = await comp.inputs(session, product) if comp is not None else None
            except (LookupError, PipelineError, ComponentError):
                inputs = None  # upstream not ready yet: no price to show
            if not product.prompt_json:
                intent = (
                    await comp.default_intent(session, product, lang)
                    if comp is not None
                    else compiler.default_intent(product.component_id, lang)
                )
        # Outside the session: choosing opens its own (the rules table). Nested, every page
        # that loads many products at once held one connection each while waiting for a
        # second, and the pool (15) ran dry for its 30 s timeout (CI's e2e hangs, M5).
        if comp is not None and inputs is not None:
            chosen = await comp.choose_model(
                product, inputs, model, settings, lang=lang, named=False, ask=False
            )
            model = chosen.model
        if intent is None:
            compiled = str((product.prompt_json or {}).get("compiled", ""))
        else:
            compiled = compiler.compile(product.component_id, intent, model)
            prompt = PromptOut(
                intent=intent, compiled=compiled, compiled_overridden=False, model_key=model
            )
        if comp is None or inputs is None:
            return prompt, None
        try:
            est = comp.estimate(inputs, compiled, model)
        except (LookupError, PipelineError, ComponentError):
            return prompt, None
        spec = self.services.registry.spec(model)
        return prompt, EstimateOut(
            model_key=model,
            where=spec.where,
            cost_usd=round(est.cost_usd, 4),
            seconds=est.seconds,
            priced=est.priced,
            final_usd=self._final_api_cost(comp, inputs, compiled, model),
        )

    def _final_api_cost(
        self, comp: Component, inputs: Inputs, compiled: str, model: str
    ) -> float | None:
        """What 「用 API 出终版」 of one take costs where the component has a ``final_api``."""
        try:
            final = get_config().components.component(comp.id).final_api
        except KeyError:
            return None
        if not final:
            return None
        inputs.params = {**inputs.params, "source_version_id": "-"}
        try:
            return round(comp.estimate(inputs, compiled, model).cost_usd, 4)
        except (LookupError, PipelineError, ComponentError, ModelError):
            return None

    async def final_cost(self, product: Product) -> float | None:
        """What 「用 API 出终版」 of a candidate product costs on its route's API model (M4: the
        keyframes 改画幅 redraws); None without an API model or before the upstream is ready."""
        comp = self.components.get(product.component_id)
        if comp is None:
            return None
        settings = await self.services.router.settings(product.component_id, item_of(product))
        try:
            model = Router.primary_model(settings, "api")
        except ModelError:
            return None
        async with self.services.db.session() as session:
            try:
                inputs = await comp.inputs(session, product)
            except (LookupError, PipelineError, ComponentError):
                return None
        inputs.params = {"source_version_id": product.current_version_id or "-"}
        compiled = self.services.compiler.compile(product.component_id, "", model)
        return round(comp.estimate(inputs, compiled, model).cost_usd, 4)

    # ------------------------------------------------------------------ commands

    async def start(
        self,
        product_id: str,
        mode: Mode,
        *,
        model: str | None = None,
        intent: str | None = None,
        compiled: str | None = None,
        count: int | None = None,
        cascade: dict[str, str] | None = None,
        where: Where | None = None,
        params: dict[str, Any] | None = None,
    ) -> Job:
        """Queue a run. ``cascade`` (``{id, origin}``): one rerun of 确认并同步
        (``pipeline/cascade.py``), adopted when it succeeds. ``where``: ``api`` is hybrid
        mode's 「用 API 出终版」 (SPEC 7.3; the route's API model). ``params``: what the
        component reads besides the prompt (``Inputs.params``). ``count``: versions to make,
        the component's ``run_count`` when None; the estimate covers them all."""
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
            starting = None if p.prompt_json else await comp.default_intent(session, p, lang)
            # An API final is one version from one draft.
            final = bool((params or {}).get("source_version_id"))
            count = count or (1 if final else await comp.run_count(session, p))
            # Work on a shot also meets the shot's cap (generate rules).
            shot = (
                (p.owner_id, (await load_rules(session, p.series_id)).shot_cap_usd)
                if p.owner_type == "shot"
                else None
            )
        settings = await router.settings(comp.id, item_of(p))
        if mode == "switch":
            base = current.model_key if current and current.model_key else None
            base = base or await self._primary(settings)
            target = model or next_alternative(settings, base)
            if target is None:
                raise PipelineError(409, "no_alternative", id=p.id)
        else:
            target = model or await self._primary(settings, where)
        self._known(target)
        params = dict(params or {})
        async with self.services.db.session() as session:
            inputs = await comp.inputs(session, p)
        inputs.params = params
        chosen = await comp.choose_model(
            p, inputs, target, settings, lang=lang, named=model is not None or mode == "switch",
            ask=True,
        )  # fmt: skip
        target = chosen.model
        if chosen.select is not None:
            params["select"] = chosen.select

        saved = PromptOut.model_validate(p.prompt_json) if p.prompt_json else None
        # A plain rerun keeps a hand-edited compiled layer; a new intent or another model
        # compiles afresh (DECISIONS M0.5 第 4 步).
        keep = mode != "switch" and intent is None and compiled is None
        kept = saved.compiled if keep and saved is not None and saved.compiled_overridden else None
        if intent is None:
            intent = saved.intent if saved else (starting or "")
        overridden = compiled is not None or kept is not None
        compiled = compiled if compiled is not None else kept
        if compiled is None:
            compiled = self._compile(comp.id, intent, target)
        prompt = PromptOut(
            intent=intent, compiled=compiled, compiled_overridden=overridden, model_key=target
        )
        await self.products.set_prompt(p.id, prompt.model_dump())

        one = comp.estimate(inputs, compiled, target)
        estimate = replace(one, cost_usd=one.cost_usd * count, seconds=one.seconds * count)
        # Hard rule 6: over the per-call cap or what is left of the episode, or no known
        # price → ask first.
        verdict = await self.budget.before_enqueue(
            estimate.cost_usd,
            cap=cap_of(settings),
            episode_id=inputs.episode_id,
            priced=estimate.priced,
            shot=shot,
        )
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
                **({"params": params} if params else {}),
                **({"cascade": dict(cascade)} if cascade else {}),
                **({} if verdict.ok else {"confirm": verdict.params()}),
            },
            series_id=p.series_id,
            episode_id=inputs.episode_id,
            product_id=p.id,
            component_id=comp.id,
            est_cost_usd=round(estimate.cost_usd, 6),
            wait_for_confirm=not verdict.ok,
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
        except NeedsConfirm as exc:
            raise await self._ask_fallback(product_id, exc) from exc
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
        inputs.params = dict(params.get("params") or {})
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
                fallback_reason=params.get("fallback_reason"),
                select=inputs.params.get("select"),
            )
            draft = await comp.run(ctx, inputs)
            origin = "fallback" if draft.fallback_reason else mode
            # An API final's parent is the draft it started from (SPEC 7.3).
            parent = inputs.params.get("source_version_id") or (base.id if base else None)
            last = await self.products.append(
                p.id,
                draft,
                origin=origin,
                parent_version_id=parent,
                adopt=True if comp.adopt_every_run else None if comp.auto_adopt else False,
            )
        assert last is not None
        spec = self.services.registry.spec(last.model_key or model)
        # A line's audio is one of dozens dubbed at once: no toast for each.
        if p.slot not in self.products.quiet_slots:
            await self.bus.publish(
                EventType.TOAST,
                {
                    "level": "success",
                    "code": "version_created",
                    "params": {"n": last.n, "model": spec.display},
                },
            )
        return {"version_id": last.id, "n": last.n, "model_key": last.model_key}

    async def _ask_fallback(self, product_id: str, exc: NeedsConfirm) -> JobNeedsConfirm:
        """``notify: ask``: the job waits; a yes reruns it on the fallback model."""
        async with self.services.db.session() as session:
            p = await require_product(session, product_id)
            comp = self._component(p.component_id)
            inputs = await comp.inputs(session, p)
            job = await session.get(Job, p.running_job_id) if p.running_job_id else None
        inputs.params = dict((job.params_json if job else {}).get("params") or {})
        compiled = str((p.prompt_json or {}).get("compiled", ""))
        estimate = comp.estimate(inputs, compiled, exc.fallback)
        est = estimate.cost_usd
        return JobNeedsConfirm(
            {
                "model_key": exc.fallback,
                "fallback_reason": "timeout" if exc.reason == "timeout" else "error",
                "confirm": {
                    "reason": "fallback",
                    "failed_model": exc.failed,
                    "error": exc.reason,
                    "estimate_usd": round(est, 4),
                    "limit_usd": None,
                    "priced": estimate.priced,
                },
            },
            est_cost_usd=round(est, 6),
        )

    async def _failed(self, product_id: str, code: str) -> None:
        await self.products.finish_run(product_id, ok=False)
        await self.bus.publish(
            EventType.TOAST, {"level": "error", "code": "run_failed", "params": {"error": code}}
        )
