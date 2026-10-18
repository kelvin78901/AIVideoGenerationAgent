"""Setup (SPEC 12.2): the machine profile, the scan job and Mock's sample machines.

One profile row per machine: ``local`` is this computer (``RealProbe``), ``demo`` is the
prototype's sample machines (``FakeProbe``, Mock mode; PC or Mac). ``DRAMA_SETUP=real|fake``
picks explicitly; otherwise Mock mode means fake.

A scan is a ``setup.scan`` job on the cpu queue. It rewrites the profile item by item and
publishes ``setup.progress`` after each one. Every scan or reset draws a new ``run`` token; a
job whose token is no longer the profile's stops without writing, so a rescan or a machine
switch never mixes two scans. All profile writes go through one lock.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
from collections import Counter
from collections.abc import Callable
from datetime import datetime
from typing import Any, Literal

import httpx
from sqlmodel import col, delete, select

from drama_series_agent.core.db import Database
from drama_series_agent.core.events import EventBus, EventType
from drama_series_agent.core.jobs import TERMINAL, JobContext, JobQueue, JobStateError
from drama_series_agent.core.models_db import InstalledItem, MachineProfileRow, new_id, utcnow
from drama_series_agent.core.paths import drama_home
from drama_series_agent.modelhub.registry import is_mock_mode
from drama_series_agent.setup.detectors import Detection, ScanContext, detect_item, join, msg
from drama_series_agent.setup.manifest import Manifest, load_manifest
from drama_series_agent.setup.probe import FakeProbe, Probe, RealProbe
from drama_series_agent.setup.schema import (
    MachineProfile,
    ProfileData,
    Recommendation,
    SetupItem,
    checking,
    item_of,
    machine_of,
)

SCAN_JOB = "setup.scan"
PROFILE_LOCAL = "local"
PROFILE_DEMO = "demo"
DemoMachine = Literal["pc", "mac"]
DEFAULT_DEMO_MACHINE: DemoMachine = "pc"
# The sample machines reveal one item per step, like the demo (mocks/events.ts:demoTiming).
FAKE_STEP_MS = 110.0

_UNSET: Any = object()


def setup_mode() -> Literal["real", "fake"]:
    explicit = os.environ.get("DRAMA_SETUP", "").strip().lower()
    if explicit == "real":
        return "real"
    if explicit == "fake":
        return "fake"
    return "fake" if is_mock_mode() else "real"


def fake_step_s() -> float:
    """Pause between items on a sample machine; ``DRAMA_SETUP_FAKE_DELAY_MS`` (tests: 0)."""
    try:
        ms = float(os.environ.get("DRAMA_SETUP_FAKE_DELAY_MS", FAKE_STEP_MS))
    except ValueError:
        ms = FAKE_STEP_MS
    return max(ms, 0.0) / 1000


class SetupBusy(Exception):
    """An install is running; scans and resets wait for it."""


class NotSimulated(Exception):
    """The sample-machine switch only exists in fake mode."""


class SetupService:
    def __init__(
        self,
        db: Database,
        bus: EventBus,
        jobs: JobQueue,
        *,
        manifest: Callable[[], Manifest] = load_manifest,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.db = db
        self.bus = bus
        self.jobs = jobs
        self._manifest = manifest
        self._transport = transport
        self._lock = asyncio.Lock()
        jobs.register(SCAN_JOB, self._scan_job)

    # ------------------------------------------------------------------ queries

    @property
    def profile_id(self) -> str:
        return PROFILE_DEMO if setup_mode() == "fake" else PROFILE_LOCAL

    def probe_for(self, row: MachineProfileRow) -> Probe:
        if row.id == PROFILE_DEMO:
            return FakeProbe.load(row.machine or DEFAULT_DEMO_MACHINE)
        return RealProbe(self._transport)

    async def profile(self) -> MachineProfile:
        async with self._lock:
            row, data = await self._get_or_create()
            if await self._settle(row, data):
                await self._save(row.id, data)
            return self._public(row, data)

    async def installed(self, profile_id: str | None = None) -> set[str]:
        pid = profile_id or self.profile_id
        async with self.db.session() as s:
            rows = await s.exec(
                select(InstalledItem.item_id).where(col(InstalledItem.profile_id) == pid)
            )
            return set(rows.all())

    # ------------------------------------------------------------------ commands

    async def start_scan(self) -> MachineProfile:
        """Scan again from the top; a scan already running is replaced."""
        async with self._lock:
            row, data = await self._get_or_create()
            if data.phase == "installing":
                raise SetupBusy
            await self._cancel(data.job_id)
            host = await self.probe_for(row).host()
            data.phase = "scanning"
            data.items = [checking(x) for x in self._manifest().for_platform(host.os)]
            data.run = new_id()
            job = await self.jobs.enqueue(
                SCAN_JOB, "cpu", {"profile_id": row.id, "run": data.run}, max_attempts=3
            )
            data.job_id = job.id
            await self._save(row.id, data)
            await self._progress(data, None)
            return self._public(row, data)

    async def switch_machine(self, machine: DemoMachine) -> MachineProfile:
        """Mock only: scan the other sample machine. Starts over: no scan, nothing installed."""
        async with self._lock:
            if self.profile_id != PROFILE_DEMO:
                raise NotSimulated
            row, data = await self._get_or_create()
            await self._cancel(data.job_id)
            row.machine = machine
            fresh = await self._idle(self.probe_for(row))
            async with self.db.session() as s:
                await s.exec(
                    delete(InstalledItem).where(col(InstalledItem.profile_id) == PROFILE_DEMO)
                )
                await s.commit()
            await self._save(row.id, fresh, machine=machine, scanned_at=None)
            row.scanned_at = None
            await self._progress(fresh, None)
            return self._public(row, fresh)

    # ------------------------------------------------------------------ scan job

    async def _scan_job(self, ctx: JobContext) -> dict[str, Any]:
        pid, run = str(ctx.params["profile_id"]), str(ctx.params["run"])
        superseded = {"superseded": True}
        async with self._lock:
            loaded = await self._load(pid)
        if loaded is None or loaded[1].run != run:
            return superseded
        row, data = loaded
        probe = self.probe_for(row)
        manifest = self._manifest()
        host = await probe.host()
        items = manifest.for_platform(host.os)
        # The sample machines have their own home folder; ours is the real one.
        envs = (
            join(host.home, ".drama-studio", "envs")
            if probe.simulated
            else str(drama_home() / "envs")
        )
        scan = await ScanContext.create(
            probe,
            items,
            mirrors=manifest.mirrors,
            envs=envs,
            models=data.install.dir if data.install else None,
        )
        # A sample machine cannot change, so what we installed on it is what counts (SPEC 12.2-3).
        installed = await self.installed(pid) if probe.simulated else set()
        machine = machine_of(host, scan.gpu)
        default_dir = await probe.default_dir()

        def reset(d: ProfileData) -> None:
            d.machine, d.default_dir = machine, default_dir
            d.items = [checking(x) for x in items]
            d.facts = {}

        # Silent: start_scan already announced the phase (a restarted job lands here again).
        if not await self._write(pid, run, reset, publish=False):
            return superseded
        step = fake_step_s() if probe.simulated else 0.0
        counts: Counter[str] = Counter()
        for i, x in enumerate(items):
            if step:
                await asyncio.sleep(step)
            det = await detect_item(x, scan)
            if x.id in installed and det.status != "ok":
                det = Detection(status="ok", found=msg("installed"), fix=None, installable=False)
            counts[det.status] += 1
            public = item_of(x, det)
            facts = {**det.facts, **({"version": det.version} if det.version else {})}

            def put(
                d: ProfileData,
                i: int = i,
                item_id: str = x.id,
                public: SetupItem = public,
                facts: dict[str, Any] = facts,
            ) -> None:
                d.items[i] = public
                if facts:
                    d.facts[item_id] = facts

            if not await self._write(pid, run, put, item=public.model_dump(mode="json")):
                return superseded
        rec = manifest.recommendation(
            cuda=scan.has_cuda, vram_gb=scan.gpu.vram_gb if scan.gpu else None
        )

        def finish(d: ProfileData) -> None:
            d.phase = "scanned"
            d.recommendation = Recommendation(preset=rec.preset, reason=rec.reason) if rec else None

        if not await self._write(pid, run, finish, scanned_at=utcnow()):
            return superseded
        return {"items": len(items), "counts": dict(counts)}

    # ------------------------------------------------------------------ storage

    async def _idle(self, probe: Probe) -> ProfileData:
        """Before the first scan: the quick hardware read (top bar), nothing else."""
        host = await probe.host()
        return ProfileData(
            machine=machine_of(host, await probe.gpu()),
            default_dir=await probe.default_dir(),
            run=new_id(),
        )

    async def _load(self, pid: str) -> tuple[MachineProfileRow, ProfileData] | None:
        async with self.db.session() as s:
            row = await s.get(MachineProfileRow, pid)
        return None if row is None else (row, ProfileData.model_validate(row.data_json))

    async def _get_or_create(self) -> tuple[MachineProfileRow, ProfileData]:
        pid = self.profile_id
        loaded = await self._load(pid)
        if loaded is not None:
            return loaded
        row = MachineProfileRow(
            id=pid, machine=DEFAULT_DEMO_MACHINE if pid == PROFILE_DEMO else None
        )
        data = await self._idle(self.probe_for(row))
        row.data_json = data.model_dump(mode="json")
        async with self.db.session() as s:
            s.add(row)
            await s.commit()
            await s.refresh(row)
        return row, data

    async def _save(
        self,
        pid: str,
        data: ProfileData,
        *,
        machine: str | None = _UNSET,
        scanned_at: datetime | None = _UNSET,
    ) -> None:
        async with self.db.session() as s:
            row = await s.get(MachineProfileRow, pid)
            if row is None:
                raise KeyError(pid)
            row.data_json = data.model_dump(mode="json")
            row.updated_at = utcnow()
            if machine is not _UNSET:
                row.machine = machine
            if scanned_at is not _UNSET:
                row.scanned_at = scanned_at
            s.add(row)
            await s.commit()

    async def _write(
        self,
        pid: str,
        run: str,
        update: Callable[[ProfileData], None],
        *,
        item: dict[str, Any] | None = None,
        scanned_at: datetime | None = _UNSET,
        publish: bool = True,
    ) -> bool:
        """Apply ``update`` if ``run`` is still the profile's, then publish the progress."""
        async with self._lock:
            loaded = await self._load(pid)
            if loaded is None or loaded[1].run != run:
                return False
            data = loaded[1]
            update(data)
            await self._save(pid, data, scanned_at=scanned_at)
            if publish:
                await self._progress(data, item)
            return True

    async def _progress(self, data: ProfileData, item: dict[str, Any] | None) -> None:
        await self.bus.publish(EventType.SETUP_PROGRESS, {"phase": data.phase, "item": item})

    async def _cancel(self, job_id: str | None) -> None:
        if job_id:
            with contextlib.suppress(JobStateError, KeyError):
                await self.jobs.cancel(job_id)

    async def _settle(self, row: MachineProfileRow, data: ProfileData) -> bool:
        """A scan whose job ended without finishing (failed for good): stop showing «checking»."""
        if data.phase != "scanning":
            return False
        job = await self.jobs.get(data.job_id) if data.job_id else None
        if job is not None and job.state not in TERMINAL:
            return False
        if row.scanned_at is None:
            data.phase, data.items = "idle", []
        else:
            data.phase = "scanned"
            failed = msg("check_failed")
            data.items = [
                x.model_copy(update={"status": "warn", "found": failed})
                if x.status == "checking"
                else x
                for x in data.items
            ]
        return True

    @staticmethod
    def _public(row: MachineProfileRow, data: ProfileData) -> MachineProfile:
        return MachineProfile(
            scanned_at=row.scanned_at,
            machine=data.machine,
            phase=data.phase,
            items=data.items,
            install=data.install,
            default_dir=data.default_dir,
            recommendation=data.recommendation,
            simulated=row.id == PROFILE_DEMO,
        )
