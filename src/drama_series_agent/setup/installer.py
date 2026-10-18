"""The installer (SPEC 12.2-3): what one item's install needs, and who runs it.

``SetupService`` owns the ``setup.install`` job: it walks the queued items in dependency order
and hands each one to an ``ItemRunner``. ``FakeRunner`` (Mock's sample machines) only moves the
progress bar, at the prototype's pace, and fails SageAttention at 60 %; ``RealRunner``
(``setup/steps.py``) runs the manifest's install steps.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from drama_series_agent.setup.detectors import msg
from drama_series_agent.setup.manifest import OS, Item, Message, topo_order

INSTALL_JOB = "setup.install"
LARGE_DOWNLOAD_GB = 10.0  # SPEC 12.2-5
# The demo's pace (mocks/events.ts:demoTiming.setupTickMs) and its failing item.
FAKE_TICK_MS = 120.0
FAKE_FAILING_ITEM = "sage"

LogLevel = Literal["info", "ok", "warn"]
LogFn = Callable[[LogLevel, str, dict[str, Any]], Awaitable[None]]
ProgressFn = Callable[[float], Awaitable[None]]


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
    facts: dict[str, dict[str, Any]] = field(default_factory=dict)  # from the last scan


@dataclass
class Installed:
    version: str | None = None
    paths: list[str] = field(default_factory=list)


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
