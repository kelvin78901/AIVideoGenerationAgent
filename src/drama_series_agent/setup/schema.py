"""API shapes of the setup page (``web/src/api/schemas/setup.ts``) and the stored profile."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from drama_series_agent.setup.comfy import ComfyEnvInfo, ComfyScan
from drama_series_agent.setup.detectors import Detection
from drama_series_agent.setup.installer import size_bytes, work_s
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
    # An item with downloads, while it runs: bytes over all its files (the total is the sizes
    # known so far), the speed over the last few seconds (bytes/s), the time left at that speed,
    # and whether a finished file's sha256 is being checked.
    bytes_done: int | None = None
    bytes_total: int | None = None
    speed: float | None = None
    eta_s: float | None = None
    verifying: bool = False


class SetupItem(BaseModel):
    id: str
    group: Group
    name: Localized
    status: Status
    found: Message | None
    fix: Message | None
    required: bool
    installable: bool
    # Installing it changes the user's own ComfyUI (SPEC 6.4.1): not ticked by default, listed
    # for approval, and a ComfyUI-Manager snapshot is taken first.
    touches_comfy: bool = False
    # For the estimates: what it downloads (bytes) and its rough time apart from that (s).
    size_bytes: int | None = None
    work_s: float = 0
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
    # The changes to the user's ComfyUI (``comfy_change``), kept after approval for the snapshot.
    changes: list[Message] = Field(default_factory=list)
    # The comfy_snapshot taken before the first of those changes, or why none could be.
    snapshot: str | None = None
    snapshot_error: Message | None = None


class Recommendation(BaseModel):
    preset: str
    reason: Literal["local_video", "no_cuda"]


class ProfileData(BaseModel):
    """``machine_profile.data_json``."""

    phase: Phase = "idle"
    machine: Machine
    default_dir: str
    # The program's own folder: an install location inside it gets a warning (step 8c).
    app_dir: str | None = None
    items: list[SetupItem] = Field(default_factory=list)
    install: InstallInfo | None = None
    recommendation: Recommendation | None = None
    # What the detectors saw beyond the status (paths, versions, latencies); not in the API.
    facts: dict[str, dict[str, Any]] = Field(default_factory=dict)
    # Item ids this machine has: set when a scan finishes, extended by each finished install,
    # kept while a rescan runs. None before the first scan. Feeds core/capabilities.py.
    found: list[str] | None = None
    # The ComfyUI the last finished scan found (SPEC 6.4.1): where it is, its model files and
    # the hash of its environment in ``comfy_env``. Kept while a rescan runs.
    comfy: ComfyScan | None = None
    # Download speed on this machine (bytes/s): the last finished item's downloads, else a short
    # download during a scan. Kept across scans; times the downloads in the estimates.
    download_bps: float | None = None
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
    app_dir: str | None
    recommendation: Recommendation | None
    # True with Mock's sample machines: the page then shows the 示例机器 switch.
    simulated: bool
    download_bps: float | None


class ComfyEnvOut(ComfyEnvInfo):
    hash: str
    captured_at: datetime


class RestoreCheck(BaseModel):
    """A rollback to a snapshot: requested, then checked by the next scan (step 8c)."""

    # pending: ComfyUI has not changed since the request (not restarted yet); done: it is back
    # at the snapshot; incomplete: it changed but not back (``diff``: what still differs);
    # unchecked: requested before the check existed.
    state: Literal["pending", "done", "incomplete", "unchecked"]
    requested_at: datetime
    diff: list[Message] = Field(default_factory=list)  # setup:restoreDiff.<code>


class ComfySnapshot(BaseModel):
    """``GET /comfy/snapshots``: one ComfyUI-Manager snapshot, newest first."""

    id: str
    manager_name: str
    env_hash: str | None
    reason: Literal["install", "manual"]
    changes: list[Message]  # what the install that took it was about to change
    created_at: datetime
    restore: RestoreCheck | None  # the last rollback to it
    restored_at: datetime | None  # when a scan found ComfyUI back at it


class NodePackSource(BaseModel):
    """A node pack a workflow needs (M5): its name, repository and the ref to check out."""

    name: str
    url: str
    ref: str = "HEAD"


class PacksInstalled(BaseModel):
    snapshot: ComfySnapshot
    installed: list[str]
    failed: list[dict[str, str]]  # {name, code}


class Restored(BaseModel):
    """``POST /comfy/snapshots/{id}/restore``: Manager applies it when ComfyUI next starts."""

    snapshot: ComfySnapshot
    restart_required: bool = True


class ComfyView(BaseModel):
    """``GET /comfy/env``: the ComfyUI the last finished scan found; both null when none."""

    scanned_at: datetime | None
    simulated: bool
    comfy: ComfyScan | None  # where it is, its model folders and files
    env: ComfyEnvOut | None  # versions and node packs


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
        size_bytes=size_bytes(item),
        work_s=work_s(item),
    )


def item_of(item: Item, d: Detection, *, touches_comfy: bool = False) -> SetupItem:
    return SetupItem(
        id=item.id,
        group=item.group,
        name=item.name,
        status=d.status,
        found=d.found,
        fix=d.fix,
        required=item.required,
        installable=d.installable,
        touches_comfy=touches_comfy,
        size_bytes=size_bytes(item),
        work_s=work_s(item),
    )
