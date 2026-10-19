"""Setup (SPEC 12.2): the machine profile, the scan job and Mock's sample machines.

One profile row per machine: ``local`` is this computer (``RealProbe``), ``demo`` is the
prototype's sample machines (``FakeProbe``, Mock mode; PC or Mac). ``DRAMA_SETUP=real|fake``
picks explicitly; otherwise Mock mode means fake.

A scan is a ``setup.scan`` job on the cpu queue. It rewrites the profile item by item and
publishes ``setup.progress`` after each one. Every scan or reset draws a new ``run`` token; a
job whose token is no longer the profile's stops without writing, so a rescan or a machine
switch never mixes two scans. All profile writes go through one lock. What the last finished
scan found (plus what installed since) tells the router which local models can run here
(``capabilities()``, SPEC 7.3).

An install is a ``setup.install`` job: it takes the queued items one at a time in dependency
order (the order ``POST /setup/install`` stored), skips those whose dependency did not make
it, and records what succeeded in ``installed_item``. Retrying an item while the job runs just
queues it again; after the job has finished it starts a new one. An install that needs elevation
or a big download waits for the user (``waiting_confirm``, SPEC 12.2-5), and so does one that
changes the user's own ComfyUI (SPEC 6.4.1): the change list is shown first, and a
ComfyUI-Manager snapshot is taken right before the first change. Without a snapshot those items
do not run.
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
from loguru import logger
from sqlalchemy.exc import IntegrityError
from sqlmodel import col, delete, desc, select

from drama_series_agent.core.capabilities import FOUND_STATUSES, Capabilities
from drama_series_agent.core.db import Database
from drama_series_agent.core.events import EventBus, EventType
from drama_series_agent.core.jobs import TERMINAL, JobContext, JobQueue, JobStateError
from drama_series_agent.core.models_db import (
    ComfyEnvRow,
    ComfySnapshotRow,
    InstalledItem,
    MachineProfileRow,
    new_id,
    utcnow,
)
from drama_series_agent.core.paths import drama_home
from drama_series_agent.modelhub.registry import is_mock_mode
from drama_series_agent.setup.comfy import ComfyEnvInfo, ComfyScan, NodePack, identify
from drama_series_agent.setup.detectors import (
    Detection,
    ScanContext,
    detect_item,
    msg,
)
from drama_series_agent.setup.installer import (
    INSTALL_JOB,
    FakeRunner,
    Installed,
    InstallEnv,
    InstallError,
    ItemRunner,
    LogLevel,
    Transfer,
    comfy_change,
    confirm_reasons,
    install_order,
)
from drama_series_agent.setup.manifest import Item, Manifest, load_manifest
from drama_series_agent.setup.pathutil import dirname, inside, join, same_path
from drama_series_agent.setup.probe import FakeProbe, HostInfo, Probe, RealProbe
from drama_series_agent.setup.schema import (
    ComfyEnvOut,
    ComfySnapshot,
    ComfyView,
    InstallInfo,
    InstallRequest,
    ItemInstall,
    MachineProfile,
    ProfileData,
    Recommendation,
    Restored,
    SetupItem,
    checking,
    item_of,
    machine_of,
)
from drama_series_agent.setup.snapshots import (
    FakeSnapshots,
    ManagerSnapshots,
    SnapshotError,
    SnapshotFailure,
    Snapshots,
    prepare_restore,
)
from drama_series_agent.setup.steps import RealRunner, speed_test_url

SCAN_JOB = "setup.scan"
MANAGER = "comfy_manager"  # the manifest item that takes the snapshots
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


class NothingSelected(Exception):
    """None of the requested items can be installed."""


class NothingToConfirm(Exception):
    """No install is waiting for the user's go-ahead."""


class ItemNotFound(Exception):
    def __init__(self, item_id: str) -> None:
        super().__init__(item_id)
        self.item_id = item_id


class ItemState(ItemNotFound):
    """The item's install is not in a state that allows this (retry / skip)."""


