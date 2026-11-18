"""不达标自动重跑和兜底 (M6 step 4; plan D): what happens when a shot's takes fail QA.

Once the last QA job of a run's takes (one job's versions, a 「批」) has written, and none of
them passes:

1. only lip sync failed (on the best of them) → 口型修复 (step 7a; until then, a rerun);
2. fewer automatic reruns since the last run a person started than the series'
   ``qa_retry_max`` → the same model makes one more take (origin ``auto_qa_rerun``), told what
   failed (``fixes``, to its prompt);
3. that many reruns → the video route's fallback model (origin ``fallback``,
   ``fallback_reason: qa_fail``; ``notify: ask`` → it waits for a yes);
4. the fallback failed too, or there is none → stop: nothing more is spent, the run log says
   「需要你看」.

A person's own run (重跑 / 换一个 / 出一条) starts the count again. Each run is priced first
(``RunService.start``): an API one over what is left of the shot's cap waits for a yes (hard
rule 6). Nothing happens when a take of the batch passes, is not checked yet or could not be
checked (``qa_pass`` None), when the shot has a run going, or once a take is adopted or the
product locked (the person decided).

What was decided is kept on the take that decided it, ``qa_json.policy`` ``{action, job_id,
model}``, for the run log (``pipeline/generate.py``).

A finished take (2K 精修, later 口型修复 and 局部修复: ``params.finish``) is no take of a batch:
once checked (the first time; 「重新质检」 adopts nothing) it is adopted when the take it came
from is the adopted one, it fails nothing that take passed, and the product is not locked
(Kelvin 2026-11-14: asking for it is asking to use it; the take stays in the history). A check
the take failed already and was kept anyway does not count (Kelvin 2026-11-17: 不比原片差就采纳).
Otherwise it stays a candidate.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from loguru import logger
from sqlmodel import select

from drama_series_agent.core.jobs import TERMINAL
from drama_series_agent.core.models_db import Job, Product, ProductVersion
from drama_series_agent.modelhub.router import Router
from drama_series_agent.pipeline import redraw, takecheck
from drama_series_agent.pipeline.errors import PipelineError
from drama_series_agent.pipeline.generate import load_rules

if TYPE_CHECKING:
    from drama_series_agent.pipeline.runs import RunService

AUTO_RERUN = "auto_qa_rerun"
FINISH = "finish"  # ``params.finish`` {kind, version_id} (``components/up.py``)
QA_FAIL = "qa_fail"
# Versions that are takes of a run (a final, an upscale, a repair are not).
BATCH_ORIGINS = ("run", "rerun", "switch", "fallback", AUTO_RERUN)
Action = Literal["none", "wait", "lip", "rerun", "fallback", "stop"]


@dataclass
class Decision:
    action: Action
    model: str | None = None
    fixes: list[str] = field(default_factory=list)
    source: ProductVersion | None = None  # the take the next one answers (the best failed)


def is_take(v: ProductVersion) -> bool:
    return v.origin in BATCH_ORIGINS and v.stage != "final"


def is_finished(v: ProductVersion) -> bool:
    """A take finished from another (2K 精修 …: ``params.finish``)."""
    return isinstance((v.params_json or {}).get(FINISH), dict)


def automatic(v: ProductVersion) -> bool:
    """A take QA asked for: a rerun (also when it fell back on an error on its way), or the
    fallback QA made."""
    return (
        v.origin == AUTO_RERUN
        or (v.params_json or {}).get("auto") == AUTO_RERUN
        or v.fallback_reason == QA_FAIL
    )


def failing(version: ProductVersion) -> list[dict[str, Any]]:
    """The checks that fail the take (on, and not passed)."""
    return [
        c
        for c in (version.qa_json or {}).get("checks") or []
        if c.get("ok") is False and not c.get("off")
    ]


def worse(version: ProductVersion, source: ProductVersion) -> list[str]:
    """The checks ``version`` fails that ``source`` (the take it was finished from) did not."""
    had = {c["metric"] for c in failing(source)}
    return [c["metric"] for c in failing(version) if c["metric"] not in had]


FIX_LINES = {
    "face": "人物的脸要和参考图一样",
    "lipsync": "说台词时嘴型要对上声音",
    "speaker": "说话的声音要是参考音色",
}


def fix_lines(version: ProductVersion) -> list[str]:
    """What the next take's prompt is told: one line per failed check."""
    rows: list[str] = []
    for c in failing(version):
        metric = c["metric"]
        detail = c.get("detail") or {}
        if metric == "vlm":
            rows += redraw.failed_text(c, takecheck.LABELS).splitlines()
        elif metric == "ocr":
            want = "、".join(f"「{t}」" for t in detail.get("expected") or [])
            rows.append(f"- 画面上的字要一字不差：{want}")
        elif metric == "asr":
            rows.append(f"- 台词要一字不差：「{detail.get('expected') or ''}」")
        else:
            rows.append(f"- {FIX_LINES.get(metric, metric)}")
    return rows


