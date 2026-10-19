"""The installer (SPEC 12.2-3): what one item's install needs, and who runs it.

``SetupService`` owns the ``setup.install`` job: it walks the queued items in dependency order
and hands each one to an ``ItemRunner``. ``FakeRunner`` (Mock's sample machines) only moves the
progress bar, at the prototype's pace, and fails SageAttention at 60 %; ``RealRunner``
(``setup/steps.py``) runs the manifest's install steps.
"""

from __future__ import annotations

import asyncio
import os
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from drama_series_agent.setup.comfy import ModelDir
from drama_series_agent.setup.detectors import msg
from drama_series_agent.setup.manifest import OS, TODO, Item, Message, topo_order

INSTALL_JOB = "setup.install"
LARGE_DOWNLOAD_GB = 10.0  # SPEC 12.2-5
# The demo's pace (mocks/events.ts:demoTiming.setupTickMs) and its failing item.
FAKE_TICK_MS = 120.0
FAKE_FAILING_ITEM = "sage"

LogLevel = Literal["info", "ok", "warn"]
LogFn = Callable[[LogLevel, str, dict[str, Any]], Awaitable[None]]


@dataclass(frozen=True)
class Transfer:
    """An item's downloads so far, over all its files (``setup/download.py:Meter``)."""

    done: int
    total: int | None  # the sizes known so far
    speed: float | None  # bytes per second over the last few seconds
    verifying: bool = False  # checking a finished file's sha256


class ProgressFn(Protocol):
    async def __call__(self, pct: float, transfer: Transfer | None = None) -> None: ...


class InstallError(Exception):
    """An item could not be installed; ``code`` is ``setup:error.<code>``."""

    def __init__(self, code: str, **params: Any) -> None:
        super().__init__(code)
        self.code = code
        self.params = params

    def message(self) -> Message:
        return Message(code=self.code, params=self.params)


@dataclass
class InstallEnv:
    """Where things go, for one install run."""

    os: OS
    mirror: Literal["auto", "official", "cn"]
    models: str  # the folder the user picked for weights
    envs: str  # ~/.drama-studio/envs
    comfy: str  # ComfyUI root: the one found, else ~/.drama-studio/ComfyUI
    comfy_python: str | None = None  # the interpreter that ComfyUI runs on, when found
    # ComfyUI's model folders from the last scan (extra_model_paths included): weights for a
    # ComfyUI folder go to its `default` one (Comfy Desktop's shared models), else {comfy}/models.
    model_dirs: list[ModelDir] = field(default_factory=list)
    facts: dict[str, dict[str, Any]] = field(default_factory=dict)  # from the last scan


@dataclass
class Installed:
    version: str | None = None
    paths: list[str] = field(default_factory=list)
    bps: float | None = None  # how fast its downloads came, when it had any


class ItemRunner(Protocol):
    async def install(
        self, item: Item, env: InstallEnv, log: LogFn, progress: ProgressFn
    ) -> Installed: ...


def fake_tick_s() -> float:
    """One progress step on a sample machine; ``DRAMA_SETUP_FAKE_TICK_MS`` (tests: 0)."""
    try:
        ms = float(os.environ.get("DRAMA_SETUP_FAKE_TICK_MS", FAKE_TICK_MS))
    except ValueError:
        ms = FAKE_TICK_MS
    return max(ms, 0.0) / 1000


class FakeRunner:
    """Installs nothing. Downloads move 10 % a step, the rest 34 %, like the demo."""

    def __init__(self, failing: str | None = FAKE_FAILING_ITEM) -> None:
        self.failing = failing

    async def install(
        self, item: Item, env: InstallEnv, log: LogFn, progress: ProgressFn
    ) -> Installed:
        step = 10.0 if item.group == "w" else 34.0
        pct = 0.0
        while True:
            tick = fake_tick_s()
            if tick:
                await asyncio.sleep(tick)
            pct += step
            if item.id == self.failing and pct >= 60:
                await progress(60)
                raise InstallError("no_wheel")
            if pct >= 100:
                return Installed()
            await progress(pct)


def install_order(items: list[Item], selected: list[str]) -> list[str]:
    """The selected ids, dependencies first, otherwise manifest order."""
    chosen = set(selected)
    return [x.id for x in topo_order(items) if x.id in chosen]


def confirm_reasons(items: list[Item], os: OS) -> list[Message]:
    """What to ask before installing: elevation for a package, a download over 10 GB."""
    reasons: list[Message] = []
    for x in items:
        if any(s.needs_admin(os) for s in x.install):
            reasons.append(msg("admin", item=x.id))
        downloads = any(s.type == "download" for s in x.install)
        if downloads and (x.size_gb or 0) > LARGE_DOWNLOAD_GB:
            reasons.append(msg("large_download", item=x.id, gb=x.size_gb))
    return reasons


def _first(item: Item, keys: tuple[str, ...]) -> str | None:
    for step in item.install:
        extra = step.model_extra or {}
        for key in keys:
            value = extra.get(key)
            if isinstance(value, str) and value and TODO not in value:
                return value
            if isinstance(value, list) and value and key == "packages":
                return " ".join(str(v) for v in value)
    return None


def comfy_change(item: Item, *, status: str, version: str | None) -> Message:
    """One line of the change list for the user's own ComfyUI (SPEC 6.4.1): what, from which
    version to which, from where, how big. Unknown parts are left out."""
    params: dict[str, Any] = {"item": item.id, "action": "update" if status == "old" else "install"}
    # A step's readable `version` (a tag) first; a bare commit shows as its short form.
    target = _first(item, ("version", "ref", "revision"))
    if target and re.fullmatch(r"[0-9a-f]{40}", target):
        target = target[:7]
    source = _first(item, ("url", "hf_repo", "packages", "requirements", "from"))
    for key, value in (("from", version), ("to", target), ("source", source)):
        if value:
            params[key] = value
    if item.size_gb:
        params["gb"] = item.size_gb
    return msg("comfy_change", **params)
