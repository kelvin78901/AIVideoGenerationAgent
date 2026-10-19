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
    # What the spend counts against (episode budget, SPEC 7.6); None for series-level work.
    episode_id: str | None = Field(default=None, index=True)
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
    # What the user agreed to spend when confirming it (waiting_confirm → queued).
    confirmed_usd: float | None = None
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


# --------------------------------------------------------------------------- M1: setup


class MachineProfileRow(SQLModel, table=True):
    """The last scan of a machine and the install state (SPEC 12.2).

    ``id`` is ``local`` for this computer, ``demo`` for Mock mode's sample machines (``machine``
    then says which one), so a simulated install never leaks into the real profile.
    """

    __tablename__ = "machine_profile"

    id: str = Field(primary_key=True)
    machine: str | None = None  # demo: pc / mac
    scanned_at: datetime | None = _ts()
    data_json: dict[str, Any] = _json(dict)  # phase, items, install, facts, recommendation…
    updated_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(UtcDateTime(), nullable=False)
    )


class InstalledItem(SQLModel, table=True):
    """What the installer put on this machine, for uninstall and the next scan (SPEC 12.2-3)."""

    __tablename__ = "installed_item"

    profile_id: str = Field(primary_key=True, foreign_key="machine_profile.id", ondelete="CASCADE")
    item_id: str = Field(primary_key=True)
    version: str | None = None
    paths_json: list[str] = _json(list)
    installed_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(UtcDateTime(), nullable=False)
    )


class ComfyEnvRow(SQLModel, table=True):
    """One ComfyUI environment the scan saw, kept under its content hash (SPEC 6.4.1, 6.4.5).

    A new row only when something changed (version, Python, PyTorch, a node pack), so a take
    made locally can always say which ComfyUI and nodes made it.
    """

    __tablename__ = "comfy_env"

    hash: str = Field(primary_key=True)
    comfyui_version: str | None = None
    comfyui_commit: str | None = None
    python: str | None = None
    torch: str | None = None
    node_packs_json: list[dict[str, Any]] = _json(list)
    captured_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(UtcDateTime(), nullable=False)
    )


class ComfySnapshotRow(SQLModel, table=True):
    """A ComfyUI-Manager snapshot of the user's ComfyUI, taken before we changed it (SPEC 6.4.1).

    ``profile_id`` keeps Mock's sample machines apart from this computer, as in
    ``machine_profile``.
    """

    __tablename__ = "comfy_snapshot"

    id: str = Field(default_factory=new_id, primary_key=True)
    profile_id: str = Field(index=True)
    manager_name: str  # the snapshot's name in ComfyUI-Manager
    env_hash: str | None = None  # comfy_env as of the last scan
    reason: str  # install / manual
    changes_json: list[dict[str, Any]] = _json(list)  # the change list the user approved
    created_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(UtcDateTime(), nullable=False)
    )
    # A rollback to it: requested (Manager applies it when ComfyUI next starts), then checked by
    # the first scan that finds ComfyUI changed. State: pending / done / incomplete, or
    # unchecked for one requested before the check existed (migration 0006).
    restore_requested_at: datetime | None = _ts()
    restore_from_hash: str | None = None  # comfy_env when the rollback was requested
    restore_state: str | None = None
    restore_diff_json: list[dict[str, Any]] | None = _json()  # what still differs
    restored_at: datetime | None = _ts()  # when a scan found ComfyUI back at this snapshot


# --------------------------------------------------------------------------- M2: products


class Product(SQLModel, table=True):
    """A card with the four buttons (改提示词 / 重跑 / 不满意换一个 / 历史), SPEC 4.2.

    Its versions are the source of truth; domain tables (bible, script lines …) mirror the
    adopted version. ``status`` keeps the run state; locked / adopted / stale are worked out on
    read (``pipeline/products.py:status_of``).
    """

    __tablename__ = "product"
    __table_args__ = (UniqueConstraint("owner_type", "owner_id", "slot"),)

    id: str = Field(default_factory=new_id, primary_key=True)
    series_id: str = Field(foreign_key="series.id", ondelete="CASCADE", index=True)
    owner_type: str  # series / episode / scene / shot / asset / line
    owner_id: str
    slot: str  # bible / suggestions / episodes / script / …
    component_id: str
    current_version_id: str | None = None  # shown on screen
    adopted_version_id: str | None = None  # used downstream
    locked_hash: str | None = None  # content hash when a gate locked it
    status: str = "empty"  # empty / queued / running / ready / failed
    # The prompt the next run uses: {intent, compiled, compiled_overridden, model_key}.
    prompt_json: dict[str, Any] | None = _json()
    running_job_id: str | None = None
    created_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(UtcDateTime(), nullable=False)
    )
    updated_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(UtcDateTime(), nullable=False)
    )