def decide(versions: Sequence[ProductVersion], *, retry_max: int, fallback: str | None) -> Decision:
    """What to do about the newest batch of ``versions`` (one product's, any order)."""
    takes = sorted((v for v in versions if is_take(v)), key=lambda v: v.n)
    if not takes:
        return Decision("none")
    newest = takes[-1]
    batch = [v for v in takes if v.job_id == newest.job_id] if newest.job_id else [newest]
    if any(v.qa_json is None for v in batch):
        return Decision("wait")
    if any(v.qa_pass is not False for v in batch):
        return Decision("none")  # one passed, or could not be checked
    best = max(batch, key=lambda v: float((v.qa_json or {}).get("score") or 0))
    if {c["metric"] for c in failing(best)} == {"lipsync"}:
        return Decision("lip", best.model_key, source=best)
    manual = [i for i, v in enumerate(takes) if not automatic(v)]
    since = takes[manual[-1] + 1 :] if manual else takes
    reruns = len({v.job_id for v in since if automatic(v) and v.fallback_reason != QA_FAIL})
    if any(v.origin == "fallback" and v.fallback_reason == QA_FAIL for v in since):
        return Decision("stop", source=best)
    if reruns < retry_max:
        return Decision("rerun", best.model_key, fix_lines(best), best)
    if fallback is not None and fallback != best.model_key:
        return Decision("fallback", fallback, fix_lines(best), best)
    return Decision("stop", source=best)


class QaPolicy:
    def __init__(self, runs: RunService) -> None:
        self.runs = runs
        self.services = runs.services
        # Two QA jobs of one batch may end together: one decision at a time.
        self._lock = asyncio.Lock()

    async def after_check(self, version_id: str, *, first: bool = True) -> None:
        """After a version's QA: a take's batch decided, a finished take maybe adopted (on its
        first check only: 「重新质检」 later adopts nothing)."""
        async with self.services.db.session() as session:
            v = await session.get(ProductVersion, version_id)
        if v is None:
            return
        if is_finished(v):
            if first:
                await self.adopt_finished(v.id)
        elif is_take(v):
            await self.after_qa(v.product_id)

    async def adopt_finished(self, version_id: str) -> bool:
        """Adopt a checked finished take that replaces the adopted one (see the module doc)."""
        async with self.services.db.session() as session:
            v = await session.get(ProductVersion, version_id)
            if v is None or not is_finished(v):
                return False
            p = await session.get(Product, v.product_id)
            source = await session.get(ProductVersion, str(v.params_json[FINISH]["version_id"]))
        if p is None or source is None or v.qa_json is None:
            return False
        if p.locked_hash or p.adopted_version_id != source.id:
            return False
        if worse(v, source):
            return False
        try:
            await self.runs.products.adopt(v.id)
        except PipelineError as exc:  # locked meanwhile
            logger.info("finished take {} left a candidate: {}", v.id, exc.code)
            return False
        return True

    async def after_qa(self, product_id: str) -> Decision:
        async with self._lock:
            return await self._after_qa(product_id)

    async def _after_qa(self, product_id: str) -> Decision:
        async with self.services.db.session() as session:
            product = await session.get(Product, product_id)
            if product is None or product.adopted_version_id or product.locked_hash:
                return Decision("none")
            if product.running_job_id is not None:
                job = await session.get(Job, product.running_job_id)
                if job is not None and job.state not in TERMINAL:
                    return Decision("none")
            versions = (
                await session.exec(
                    select(ProductVersion).where(ProductVersion.product_id == product_id)
                )
            ).all()
            rules = await load_rules(session, product.series_id)
        from drama_series_agent.pipeline.runs import item_of

        settings = await self.services.router.settings(product.component_id, item_of(product))
        takes = [v for v in versions if is_take(v)]
        if not takes:
            return Decision("none")
        newest = max(takes, key=lambda v: v.n)
        fallback = Router.fallback_model(settings, [newest.model_key or ""], QA_FAIL)
        decision = decide(versions, retry_max=rules.qa_retry_max, fallback=fallback)
        if decision.action in ("none", "wait"):
            return decision
        if decision.action == "lip":  # 口型修复 comes with step 7a; a rerun until then
            assert decision.source is not None
            decision = Decision(
                "rerun", decision.model, fix_lines(decision.source), decision.source
            )
        job_id: str | None = None
        try:
            if decision.action == "rerun":
                job = await self.runs.start(
                    product_id,
                    "rerun",
                    model=decision.model,
                    count=1,
                    params={"fixes": decision.fixes},
                    origin=AUTO_RERUN,
                )
                job_id = job.id
            elif decision.action == "fallback":
                ask = settings.values["fallback"].get("notify") == "ask"
                assert decision.model is not None
                job = await self.runs.start(
                    product_id,
                    "rerun",
                    model=decision.model,
                    count=1,
                    params={"fixes": decision.fixes},
                    fallback_reason=QA_FAIL,
                    ask=self._confirm(newest) if ask else None,
                )
                job_id = job.id
        except PipelineError as exc:  # a run started meanwhile, a component off …
            logger.info("QA left {} as it is: {}", product_id, exc.code)
            return Decision("none")
        assert decision.source is not None
        await self._note(decision.source.id, decision, job_id)
        return decision

    def _confirm(self, failed: ProductVersion) -> dict[str, Any]:
        """What the card asking for the fallback says (the estimate is filled in by ``start``)."""
        return {"reason": "fallback", "failed_model": failed.model_key, "error": QA_FAIL}

    async def _note(self, version_id: str, decision: Decision, job_id: str | None) -> None:
        async with self.services.db.session() as session:
            v = await session.get(ProductVersion, version_id)
            if v is None:
                return
            v.qa_json = {
                **(v.qa_json or {}),
                "policy": {"action": decision.action, "job_id": job_id, "model": decision.model},
            }
            session.add(v)
            await session.commit()
