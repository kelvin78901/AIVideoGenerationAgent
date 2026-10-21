"""API shapes of products and versions (front-end contract ``web/src/api/schemas/products.ts``)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

OwnerType = Literal["series", "episode", "scene", "shot", "asset", "line"]
ProductStatus = Literal[
    "empty", "queued", "running", "ready", "stale", "adopted", "locked", "failed"
]  # fmt: skip
# ``pick``: the candidate the user locked, alone (M3); ``upload``: the user's own file.
VersionOrigin = Literal[
    "run", "rerun", "switch", "edit", "fallback", "import", "auto_qa_rerun", "comfy_ingest",
    "pick", "upload",
]  # fmt: skip


class VersionFileOut(BaseModel):
    role: str
    path: str
    sha256: str
    mime: str
    duration_s: float | None = None
    w: int | None = None
    h: int | None = None
    idx: int | None = None  # a candidate's or view's number in its version (M3)
    view: str | None = None  # side / back / expressions (补视图)
    line: int | None = None  # a voice sample: which of its audition lines it reads
    emotion: str | None = None  # a voice's emotion variant (config/voice.yaml)
    waveform: list[float] | None = None  # audio: 64 peaks, 0–1 (media/audio.py)


class VersionOut(BaseModel):
    id: str
    product_id: str
    n: int
    origin: VersionOrigin
    parent_version_id: str | None
    payload: dict[str, Any]
    files: list[VersionFileOut]
    content_hash: str | None
    intent: str | None
    compiled: str | None
    compiled_overridden: bool
    model_key: str | None
    where: Literal["local", "api"] | None
    seed: int | None
    params: dict[str, Any]
    qa: dict[str, Any] | None
    qa_pass: bool | None
    fallback_reason: Literal["error", "timeout", "qa_fail"] | None
    stage: Literal["draft", "final"] | None
    rating: int | None
    cost_usd: float
    job_id: str | None
    created_at: datetime
    note: str | None


class PromptOut(BaseModel):
    intent: str
    compiled: str
    compiled_overridden: bool
    model_key: str


class EstimateOut(BaseModel):
    model_key: str
    where: Literal["local", "api"]
    cost_usd: float
    seconds: float | None


class RunningOut(BaseModel):
    job_id: str
    model_key: str
    state: Literal["queued", "waiting_confirm", "running"]
    # The 确认并同步 this run is part of (shown as 「同步中」); None for a run of its own.
    cascade_id: str | None = None


class PickOut(BaseModel):
    """「选这个」: candidate ``idx`` (0-based, its ``files[].idx``) of version ``version_id``."""

    version_id: str
    idx: int


class ProductOut(BaseModel):
    id: str
    series_id: str
    owner_type: OwnerType
    owner_id: str
    slot: str
    component_id: str
    current_version_id: str | None
    adopted_version_id: str | None
    locked_hash: str | None
    status: ProductStatus
    versions: list[VersionOut]  # oldest first
    prompt: PromptOut | None
    estimate: EstimateOut | None
    running: RunningOut | None
    pick: PickOut | None = None
    settings: dict[str, Any] | None = None
    retired: bool = False