class NoComfy(Exception):
    """The last scan found no ComfyUI of the user's to snapshot."""


class SnapshotNotFound(Exception):
    pass


class SnapshotFailed(Exception):
    def __init__(self, reason: SnapshotFailure) -> None:
        super().__init__(reason)
        self.reason = reason


class _Superseded(Exception):
    """A newer scan, install or reset took over the profile; the job stops writing."""


def _blocker(
    item: Item, states: dict[str, SetupItem], installed: set[str]
) -> tuple[str, str] | None:
    """Why ``item`` cannot go ahead: a dependency that is not on this machine and did not install.

    A dependency the scan found (even an old one) counts, so a failed update does not block the
    items that need it.
    """
    for dep in item.depends_on:
        x = states.get(dep)
        if x is None or dep in installed or x.status in ("ok", "old", "warn"):
            continue
        if x.install is None:
            return "dependency_missing", dep
        if x.install.state in ("failed", "skipped"):
            return "dependency_failed", dep
    return None


class SetupService:
    def __init__(
        self,
        db: Database,
        bus: EventBus,
        jobs: JobQueue,
        *,
        manifest: Callable[[], Manifest] = load_manifest,
        transport: httpx.AsyncBaseTransport | None = None,
        runner: Callable[[MachineProfileRow], ItemRunner] | None = None,
        snapshots: Callable[[MachineProfileRow, ProfileData], Snapshots] | None = None,
    ) -> None:
        self.db = db
        self.bus = bus
        self.jobs = jobs
        self._manifest = manifest
        self._transport = transport
        self._runner = runner
        self._snapshots = snapshots
        self._lock = asyncio.Lock()
        jobs.register(SCAN_JOB, self._scan_job)
        jobs.register(INSTALL_JOB, self._install_job)

    # ------------------------------------------------------------------ queries

    @property
    def profile_id(self) -> str:
        return PROFILE_DEMO if setup_mode() == "fake" else PROFILE_LOCAL

    def probe_for(self, row: MachineProfileRow) -> Probe:
        if row.id == PROFILE_DEMO:
            return FakeProbe.load(row.machine or DEFAULT_DEMO_MACHINE)
        return RealProbe(self._transport)

    def runner_for(self, row: MachineProfileRow) -> ItemRunner:
        if self._runner is not None:
            return self._runner(row)
        if row.id == PROFILE_DEMO:
            return FakeRunner()
        return RealRunner(
            mirrors=self._manifest().mirrors, transport=self._transport, already=self._already_ok
        )

    def snapshots_for(self, row: MachineProfileRow, data: ProfileData) -> Snapshots:
        if self._snapshots is not None:
            return self._snapshots(row, data)
        if row.id == PROFILE_DEMO:
            return FakeSnapshots()
        url = (data.comfy.url if data.comfy else None) or data.facts.get("comfy", {}).get("url")
        return ManagerSnapshots(url or "http://127.0.0.1:8188", self._transport)

    async def _already_ok(self, item: Item, env: InstallEnv) -> bool:
        """Installed by hand since the scan? Ask its detector again, on the real machine."""
        manifest = self._manifest()
        ctx = await ScanContext.create(
            RealProbe(self._transport),
            manifest.for_platform(env.os),
            mirrors=manifest.mirrors,
            envs=env.envs,
            models=env.models,
        )
        return (await detect_item(item, ctx)).status == "ok"

    async def profile(self) -> MachineProfile:
        async with self._lock:
            row, data = await self._current()
            return self._public(row, data)

    async def capabilities(self) -> Capabilities | None:
        """What this machine can run locally (core/capabilities.py); None before the first scan.

        Reads the stored row without the lock: every write replaces it whole.
        """
        loaded = await self._load(self.profile_id)
        data = loaded[1] if loaded is not None else None
        if data is None or data.found is None:
            return None
        gpu = data.machine.gpu
        return Capabilities.of(cuda=gpu is not None and gpu.backend == "cuda", found=data.found)

    async def comfy_env(self) -> ComfyView:
        """The ComfyUI the last finished scan found and its environment (SPEC 6.4.1)."""
        loaded = await self._load(self.profile_id)
        row, data = loaded if loaded is not None else (None, None)
        scan = data.comfy if data is not None else None
        env: ComfyEnvOut | None = None
        if scan is not None:
            async with self.db.session() as s:
                stored = await s.get(ComfyEnvRow, scan.env_hash)
            if stored is not None:
                env = ComfyEnvOut(
                    hash=stored.hash,
                    captured_at=stored.captured_at,
                    comfyui_version=stored.comfyui_version,
                    comfyui_commit=stored.comfyui_commit,
                    python=stored.python,
                    torch=stored.torch,
                    node_packs=[NodePack.model_validate(p) for p in stored.node_packs_json],
                )
        return ComfyView(
            scanned_at=row.scanned_at if row is not None else None,
            simulated=self.profile_id == PROFILE_DEMO,
            comfy=scan,
            env=env,
        )

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
            row, data = await self._current()
            if data.phase == "installing":
                raise SetupBusy
            await self._cancel(data.job_id)
            host = await self.probe_for(row).host()
            data.phase = "scanning"
            data.items = [checking(x) for x in self._manifest().for_platform(host.os)]
            await self._enqueue(row.id, data, SCAN_JOB)
            await self._progress(data, None)
            return self._public(row, data)

    async def start_install(self, req: InstallRequest) -> MachineProfile:
        async with self._lock:
            row, data = await self._current()
            if data.phase in ("scanning", "installing"):
                raise SetupBusy
            items = self._manifest().for_platform(data.machine.os)
            by_id = {x.id: x for x in items}
            states = {x.id: x for x in data.items}
            installable = {x.id for x in data.items if x.installable and x.id in by_id}
            selected = [i for i in req.items if i in installable]
            # Changing the user's ComfyUI needs a snapshot, so ComfyUI-Manager comes first.
            if any(states[i].touches_comfy for i in selected) and MANAGER in installable:
                selected.append(MANAGER)
            order = install_order(items, selected)
            if not order:
                raise NothingSelected
            # Into the found ComfyUI (its only dependency) Manager goes first, so the snapshot
            # comes before every other change; into one we install, after that ComfyUI.
            if MANAGER in order and states[MANAGER].touches_comfy:
                order.insert(0, order.pop(order.index(MANAGER)))
            changes = [
                comfy_change(
                    by_id[i],
                    status=states[i].status,
                    version=data.facts.get(i, {}).get("version"),
                )
                for i in order
                if states[i].touches_comfy
            ]
            reasons = changes + confirm_reasons([by_id[i] for i in order], data.machine.os)
            data.phase = "installing"
            data.install = InstallInfo(
                items=order, mirror=req.mirror, dir=req.dir, confirm=reasons, changes=changes
            )
            for x in data.items:
                x.install = ItemInstall(state="queued") if x.id in order else None
            await self._enqueue(row.id, data, INSTALL_JOB, wait=bool(reasons))
            await self._log("info", "mirror", mirror=req.mirror, dir=req.dir)
            if data.app_dir and inside(req.dir, data.app_dir):
                await self._log("warn", "dir_in_app", dir=req.dir)
            if reasons:
                await self._log("warn", "confirm")
            await self._progress(data, None)
            return self._public(row, data)

    async def confirm_install(self) -> MachineProfile:
        """The user approved elevation / big downloads: the install job may start."""
        async with self._lock:
            row, data = await self._current()
            if not self._waiting(data) or data.install is None or data.job_id is None:
                raise NothingToConfirm
            try:
                await self.jobs.confirm(data.job_id)
            except (JobStateError, KeyError):
                raise NothingToConfirm from None
            data.install.confirm = []
            await self._save(row.id, data)
            await self._progress(data, None)
            return self._public(row, data)

    async def cancel_install(self) -> MachineProfile:
        """The user declined: nothing starts, back to the scan result."""
        async with self._lock:
            row, data = await self._current()
            if not self._waiting(data) or data.install is None:
                raise NothingToConfirm
            await self._cancel(data.job_id)
            data.install.confirm = []
            data.phase = "scanned"
            for x in data.items:
                x.install = None
            data.run = new_id()
            await self._save(row.id, data)
            await self._log("info", "cancel")
            await self._progress(data, None)
            return self._public(row, data)

    async def retry(self, item_id: str) -> MachineProfile:
        async with self._lock:
            row, data = await self._current()
            x = self._install_item(data, item_id)
            assert x.install is not None
            if x.install.state not in ("failed", "skipped"):
                raise ItemState(item_id)
            x.install = ItemInstall(state="queued")
            if data.install is not None:
                data.install.snapshot_error = None  # e.g. ComfyUI is open now: try again
            if data.phase == "installing":
                await self._save(row.id, data)  # the running job picks it up
            else:
                data.phase = "installing"
                await self._enqueue(row.id, data, INSTALL_JOB)
            await self._log("info", "retry", item=item_id)
            await self._progress(data, x.model_dump(mode="json"))
            return self._public(row, data)

    async def skip(self, item_id: str) -> MachineProfile:
        async with self._lock:
            row, data = await self._current()
            x = self._install_item(data, item_id)
            assert x.install is not None
            if x.install.state not in ("failed", "queued"):
                raise ItemState(item_id)
            x.install = x.install.model_copy(update={"state": "skipped"})
            await self._save(row.id, data)
            await self._log("info", "skip", item=item_id)
            await self._progress(data, x.model_dump(mode="json"))
            return self._public(row, data)

    async def switch_machine(self, machine: DemoMachine) -> MachineProfile:
        """Mock only: scan the other sample machine. Starts over: no scan, nothing installed,
        no snapshots."""
        async with self._lock:
            if self.profile_id != PROFILE_DEMO:
                raise NotSimulated
            row, data = await self._current()
            await self._cancel(data.job_id)
            row.machine = machine
            fresh = await self._idle(self.probe_for(row))
            async with self.db.session() as s:
                await s.exec(
                    delete(InstalledItem).where(col(InstalledItem.profile_id) == PROFILE_DEMO)
                )
                await s.exec(
                    delete(ComfySnapshotRow).where(col(ComfySnapshotRow.profile_id) == PROFILE_DEMO)
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
        scan = await ScanContext.create(
            probe,
            items,
            mirrors=manifest.mirrors,
            envs=self._envs(host, simulated=probe.simulated),
            models=data.install.dir if data.install else None,
        )
        # A sample machine cannot change, so what we installed on it is what counts (SPEC 12.2-3).
        installed = await self.installed(pid) if probe.simulated else set()
        machine = machine_of(host, scan.gpu)
        default_dir = await probe.default_dir()
        app_dir = await probe.app_dir()

        def reset(d: ProfileData) -> None:
            d.machine, d.default_dir, d.app_dir = machine, default_dir, app_dir
            d.items = [checking(x) for x in items]
            d.facts = {}

        # Silent: start_scan already announced the phase (a restarted job lands here again).
        if not await self._write(pid, run, reset, publish=False):
            return superseded
        # The user's own ComfyUI, as opposed to none or the one we installed (SPEC 6.4.1).
        inst = await scan.comfy()
        ours = join(dirname(scan.vars["envs"]), "ComfyUI")
        theirs = inst is not None and (inst.root is None or not same_path(inst.root, ours))
        step = fake_step_s() if probe.simulated else 0.0
        counts: Counter[str] = Counter()
        seen: dict[str, dict[str, Any]] = {}
        for i, x in enumerate(items):
            if step:
                await asyncio.sleep(step)
            det = await detect_item(x, scan)
            if x.id in installed and det.status != "ok":
                det = Detection(status="ok", found=msg("installed"), fix=None, installable=False)
            counts[det.status] += 1
            public = item_of(x, det, touches_comfy=theirs and x.touches_comfy)
            facts = {**det.facts, **({"version": det.version} if det.version else {})}
            seen[x.id] = facts

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
        comfy = await self._identify(scan)
        rec = manifest.recommendation(
            cuda=scan.has_cuda, vram_gb=scan.gpu.vram_gb if scan.gpu else None
        )
        # No measured speed yet (no install here so far): time a short download.
        bps: float | None = None
        if data.download_bps is None and (url := speed_test_url(items, manifest.mirrors, seen)):
            bps = await probe.download_speed(url)

        def finish(d: ProfileData) -> None:
            d.phase = "scanned"
            d.recommendation = Recommendation(preset=rec.preset, reason=rec.reason) if rec else None
            d.found = [x.id for x in d.items if x.status in FOUND_STATUSES]
            d.comfy = comfy
            if bps is not None and d.download_bps is None:
                d.download_bps = round(bps)

        if not await self._write(pid, run, finish, scanned_at=utcnow()):
            return superseded
        return {"items": len(items), "counts": dict(counts)}

    async def _identify(self, scan: ScanContext) -> ComfyScan | None:
        """Read the ComfyUI the scan found (read-only) and keep its environment by hash."""
        inst = await scan.comfy()
        if inst is None:
            return None
        try:
            found = await identify(scan.probe, scan.host, inst, await scan.object_info())
        except Exception:
            logger.exception("identifying ComfyUI at {} failed", inst.root or inst.url)
            return None
        await self._keep_env(found.scan.env_hash, found.env)
        return found.scan

    async def _keep_env(self, env_hash: str, env: ComfyEnvInfo) -> None:
        """A new ``comfy_env`` row only when this environment has not been seen before."""
        async with self.db.session() as s:
            if await s.get(ComfyEnvRow, env_hash) is not None:
                return
            s.add(
                ComfyEnvRow(
                    hash=env_hash,
                    comfyui_version=env.comfyui_version,
                    comfyui_commit=env.comfyui_commit,
                    python=env.python,
                    torch=env.torch,
                    node_packs_json=[p.model_dump(mode="json") for p in env.node_packs],
                )
            )
            try:
                await s.commit()
            except IntegrityError:  # a scan it replaced stored the same one meanwhile
                await s.rollback()

    # ------------------------------------------------------------------ install job

    async def _install_job(self, ctx: JobContext) -> dict[str, Any]:
        pid, run = str(ctx.params["profile_id"]), str(ctx.params["run"])
        try:
            async with self._lock:
                data = await self._load_run(pid, run)
                # Back after a restart: the item that was running starts over.
                for x in data.items:
                    if x.install is not None and x.install.state == "running":
                        x.install = ItemInstall(state="queued")
                await self._save(pid, data)
            loaded = await self._load(pid)
            assert loaded is not None
            row = loaded[0]
            runner = self.runner_for(row)
            items = {x.id: x for x in self._manifest().for_platform(data.machine.os)}
            env = await self._install_env(row, data)
            while (nxt := await self._next_item(pid, run, items)) is not None:
                item, touches = nxt
                snapshot = row if touches and item.snapshot_first else None
                await self._install_one(pid, run, item, runner, env, snapshot_for=snapshot)
            done = await self._load_run(pid, run)
        except _Superseded:
            return {"superseded": True}
        states = Counter(x.install.state for x in done.items if x.install is not None)
        return {"states": dict(states)}

    async def _next_item(
        self, pid: str, run: str, items: dict[str, Item]
    ) -> tuple[Item, bool] | None:
        """Mark the next queued item running; return it and whether it changes the user's
        ComfyUI. None (and phase done) when nothing is left."""
        async with self._lock:
            data = await self._load_run(pid, run)
            assert data.install is not None
            installed = await self.installed(pid)
            states = {x.id: x for x in data.items}
            for item_id in data.install.items:
                x = states.get(item_id)
                if x is None or x.install is None or x.install.state != "queued":
                    continue
                item = items.get(item_id)
                blocked = (
                    _blocker(item, states, installed) if item else ("dependency_missing", item_id)
                )
                if blocked is not None:
                    code, dep = blocked
                    x.install = ItemInstall(state="skipped", error=msg(code, item=dep))
                    await self._save(pid, data)
                    await self._log("warn", "skip_dep", item=item_id, dep=dep)
                    await self._progress(data, x.model_dump(mode="json"))
                    continue
                assert item is not None
                x.install = ItemInstall(state="running")
                await self._save(pid, data)
                await self._log("info", "start", item=item_id)
                await self._progress(data, x.model_dump(mode="json"))
                return item, x.touches_comfy
            data.phase = "done"
            await self._save(pid, data)
            await self._log("ok", "finish")
            await self._progress(data, None)
            return None

    async def _install_one(
        self,
        pid: str,
        run: str,
        item: Item,
        runner: ItemRunner,
        env: InstallEnv,
        *,
        snapshot_for: MachineProfileRow | None = None,
    ) -> None:
        """Install one item; with ``snapshot_for``, only after a snapshot of the user's ComfyUI."""

        async def progress(pct: float, transfer: Transfer | None = None) -> None:
            update: dict[str, Any] = {"pct": max(0.0, min(99.0, round(pct, 1)))}
            if transfer is not None:
                left = transfer.total - transfer.done if transfer.total is not None else None
                speed = transfer.speed
                update |= {
                    "bytes_done": transfer.done,
                    "bytes_total": transfer.total,
                    "speed": round(speed) if speed else None,
                    "eta_s": round(left / speed) if speed and left is not None else None,
                    "verifying": transfer.verifying,
                }
            await self._update_item(pid, run, item.id, lambda i: i.model_copy(update=update))

        async def log(level: LogLevel, code: str, params: dict[str, Any]) -> None:
            await self._log(level, code, **params)

        error: Any = None
        try:
            if snapshot_for is not None:
                await self._ensure_snapshot(pid, run, snapshot_for)
            result = await runner.install(item, env, log, progress)
        except InstallError as exc:
            error = exc.message()
        except (asyncio.CancelledError, _Superseded):
            raise
        except Exception as exc:
            logger.exception("installing {} failed", item.id)
            error = msg("internal", message=str(exc)[:300])
        if error is not None:
            failed = "fail" if item.required else "fail_optional"
            await self._update_item(
                pid,
                run,
                item.id,
                lambda i: i.model_copy(update={"state": "failed", "error": error}),
                log=("warn", failed, {"item": item.id}),
            )
            return
        await self._update_item(
            pid,
            run,
            item.id,
            lambda i: ItemInstall(state="done", pct=100),
            log=("ok", "done", {"item": item.id}),
            record=result,
        )

    async def _ensure_snapshot(self, pid: str, run: str, row: MachineProfileRow) -> None:
        """One snapshot per install run, before its first change to the user's ComfyUI.

        Raises ``InstallError(snapshot_<reason>)`` when none can be taken; the reason is kept
        for the run, so the other items fail fast (a retry clears it).
        """
        async with self._lock:
            data = await self._load_run(pid, run)
            info = data.install
            assert info is not None
            if info.snapshot is not None:
                return
            if info.snapshot_error is not None:
                raise InstallError(info.snapshot_error.code)
            manager = next((x for x in data.items if x.id == MANAGER), None)
            just_installed = (
                manager is not None
                and manager.install is not None
                and (manager.install.state == "done")
            )
        reason: SnapshotFailure | None = "restart" if just_installed else None
        name: str | None = None
        if reason is None:
            try:
                name = await self.snapshots_for(row, data).save()
            except SnapshotError as exc:
                reason = exc.reason
        async with self._lock:
            data = await self._load_run(pid, run)
            assert data.install is not None
            if name is not None:
                snap = await self._add_snapshot(pid, name, data, "install", data.install.changes)
                data.install.snapshot = snap.id
                await self._save(pid, data)
                await self._log("ok", "snapshot", name=name)
                return
            assert reason is not None
            data.install.snapshot_error = msg(f"snapshot_{reason}")
            await self._save(pid, data)
            await self._log("warn", "snapshot_failed", reason=reason)
        raise InstallError(f"snapshot_{reason}")

    async def _add_snapshot(
        self, pid: str, name: str, data: ProfileData, reason: str, changes: list[Any]
    ) -> ComfySnapshotRow:
        row = ComfySnapshotRow(
            profile_id=pid,
            manager_name=name,
            env_hash=data.comfy.env_hash if data.comfy else None,
            reason=reason,
            changes_json=[m.model_dump(mode="json") for m in changes],
        )
        async with self.db.session() as s:
            s.add(row)
            await s.commit()
            await s.refresh(row)
        return row

    @staticmethod
    def _snapshot_of(row: ComfySnapshotRow) -> ComfySnapshot:
        return ComfySnapshot.model_validate(
            {
                "id": row.id,
                "manager_name": row.manager_name,
                "env_hash": row.env_hash,
                "reason": row.reason,
                "changes": row.changes_json,
                "created_at": row.created_at,
                "restored_at": row.restored_at,
            }
        )

    async def snapshots(self) -> list[ComfySnapshot]:
        async with self.db.session() as s:
            rows = await s.exec(
                select(ComfySnapshotRow)
                .where(col(ComfySnapshotRow.profile_id) == self.profile_id)
                .order_by(desc(col(ComfySnapshotRow.created_at)))
            )
            return [self._snapshot_of(r) for r in rows.all()]

    async def take_snapshot(self) -> ComfySnapshot:
        """A snapshot on request (reason ``manual``)."""
        loaded = await self._load(self.profile_id)
        if loaded is None or loaded[1].comfy is None:
            raise NoComfy
        row, data = loaded
        try:
            name = await self.snapshots_for(row, data).save()
        except SnapshotError as exc:
            raise SnapshotFailed(exc.reason) from None
        return self._snapshot_of(await self._add_snapshot(row.id, name, data, "manual", []))

    async def restore_snapshot(self, snapshot_id: str) -> Restored:
        """Ask ComfyUI-Manager to restore it; it takes effect when ComfyUI next starts."""
        loaded = await self._load(self.profile_id)
        async with self.db.session() as s:
            snap = await s.get(ComfySnapshotRow, snapshot_id)
        if loaded is None or snap is None or snap.profile_id != self.profile_id:
            raise SnapshotNotFound
        row, data = loaded
        if data.phase == "installing":
            raise SetupBusy
        if row.id != PROFILE_DEMO and data.comfy and data.comfy.root:
            with contextlib.suppress(OSError):  # Manager may still manage without it
                await asyncio.to_thread(prepare_restore, data.comfy.root)
        try:
            await self.snapshots_for(row, data).restore(snap.manager_name)
        except SnapshotError as exc:
            raise SnapshotFailed(exc.reason) from None
        async with self.db.session() as s:
            stored = await s.get(ComfySnapshotRow, snapshot_id)
            assert stored is not None
            stored.restored_at = utcnow()
            s.add(stored)
            await s.commit()
            await s.refresh(stored)
        return Restored(snapshot=self._snapshot_of(stored))

    async def _update_item(
        self,
        pid: str,
        run: str,
        item_id: str,
        change: Callable[[ItemInstall], ItemInstall],
        *,
        log: tuple[LogLevel, str, dict[str, Any]] | None = None,
        record: Installed | None = None,
    ) -> None:
        async with self._lock:
            data = await self._load_run(pid, run)
            x = next((i for i in data.items if i.id == item_id), None)
            if x is None or x.install is None:
                return
            x.install = change(x.install)
            if record is not None:
                await self._record(pid, item_id, record)
                if data.found is not None and item_id not in data.found:
                    data.found.append(item_id)
                if record.bps:
                    data.download_bps = round(record.bps)
            await self._save(pid, data)
            if log is not None:
                await self._log(log[0], log[1], **log[2])
            await self._progress(data, x.model_dump(mode="json"))

    async def _record(self, pid: str, item_id: str, result: Installed) -> None:
        async with self.db.session() as s:
            row = await s.get(InstalledItem, (pid, item_id))
            if row is None:
                row = InstalledItem(profile_id=pid, item_id=item_id)
            row.version = result.version
            row.paths_json = list(result.paths)
            row.installed_at = utcnow()
            s.add(row)
            await s.commit()

    async def _install_env(self, row: MachineProfileRow, data: ProfileData) -> InstallEnv:
        assert data.install is not None
        probe = self.probe_for(row)
        host = await probe.host()
        envs = self._envs(host, simulated=probe.simulated)
        comfy = data.facts.get("comfy", {})
        return InstallEnv(
            os=host.os,
            mirror=data.install.mirror,
            models=data.install.dir,
            envs=envs,
            comfy=comfy.get("root") or join(dirname(envs), "ComfyUI"),
            comfy_python=comfy.get("python"),
            model_dirs=list(data.comfy.model_dirs) if data.comfy else [],
            facts=data.facts,
        )

    # ------------------------------------------------------------------ storage

    @staticmethod
    def _envs(host: HostInfo, *, simulated: bool) -> str:
        """``~/.drama-studio/envs``; the sample machines have their own home folder."""
        if simulated:
            return join(host.home, ".drama-studio", "envs")
        return str(drama_home() / "envs")

    async def _current(self) -> tuple[MachineProfileRow, ProfileData]:
        row, data = await self._get_or_create()
        if await self._settle(row, data):
            await self._save(row.id, data)
        return row, data

    async def _load_run(self, pid: str, run: str) -> ProfileData:
        loaded = await self._load(pid)
        if loaded is None or loaded[1].run != run:
            raise _Superseded
        return loaded[1]

    async def _enqueue(self, pid: str, data: ProfileData, kind: str, *, wait: bool = False) -> None:
        """Start ``kind`` under a new run token and save the profile (caller holds the lock)."""
        data.run = new_id()
        job = await self.jobs.enqueue(
            kind, "cpu", {"profile_id": pid, "run": data.run}, max_attempts=3, wait_for_confirm=wait
        )
        data.job_id = job.id
        await self._save(pid, data)

    @staticmethod
    def _waiting(data: ProfileData) -> bool:
        return data.phase == "installing" and bool(data.install and data.install.confirm)

    @staticmethod
    def _install_item(data: ProfileData, item_id: str) -> SetupItem:
        x = next((i for i in data.items if i.id == item_id), None)
        if x is None or x.install is None:
            raise ItemNotFound(item_id)
        return x

    async def _log(self, level: LogLevel, code: str, **params: Any) -> None:
        await self.bus.publish(
            EventType.SETUP_LOG, {"level": level, "code": code, "params": params}
        )

    async def _idle(self, probe: Probe) -> ProfileData:
        """Before the first scan: the quick hardware read (top bar), nothing else."""
        host = await probe.host()
        return ProfileData(
            machine=machine_of(host, await probe.gpu()),
            default_dir=await probe.default_dir(),
            app_dir=await probe.app_dir(),
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
            try:
                data = await self._load_run(pid, run)
            except _Superseded:
                return False
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
        """A scan or install whose job ended without finishing (failed for good, e.g. it kept
        crashing the process): stop showing «checking» / «queued»."""
        if data.phase not in ("scanning", "installing"):
            return False
        job = await self.jobs.get(data.job_id) if data.job_id else None
        if job is not None and job.state not in TERMINAL:
            return False
        if data.phase == "installing":
            data.phase = "done"
            for x in data.items:
                if x.install is not None and x.install.state in ("queued", "running"):
                    x.install = x.install.model_copy(
                        update={"state": "failed", "error": msg("interrupted")}
                    )
        elif row.scanned_at is None:
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
            app_dir=data.app_dir,
            recommendation=data.recommendation,
            simulated=row.id == PROFILE_DEMO,
            download_bps=data.download_bps,
        )
