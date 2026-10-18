"""API shapes of the setup page (``web/src/api/schemas/setup.ts``) and the stored profile."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from drama_series_agent.setup.detectors import Detection
from drama_series_agent.setup.manifest import OS, Group, Item, Localized, Message, Status
from drama_series_agent.setup.probe import GpuInfo, HostInfo

Phase = Literal["idle", "scanning", "scanned", "installing", "done"]
InstallState = Literal["queued", "running", "done", "failed", "skipped"]
Mirror = Literal["auto", "official", "cn"]


class Gpu(BaseModel):
    name: str
    vram_gb: float
    backend: Literal["cuda", "mps"]


class Machine(BaseModel):
    os: OS
    gpu: Gpu | None


class ItemInstall(BaseModel):
    state: InstallState
    pct: float = 0
    error: Message | None = None


class SetupItem(BaseModel):
    id: str
    group: Group
    name: Localized
    status: Status
    found: Message | None
    fix: Message | None
    required: bool
    installable: bool
    install: ItemInstall | None = None


class InstallRequest(BaseModel):
    """``POST /setup/install``."""

    items: list[str]
    mirror: Mirror
    dir: str = Field(min_length=1, max_length=1024)


class InstallInfo(InstallRequest):
    """The last install request: the items it took, in install order."""

    # What the user has to approve before it starts (SPEC 12.2-5); empty once approved.
    confirm: list[Message] = Field(default_factory=list)


class Recommendation(BaseModel):
    preset: str
    reason: Literal["local_video", "no_cuda"]


class ProfileData(BaseModel):
    """``machine_profile.data_json``."""

    phase: Phase = "idle"
    machine: Machine
    default_dir: str
    items: list[SetupItem] = Field(default_factory=list)
    install: InstallInfo | None = None
    recommendation: Recommendation | None = None
    # What the detectors saw beyond the status (paths, versions, latencies); not in the API.
    facts: dict[str, dict[str, Any]] = Field(default_factory=dict)
    # Bumped by every scan / reset; a job whose token is stale stops writing.
    run: str | None = None
    job_id: str | None = None


class MachineProfile(BaseModel):
    """``GET /setup/profile``."""

    scanned_at: datetime | None
    machine: Machine
    phase: Phase
    items: list[SetupItem]
    install: InstallInfo | None
    default_dir: str
    recommendation: Recommendation | None
    # True with Mock's sample machines: the page then shows the 示例机器 switch.
    simulated: bool


def short_gpu_name(name: str) -> str:
    """``NVIDIA GeForce RTX 5090`` → ``RTX 5090`` (the top bar's label)."""
    return re.sub(r"^(NVIDIA\s+)?(GeForce\s+)?", "", name).strip() or name


def machine_of(host: HostInfo, gpu: GpuInfo | None) -> Machine:
    return Machine(
        os=host.os,
        gpu=(
            Gpu(name=short_gpu_name(gpu.name), vram_gb=round(gpu.vram_gb), backend=gpu.backend)
            if gpu
            else None
        ),
    )


def checking(item: Item) -> SetupItem:
    return SetupItem(
        id=item.id,
        group=item.group,
        name=item.name,
        status="checking",
        found=None,
        fix=None,
        required=item.required,
        installable=False,
    )


def item_of(item: Item, d: Detection) -> SetupItem:
    return SetupItem(
        id=item.id,
        group=item.group,
        name=item.name,
        status=d.status,
        found=d.found,
        fix=d.fix,
        required=item.required,
        installable=d.installable,
    )
