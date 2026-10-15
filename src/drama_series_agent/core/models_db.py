"""SQLModel tables (SPEC 4.3, 10). Each milestone adds its own tables with a new migration.

All timestamps are timezone-aware UTC with millisecond precision.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Column, DateTime, Dialect, Index, UniqueConstraint
from sqlalchemy.types import TypeDecorator
from sqlmodel import Field, SQLModel


class UtcDateTime(TypeDecorator[datetime]):
    """SQLite drops tzinfo; store UTC and hand back aware datetimes."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime; use utcnow()")
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def utcnow() -> datetime:
    now = datetime.now(UTC)
    return now.replace(microsecond=now.microsecond // 1000 * 1000)


def new_id() -> str:
    return uuid.uuid4().hex


def _ts(*, nullable: bool = True, index: bool = False) -> Any:
    return Field(
        default=None,
        sa_column=Column(UtcDateTime(), nullable=nullable, index=index),
    )


def _json(default: Any = None) -> Any:
    if callable(default):
        return Field(default_factory=default, sa_column=Column(JSON, nullable=False))
    return Field(default=default, sa_column=Column(JSON, nullable=True))


class Job(SQLModel, table=True):
    __tablename__ = "job"
    __table_args__ = (Index("ix_job_queue_state", "queue", "state", "priority"),)

    id: str = Field(default_factory=new_id, primary_key=True)
    series_id: str | None = Field(default=None, index=True)
    product_id: str | None = Field(default=None, index=True)
    component_id: str | None = None
    kind: str
    queue: str  # gpu / api:<provider> / cpu
    state: str = Field(default="queued", index=True)
    priority: int = 0  # higher runs first
    attempt: int = 0
    max_attempts: int = 3
    params_json: dict[str, Any] = _json(dict)
    result_json: dict[str, Any] | None = _json()
    error_json: dict[str, Any] | None = _json()
    depends_on_json: list[str] = _json(list)
    est_cost_usd: float | None = None
    fallback_from_job_id: str | None = None
    created_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(UtcDateTime(), nullable=False)
    )
    started_at: datetime | None = _ts()
    finished_at: datetime | None = _ts()


class ModelCall(SQLModel, table=True):
    """One row per model call, local or API. The dashboard's only data source (SPEC 10)."""

    __tablename__ = "model_call"

    id: int | None = Field(default=None, primary_key=True)
    # ownership
    series_id: str | None = Field(default=None, index=True)
    episode_id: str | None = Field(default=None, index=True)
    scene_id: str | None = None
    shot_id: str | None = None
    component_id: str | None = Field(default=None, index=True)
    product_id: str | None = None
    version_id: str | None = None
    job_id: str | None = Field(default=None, index=True)
    # model
    provider_id: str | None = None
    model_key: str
    where: str  # local / api
    is_fallback: bool = False
    fallback_reason: str | None = None
    is_switch: bool = False
    attempt: int = 1
    # time
    queued_at: datetime | None = _ts()
    started_at: datetime | None = _ts(index=True)
    finished_at: datetime | None = _ts()
    # usage
    tokens_in: int | None = None
    tokens_out: int | None = None
    images: int | None = None
    output_seconds: float | None = None
    chars: int | None = None
    input_seconds: float | None = None
    # cost
    unit_prices_json: dict[str, Any] | None = _json()
    cost_usd: float = 0.0
    billed: bool = True
    # local resources
    vram_peak_mb: int | None = None
    gpu_util_avg: float | None = None
    # result
    status: str  # success / error / timeout / canceled
    error_code: str | None = None
    qa_scores_json: dict[str, Any] | None = _json()
    qa_pass: bool | None = None


class ConfigOverride(SQLModel, table=True):
    __tablename__ = "config_override"
    __table_args__ = (UniqueConstraint("scope", "scope_id", "component_id"),)

    id: int | None = Field(default=None, primary_key=True)
    scope: str  # project / component / item
    scope_id: str | None = None
    component_id: str | None = None
    data_json: dict[str, Any] = _json(dict)
    updated_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(UtcDateTime(), nullable=False)
    )


class ProviderAccount(SQLModel, table=True):
    """Per-provider account state. The key itself lives in the OS keyring, never here."""

    __tablename__ = "provider_account"

    provider_id: str = Field(primary_key=True)
    has_key: bool = False
    key_ref: str | None = None  # keyring entry name
    base_url_override: str | None = None
    enabled: bool = True
    updated_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(UtcDateTime(), nullable=False)
    )


class CustomModel(SQLModel, table=True):
    __tablename__ = "custom_model"
    __table_args__ = (UniqueConstraint("provider_id", "model_id"),)

    id: int | None = Field(default=None, primary_key=True)
    provider_id: str
    model_id: str
    display_name: str
    price_in: float | None = None
    price_out: float | None = None
    caps_json: dict[str, Any] = _json(dict)
    created_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(UtcDateTime(), nullable=False)
    )


class Event(SQLModel, table=True):
    """Persisted SSE events so clients can replay from ``Last-Event-ID``."""

    __tablename__ = "event"

    id: int | None = Field(default=None, primary_key=True)
    type: str
    data_json: dict[str, Any] = _json(dict)
    created_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(UtcDateTime(), nullable=False)
    )


# --------------------------------------------------------------------------- M1: series, spec


class Series(SQLModel, table=True):
    __tablename__ = "series"

    id: str = Field(default_factory=new_id, primary_key=True)
    slug: str = Field(unique=True)
    title: str
    ui_lang: str = "zh-CN"
    settings_json: dict[str, Any] = _json(dict)
    created_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(UtcDateTime(), nullable=False)
    )


class OutputSpecRow(SQLModel, table=True):
    """One output spec per series (SPEC 4.1, 13). Sizes are derived, never stored."""

    __tablename__ = "output_spec"

    series_id: str = Field(primary_key=True, foreign_key="series.id", ondelete="CASCADE")
    platform: str  # cn / intl / wide / custom
    aspect: str  # 9:16 / 16:9 / 3:4 / 1:1 / 21:9
    delivery: str  # 1080p / 2k
    fps: int  # 24 / 25 / 30
    episode_len: str  # short / mid / long / xl
    subtitles: str  # burn / srt / both
    audio_json: dict[str, Any] = _json(dict)  # sample_rate, lufs, peak_dbtp
    codec: str = "h264"
    ai_mark: bool = True
    derive: str | None = None  # the second aspect made at export time
    # Set when the first keyframe is adopted; afterwards an aspect change needs an impact preview.
    locked_at: datetime | None = _ts()