class ProductVersion(SQLModel, table=True):
    """One run or edit of a product. Append-only: never updated except ``rating`` / ``note``."""

    __tablename__ = "product_version"
    __table_args__ = (UniqueConstraint("product_id", "n"),)

    id: str = Field(default_factory=new_id, primary_key=True)
    product_id: str = Field(foreign_key="product.id", ondelete="CASCADE", index=True)
    n: int  # 1-based, shown as v{n}
    # run / rerun / switch / edit / fallback / import / auto_qa_rerun / comfy_ingest
    origin: str
    parent_version_id: str | None = None
    payload_json: dict[str, Any] = _json(dict)
    files_json: list[dict[str, Any]] = _json(list)  # role, path, sha256, mime, duration_s, w, h
    content_hash: str
    intent: str | None = None
    compiled: str | None = None
    compiled_overridden: bool = False
    model_key: str | None = None
    where: str | None = None  # local / api
    seed: int | None = None
    params_json: dict[str, Any] = _json(dict)
    qa_json: dict[str, Any] | None = _json()
    qa_pass: bool | None = None
    fallback_reason: str | None = None  # error / timeout / qa_fail
    stage: str | None = None  # hybrid mode: draft / final
    rating: int | None = None
    cost_usd: float = 0.0
    job_id: str | None = None
    note: str | None = None
    # Local ComfyUI runs (SPEC 6.4.5).
    workflow_id: str | None = None
    workflow_sha256: str | None = None
    comfy_env_hash: str | None = None
    created_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(UtcDateTime(), nullable=False)
    )


class Dependency(SQLModel, table=True):
    """What a version was built from: one row per upstream slice it read (SPEC 4.2).

    ``slice`` names the part of the upstream product that went into the prompt (``""`` = all of
    it, ``episode:<id>`` = one episode's beats …) and ``upstream_hash`` its hash at build time.
    """

    __tablename__ = "dependency"

    id: int | None = Field(default=None, primary_key=True)
    version_id: str = Field(foreign_key="product_version.id", ondelete="CASCADE", index=True)
    product_id: str = Field(index=True)
    upstream_product_id: str = Field(index=True)
    slice: str = ""
    upstream_hash: str


class GateDecision(SQLModel, table=True):
    """A gate confirmed or reopened (SPEC 4.2), with the hashes it locked."""

    __tablename__ = "gate_decision"

    id: str = Field(default_factory=new_id, primary_key=True)
    series_id: str = Field(foreign_key="series.id", ondelete="CASCADE", index=True)
    gate: str  # novel / script / assets / storyboard / takes / export
    scope_id: str  # series id (novel) or episode id
    action: str  # confirm / reopen
    product_hashes_json: dict[str, str] = _json(dict)  # product id → effective hash
    decided_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(UtcDateTime(), nullable=False)
    )


class AppSetting(SQLModel, table=True):
    """App-wide settings that are not per component: e.g. ``config.defaults`` (Models page)."""

    __tablename__ = "app_setting"

    key: str = Field(primary_key=True)
    value_json: dict[str, Any] = _json(dict)
    updated_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(UtcDateTime(), nullable=False)
    )


class LlmCache(SQLModel, table=True):
    """Validated LLM answers by request hash (model, messages, seed …).

    A job that is retried or resumed after a restart reuses the chunks it already paid for;
    a rerun has a new seed, so it asks again.
    """

    __tablename__ = "llm_cache"

    key: str = Field(primary_key=True)
    model_key: str
    value_json: Any = Field(sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(UtcDateTime(), nullable=False)
    )


class NovelSource(SQLModel, table=True):
    """One imported novel file (SPEC 4.1). A re-import adds a row; the old text stays.

    The text lives in the blob store: ``sha256`` is the normalized text (UTF-8, ``\n`` line
    ends), which every source span points into; ``original_sha256`` is the uploaded file.
    Which source a series uses is the adopted version of its ``novel`` product.
    """

    __tablename__ = "novel_source"

    id: str = Field(default_factory=new_id, primary_key=True)
    series_id: str = Field(foreign_key="series.id", ondelete="CASCADE", index=True)
    filename: str
    sha256: str
    original_sha256: str
    encoding: str  # utf-8 / utf-16 / gb18030 / docx
    split_by: str  # heading / length
    chars: int  # paragraph characters, headings and blank lines excluded
    rights_confirmed_at: datetime = Field(sa_column=Column(UtcDateTime(), nullable=False))
    created_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(UtcDateTime(), nullable=False)
    )


class Chapter(SQLModel, table=True):
    """A chapter of a novel source: character offsets into its text (SPEC 4.1).

    Paragraphs are numbered across the whole book (``para_start`` + i) and their offsets are
    stored, so a source keeps its numbering even if the splitting rules change later.
    """

    __tablename__ = "chapter"
    __table_args__ = (UniqueConstraint("source_id", "idx"),)

    id: str = Field(default_factory=new_id, primary_key=True)
    source_id: str = Field(foreign_key="novel_source.id", ondelete="CASCADE", index=True)
    idx: int  # 0-based
    # The heading line; None for text before the first heading or a part of a length split.
    title: str | None = None
    start: int
    end: int
    para_start: int
    paras_json: list[list[int]] = _json(list)  # [[start, end], …]


