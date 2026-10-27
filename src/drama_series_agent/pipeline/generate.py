"""Generate step (M5 step 8; prototype Generate.dc.html): the auto rules over the take wall and
the run log.

**Rules** (``GET/PUT /series/{id}/generate-rules``) are per series, kept in ``app_setting``
under ``generate.rules.<series id>``; a field nobody set reads the config: ``takes_per_shot`` is
the video component's ``candidates``, ``qa_retry_max`` the fallback default ``qa_fail_n`` (read
by M6's QA reruns), ``shot_cap_usd`` the config's ``shot_cap_usd`` (``modelhub/budget.py``), and
``thresholds`` the QA component's, read-only here.

**Run log** (``GET /episodes/{id}/generate-log``) is worked out on read from the video products
of the episode's shots: each take (a version) is a line, a take made by a fallback gets the
fallback's line before it, and the jobs still running, waiting for a yes or failed get one each.
No table of its own.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from drama_series_agent.core.config import get_config
from drama_series_agent.core.models_db import (
    AppSetting,
    Episode,
    Job,
    Product,
    ProductVersion,
    Shot,
    utcnow,
)

VIDEO_COMPONENT = "vid"
QA_COMPONENT = "qa"
# Versions that are takes; ``pick`` / ``edit`` / ``import`` are not generation runs.
TAKE_ORIGINS = ("run", "rerun", "switch", "fallback")
LOGGED_JOB_STATES = ("running", "waiting_confirm", "failed")


class QaThresholds(BaseModel):
    face_sim: float
    syncnet_conf: float
    cer_max: float


class GenerateRules(BaseModel):
    takes_per_shot: int = Field(ge=1, le=6)
    qa_retry_max: int = Field(ge=0, le=5)
    shot_cap_usd: float = Field(ge=0)
    thresholds: QaThresholds


class GenerateRulesPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    takes_per_shot: int | None = Field(default=None, ge=1, le=6)
    qa_retry_max: int | None = Field(default=None, ge=0, le=5)
    shot_cap_usd: float | None = Field(default=None, ge=0)


class LogMessage(BaseModel):
    code: str
    params: dict[str, str | int | float] = Field(default_factory=dict)


class GenerateLogEntry(BaseModel):
    id: str
    at: datetime
    shot_label: str
    message: LogMessage
    warn: bool


def _key(series_id: str) -> str:
    return f"generate.rules.{series_id}"


def default_rules() -> GenerateRules:
    cfg = get_config().components
    try:
        takes = cfg.component(VIDEO_COMPONENT).candidates or 1
    except KeyError:
        takes = 1
    try:
        raw = getattr(cfg.component(QA_COMPONENT), "thresholds", None) or {}
    except KeyError:
        raw = {}
    return GenerateRules(
        takes_per_shot=takes,
        qa_retry_max=cfg.fallback_defaults.qa_fail_n,
        shot_cap_usd=cfg.shot_cap_usd,
        thresholds=QaThresholds(
            face_sim=float(raw.get("face_sim", 0.75)),
            syncnet_conf=float(raw.get("syncnet_conf", 6)),
            cer_max=float(raw.get("cer_max", 0.1)),
        ),
    )


async def load_rules(session: AsyncSession, series_id: str) -> GenerateRules:
    row = await session.get(AppSetting, _key(series_id))
    saved = GenerateRulesPatch.model_validate(row.value_json) if row else GenerateRulesPatch()
    return default_rules().model_copy(update=saved.model_dump(exclude_none=True))


async def save_rules(
    session: AsyncSession, series_id: str, patch: GenerateRulesPatch
) -> GenerateRules:
    """Merge ``patch`` into what the series saved (the UI changes one field at a time)."""
    row = await session.get(AppSetting, _key(series_id)) or AppSetting(key=_key(series_id))
    row.value_json = {**row.value_json, **patch.model_dump(exclude_none=True)}
    row.updated_at = utcnow()
    session.add(row)
    await session.commit()
    return await load_rules(session, series_id)


async def generate_log(
    session: AsyncSession, episode_id: str, *, timeout_minutes: int
) -> list[GenerateLogEntry]:
    """The episode's run log, oldest first. ``timeout_minutes``: the local time limit a
    timeout fallback line names."""
    episode = await session.get(Episode, episode_id)
    shots = (
        await session.exec(
            select(Shot).where(Shot.episode_id == episode_id, col(Shot.retired).is_(False))
        )
    ).all()
    n = episode.idx if episode is not None else 0
    labels = {s.id: f"{n}-{s.idx:02d}" for s in shots}
    products = (
        await session.exec(
            select(Product).where(
                Product.owner_type == "shot",
                col(Product.owner_id).in_(list(labels)),
                Product.component_id == VIDEO_COMPONENT,
            )
        )
    ).all()
    label_of = {p.id: labels[p.owner_id] for p in products}
    versions = (
        await session.exec(
            select(ProductVersion).where(
                col(ProductVersion.product_id).in_(list(label_of)),
                col(ProductVersion.origin).in_(TAKE_ORIGINS),
            )
        )
    ).all()
    jobs = (
        await session.exec(
            select(Job).where(
                col(Job.product_id).in_(list(label_of)), col(Job.state).in_(LOGGED_JOB_STATES)
            )
        )
    ).all()

    out: list[GenerateLogEntry] = []
    for v in versions:
        label = label_of[v.product_id]
        model = v.model_key or ""
        if v.fallback_reason in ("timeout", "error"):
            params: dict[str, str | int | float] = {"model": model}
            if v.fallback_reason == "timeout":
                params["minutes"] = timeout_minutes
            out.append(
                _entry(
                    f"fb-{v.id}",
                    v.created_at,
                    label,
                    f"fallback_{v.fallback_reason}",
                    params,
                    warn=True,
                )
            )
        out.append(_take(v, label))
    for job in jobs:
        label = label_of[job.product_id or ""]
        model = str(job.params_json.get("model_key", ""))
        if job.state == "running":
            at = job.started_at or job.created_at
            out.append(_entry(f"job-{job.id}", at, label, "started", {"model": model}))
        elif job.state == "waiting_confirm":
            cost = float(job.est_cost_usd or 0)
            out.append(
                _entry(
                    f"job-{job.id}",
                    job.created_at,
                    label,
                    "waiting",
                    {"model": model, "cost_usd": round(cost, 4)},
                    warn=True,
                )
            )
        else:
            at = job.finished_at or job.created_at
            error = str((job.error_json or {}).get("code", ""))
            out.append(
                _entry(
                    f"job-{job.id}",
                    at,
                    label,
                    "failed",
                    {"model": model, "error": error},
                    warn=True,
                )
            )
    out.sort(key=lambda e: (e.at, e.id))
    return out


def _take(v: ProductVersion, label: str) -> GenerateLogEntry:
    """``take`` / ``switch`` / ``final``; once QA has run (M6) ``take_pass`` / ``take_fail``
    and ``switch_pass`` / ``switch_fail``."""
    prefix = "final" if v.stage == "final" else "switch" if v.origin == "switch" else "take"
    checks: list[dict[str, Any]] = list((v.qa_json or {}).get("checks") or [])
    fails = sum(1 for c in checks if c.get("ok") is False)
    code = prefix
    if v.qa_json is not None and prefix != "final":
        code = f"{prefix}_{'fail' if fails else 'pass'}"
    params: dict[str, str | int | float] = {
        "model": v.model_key or "",
        "take": v.n,
        "cost_usd": round(v.cost_usd, 4),
        "fails": fails,
    }
    return _entry(
        f"v-{v.id}", v.created_at, label, code, params, warn=fails > 0 or v.origin == "switch"
    )


def _entry(
    entry_id: str,
    at: datetime,
    label: str,
    code: str,
    params: dict[str, str | int | float],
    *,
    warn: bool = False,
) -> GenerateLogEntry:
    return GenerateLogEntry(
        id=entry_id,
        at=at,
        shot_label=label,
        message=LogMessage(code=code, params=params),
        warn=warn,
    )
