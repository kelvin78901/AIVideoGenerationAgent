"""The workflow library's API shapes: the contract in ``web/src/api/schemas/workflows.ts``."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from drama_series_agent.setup.manifest import Message

Tier = Literal["recommended", "mine", "unverified"]
SlotName = Literal[
    "first_frame",
    "video_in",
    "ref_image",
    "ref_audio",
    "prompt",
    "negative",
    "dialogue_audio",
    "width",
    "height",
    "fps",
    "seconds",
    "seed",
    "video_out",
    "image_out",
    "audio_out",
]


class BindingOut(BaseModel):
    slot: SlotName
    index: int | None = None
    node_title: str
    node_class: str
    field: str | None = None
    state: Literal["dramastudio", "confirmed", "guessed"]


class NodeOut(BaseModel):
    title: str
    class_type: str
    fields: list[str]


class MissingPack(BaseModel):
    name: str
    classes: list[str]
    source: Literal["registry", "git", "studio"]  # studio: DramaStudio's own, from the repo
    version: str | None = None
    url: str | None = None


class MissingModel(BaseModel):
    folder: str
    name: str
    size_bytes: int | None = None
    url: str | None = None


class ClassCount(BaseModel):
    found: int
    total: int


class CheckOut(BaseModel):
    at: datetime
    status: Literal["ok", "missing", "broken"]
    node_classes: ClassCount
    missing_packs: list[MissingPack] = Field(default_factory=list)
    missing_models: list[MissingModel] = Field(default_factory=list)
    problems: list[Message] = Field(default_factory=list)


class TrialOut(BaseModel):
    at: datetime
    status: Literal["running", "passed", "failed"]
    job_id: str | None = None
    w: int
    h: int
    seconds: float
    duration_s: float | None = None
    vram_gb: float | None = None
    error: Message | None = None


class CapsOut(BaseModel):
    aspects: list[str]
    max_seconds: float | None = None
    refs: int | None = None
    vram_gb: float | None = None


class WorkflowOut(BaseModel):
    id: str
    slug: str
    model_key: str
    name: str
    tier: Tier
    source: Literal["repo", "user"]
    origin: str | None
    components: list[str]
    caps: CapsOut
    file_sha256: str
    file_changed: bool
    uses_dramastudio_nodes: bool
    bindings: list[BindingOut]
    nodes: list[NodeOut]
    check: CheckOut | None
    trial: TrialOut | None
    created_at: datetime
    updated_at: datetime


class ComfyWorkflowFile(BaseModel):
    path: str
    modified_at: datetime
    imported_as: str | None
    board: bool


class ImportIn(BaseModel):
    """A dropped API- or UI-format JSON file, or a path from ComfyUI's own list."""

    file_name: str | None = None
    workflow: dict[str, Any] | None = None
    comfy_path: str | None = None


class TierIn(BaseModel):
    tier: Tier


class DepsInstalled(BaseModel):
    """``POST /workflows/{id}/deps/install``: what got installed, and the snapshot taken first."""

    workflow: WorkflowOut
    packs: int
    models: int
    snapshot: str
    restart_required: bool  # a real ComfyUI loads new node packs when it restarts
    failed: list[dict[str, str]] = Field(default_factory=list)  # {name, code}