class BibleEntity(SQLModel, table=True):
    """One entry of a series' story bible (SPEC 4.1), mirroring the adopted ``bible`` version.

    Rebuilt from that version on every adopt (``bible/service.py:materialize``): upserted by
    id, and entries the version no longer has are marked ``retired`` rather than deleted, so
    rows that point at them later (assets, shots) keep their foreign keys.
    """

    __tablename__ = "bible_entity"

    id: str = Field(primary_key=True)
    series_id: str = Field(foreign_key="series.id", ondelete="CASCADE", index=True)
    version_id: str  # the adopted version this row mirrors
    kind: str  # character / location / prop / event / relation
    name: str
    aliases_json: list[str] = _json(list)
    data_json: dict[str, Any] = _json(dict)
    paras_json: list[int] = _json(list)  # paragraph numbers across the book, 0-based
    source_spans_json: list[dict[str, Any]] = _json(list)  # [{source_id, start, end}, …]
    frozen: bool = False  # the user marked it as not to be changed by extraction
    retired: bool = False
    updated_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(UtcDateTime(), nullable=False)
    )


class Suggestion(SQLModel, table=True):
    """One enrichment suggestion (SPEC 4.1), mirroring the adopted ``suggestions`` version.

    Rebuilt on every adopt like ``bible_entity`` (upsert by id, ``retired`` instead of a
    delete). ``text`` is what the model proposed; a rewrite and the user's decision live in
    ``suggestion_decision``.
    """

    __tablename__ = "suggestion"

    id: str = Field(primary_key=True)
    series_id: str = Field(foreign_key="series.id", ondelete="CASCADE", index=True)
    version_id: str  # the adopted version this row mirrors
    kind: str  # appearance / lighting / inner_to_action / cliffhanger / motive / timeline …
    para_idx: int  # the paragraph (across the book, 0-based) the addition follows
    anchor_span_json: dict[str, Any] = _json(dict)  # {source_id, start, end}
    reason: str = ""
    text: str = ""
    retired: bool = False
    updated_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(UtcDateTime(), nullable=False)
    )


class SuggestionDecision(SQLModel, table=True):
    """What the user decided on a suggestion (M2 plan 设计要点「建议的决定不进版本」).

    Keyed by suggestion id, outside the versions: deciding makes no version, and a rerun that
    keeps the id keeps the decision. No row = pending.
    """

    __tablename__ = "suggestion_decision"

    suggestion_id: str = Field(primary_key=True)
    series_id: str = Field(foreign_key="series.id", ondelete="CASCADE", index=True)
    status: str = "pending"  # pending / accepted / rejected / rewritten
    text: str | None = None  # the rewrite (「按要求重写」), used instead of the model's text
    rewrite_instruction: str | None = None
    rewritten_by: str | None = None  # model key
    updated_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(UtcDateTime(), nullable=False)
    )


class Episode(SQLModel, table=True):
    """One episode of a series (SPEC 4.1), mirroring the adopted ``episodes`` version (分集规划).

    Rebuilt on every adopt like ``bible_entity`` (upsert by id, ``retired`` instead of a
    delete, so the episode's products and spending keep their foreign keys). ``budget_usd`` is
    the user's setting (the Models page), not part of any version: an adopt never changes it.
    """

    __tablename__ = "episode"

    id: str = Field(primary_key=True)
    series_id: str = Field(foreign_key="series.id", ondelete="CASCADE", index=True)
    version_id: str  # the adopted version this row mirrors
    idx: int  # 1-based within the series
    title: str = ""
    hook: str | None = None
    cliffhanger: str | None = None
    target_seconds: int | None = None
    scene_count: int | None = None  # 预计场数 (the plan's estimate, before the script)
    budget_usd: float | None = None
    retired: bool = False
    updated_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(UtcDateTime(), nullable=False)
    )


class Beat(SQLModel, table=True):
    """One beat of an episode's plan (SPEC 4.1), mirroring the adopted ``episodes`` version."""

    __tablename__ = "beat"

    id: str = Field(primary_key=True)
    series_id: str = Field(foreign_key="series.id", ondelete="CASCADE", index=True)
    episode_id: str = Field(index=True)
    version_id: str
    idx: int  # 1-based within the episode
    text: str = ""
    emotion: float = 0.0  # -1 (lowest) … 1 (highest), the emotion curve
    paras_json: list[int] = _json(list)  # paragraph numbers across the book, 0-based
    source_spans_json: list[dict[str, Any]] = _json(list)  # [{source_id, start, end}, …]
    retired: bool = False
    updated_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(UtcDateTime(), nullable=False)
    )
