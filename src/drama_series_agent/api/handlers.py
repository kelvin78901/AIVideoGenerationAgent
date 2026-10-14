"""Job handlers: the bridge from queued jobs to ``router.call()``."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from drama_series_agent.core.jobs import JobContext, JobError
from drama_series_agent.modelhub.adapters.base import CallContext, ModelError, ModelRequest

if TYPE_CHECKING:
    from drama_series_agent.api.state import StudioState

LLM_TEST = "dev.llm_test"


def register_handlers(state: StudioState) -> None:
    async def llm_test(ctx: JobContext) -> dict[str, Any]:
        params = ctx.params
        component_id = str(params.get("component_id", "script"))
        req = ModelRequest(
            kind="llm",
            messages=[{"role": "user", "content": str(params.get("prompt", "测试"))}],
            params={"mock_delay_s": float(params.get("delay_s", 3.0))},
        )
        call_ctx = CallContext(
            component_id=component_id,
            series_id=ctx.job.series_id,
            job_id=ctx.job.id,
            attempt=ctx.job.attempt,
        )
        try:
            routed = await state.router.call(component_id, req, call_ctx)
        except ModelError as exc:
            raise JobError(exc.code, {"message": str(exc)}, retryable=exc.retryable) from exc
        return {
            "text": routed.text,
            "model_key": routed.model_key,
            "where": routed.where,
            "cost_usd": routed.cost_usd,
            "call_id": routed.call_id,
            "is_fallback": routed.is_fallback,
        }

    state.jobs.register(LLM_TEST, llm_test)
