"""Downloads for the installer: byte progress, several connections, resume (M1 step 8c).

A file is fetched in blocks of 64 MB into ``<name>.part``. Each connection streams from the
start of a free block to the end of the file and claims the blocks it reaches one by one; it
stops at a block another connection has. ``<name>.part.json`` records the finished blocks, so a
restart resumes and a failed request retries only its block. A server that ignores Range gets
one connection from the start. A ``.part`` left by the old single-connection download (no
record) counts as the finished blocks at its start.

How many connections is measured, not set: one to begin with, another while the total speed
keeps rising, and back one as soon as it does not (``Tuner``). On Kelvin's line a single
connection already fills it and more are slower (2026-10-18: 25–30 MB/s with one, 16–24 MB/s
with four or eight), so a fixed number would be wrong.

``Meter`` adds up an item's files: bytes done / total, the speed over the last few seconds and
whether a finished file is being checked; it reports at most once a second.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import math
import re
import sys
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Literal

import httpx

from drama_series_agent.setup.installer import InstallError, Transfer

BLOCK = 64 << 20
CHUNK = 1 << 20
MAX_CONNECTIONS = 8
GAIN = 1.10  # another connection stays only if the total speed rose by 10 %
WINDOW_S = 5.0  # how long a number of connections runs before it is judged
REPORT_S = 1.0
SPEED_WINDOW_S = 5.0
BLOCK_ATTEMPTS = 3  # a block that fails this often in a row fails the file
RETRY_S = 1.0
TIMEOUT = httpx.Timeout(30, read=120)
_CONTENT_RANGE = re.compile(r"bytes (\d+)-(\d+)/(\d+|\*)")

Clock = Callable[[], float]
Sleep = Callable[[float], Awaitable[None]]


# --------------------------------------------------------------------------- meter


class Meter:
    """Bytes of one item's downloads, reported at most every ``every_s`` seconds."""

    def __init__(
        self,
        report: Callable[[Transfer], Awaitable[None]],
        *,
        clock: Clock = time.monotonic,
        every_s: float = REPORT_S,
        window_s: float = SPEED_WINDOW_S,
    ) -> None:
        self._report = report
        self._clock = clock
        self._every = every_s
        self._window = window_s
        self._files: dict[str, tuple[int, int | None]] = {}  # key -> (done, total)
        self.received = 0  # bytes that came over the network in this run
        self._samples: deque[tuple[float, int]] = deque()
        self._last: float | None = None
        self._verifying = False
        self._started: float | None = None
        self._busy_s = 0.0  # time spent receiving (for the measured speed)

    def expect(self, key: str, total: int | None, done: int = 0) -> None:
        self._files[key] = (done, total)

    def got(self, key: str, n: int) -> None:
        done, total = self._files.get(key, (0, None))
        self._files[key] = (done + n, total)
        self.received += n
        now = self._clock()
        self._samples.append((now, self.received))
        while len(self._samples) > 2 and now - self._samples[1][0] >= self._window:
            self._samples.popleft()

    def drop(self, key: str, n: int) -> None:
        """``n`` bytes of ``key`` will be fetched again (a block that failed part way)."""
        done, total = self._files.get(key, (0, None))
        self._files[key] = (max(0, done - n), total)

    def start(self) -> None:
        """Receiving begins (a file starts); ``stop`` ends it. Measures the average speed."""
        self._started = self._clock()
        self._samples.clear()
        self._samples.append((self._started, self.received))

    def stop(self) -> None:
        if self._started is not None:
            self._busy_s += self._clock() - self._started
            self._started = None

    @property
    def done(self) -> int:
        return sum(d for d, _ in self._files.values())

    @property
    def total(self) -> int | None:
        """The sizes known so far; None while none is."""
        known = [t for _, t in self._files.values() if t is not None]
        return sum(known) if known else None

    def speed(self) -> float | None:
        """Bytes per second over the last few seconds; None in the first second."""
        if len(self._samples) < 2:
            return None
        (t0, b0), (t1, b1) = self._samples[0], self._samples[-1]
        return (b1 - b0) / (t1 - t0) if t1 - t0 >= 1.0 else None

    def average(self) -> float | None:
        """This run's speed while receiving: what to expect next time (``download_bps``)."""
        busy = self._busy_s + (self._clock() - self._started if self._started is not None else 0)
        return self.received / busy if busy >= 1.0 and self.received >= CHUNK else None

    def transfer(self) -> Transfer:
        speed = None if self._verifying else self.speed()
        return Transfer(done=self.done, total=self.total, speed=speed, verifying=self._verifying)

    async def tick(self, *, force: bool = False) -> None:
        now = self._clock()
        if force or self._last is None or now - self._last >= self._every:
            self._last = now
            await self._report(self.transfer())

    async def verifying(self, on: bool) -> None:
        self._verifying = on
        await self.tick(force=True)


# --------------------------------------------------------------------------- tuner


@dataclass
class Tuner:
    """How many connections: one more while the total speed keeps rising, then stay.

    Shared by all files of an install run, so a later file starts with what was found.
    """

    max_n: int = MAX_CONNECTIONS
    gain: float = GAIN
    n: int = 1
    settled: bool = False
    best: float | None = None

    def judge(self, speed: float) -> int:
        """``speed`` was measured with ``n`` connections; returns how many to run now."""
        if self.settled:
            return self.n
        if self.best is not None and speed <= self.best * self.gain:
            self.n, self.settled = self.n - 1, True  # no better: back one, and stay
            return self.n
        self.best = speed
        if self.n >= self.max_n:
            self.settled = True
        else:
            self.n += 1
        return self.n


# --------------------------------------------------------------------------- remote


@dataclass(frozen=True)
class Remote:
    size: int | None
    ranges: bool  # the server honours Range


async def probe(client: httpx.AsyncClient, url: str) -> Remote:
    """Size and Range support from one ``Range: bytes=0-0`` request (redirects followed)."""
    async with client.stream("GET", url, headers={"Range": "bytes=0-0"}) as resp:
        if resp.status_code == 206:
            m = _CONTENT_RANGE.fullmatch(resp.headers.get("content-range", ""))
            size = int(m.group(3)) if m and m.group(3) != "*" else None
            return Remote(size=size, ranges=size is not None)
        if resp.status_code == 200:
            length = resp.headers.get("content-length")
            return Remote(size=int(length) if length else None, ranges=False)
        raise InstallError("download_failed", status=resp.status_code, file=url.rsplit("/", 1)[-1])


async def measure_speed(
    client: httpx.AsyncClient, url: str, *, nbytes: int = 16 << 20, timeout_s: float = 15.0
) -> float | None:
    """Bytes per second for the first ``nbytes`` of ``url`` (kept in memory); None if it fails."""
    start = time.perf_counter()
    got = 0
    try:
        async with asyncio.timeout(timeout_s):
            headers = {"Range": f"bytes=0-{nbytes - 1}"}
            async with client.stream("GET", url, headers=headers) as resp:
                if resp.status_code not in (200, 206):
                    return None
                first: float | None = None
                async for chunk in resp.aiter_bytes(CHUNK):
                    if first is None:
                        first = time.perf_counter()  # leave out the redirect and the first byte
                        start = first
                    got += len(chunk)
                    if got >= nbytes:
                        break
    except (httpx.HTTPError, TimeoutError):
        pass
    elapsed = time.perf_counter() - start
    return got / elapsed if got >= (1 << 20) and elapsed > 0 else None


# --------------------------------------------------------------------------- one file


def _sha256_sync(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


async def sha256_of(path: Path) -> str:
    return await asyncio.to_thread(_sha256_sync, path)


def _make_sparse(fh: IO[bytes]) -> None:
    """Windows: a block far into the file must not make NTFS write zeros up to it first."""
    if sys.platform == "win32":
        import ctypes
        import msvcrt
        from ctypes import wintypes

        fsctl_set_sparse = 0x900C4
        handle = wintypes.HANDLE(msvcrt.get_osfhandle(fh.fileno()))
        returned = wintypes.DWORD()
        ctypes.windll.kernel32.DeviceIoControl(
            handle, fsctl_set_sparse, None, 0, None, 0, ctypes.byref(returned), None
        )


def _write_at(fh: IO[bytes], pos: int, data: bytes) -> None:
    fh.seek(pos)
    fh.write(data)


BlockState = Literal["free", "active", "done"]


@dataclass
class _Blocks:
    size: int
    block: int
    state: list[BlockState] = field(default_factory=list)

    @classmethod
    def of(cls, size: int, block: int, done: set[int]) -> _Blocks:
        n = max(1, math.ceil(size / block))
        return cls(size, block, ["done" if i in done else "free" for i in range(n)])

    def end(self, i: int) -> int:
        return min(self.size, (i + 1) * self.block)

    @property
    def finished(self) -> bool:
        return all(s == "done" for s in self.state)

    def done_ids(self) -> list[int]:
        return [i for i, s in enumerate(self.state) if s == "done"]

    def claim_start(self) -> int | None:
        """Where a new connection starts: the free run with the most blocks it would get. A
        run right after a block being streamed is split in the middle (that stream goes on
        into its first half)."""
        best: tuple[int, int] | None = None  # (blocks it gets, start)
        i = 0
        while i < len(self.state):
            if self.state[i] != "free":
                i += 1
                continue
            j = i
            while j < len(self.state) and self.state[j] == "free":
                j += 1
            start = i
            if i > 0 and self.state[i - 1] == "active":
                if j - i < 2:
                    i = j
                    continue
                start = i + (j - i) // 2
            gets = j - start
            if best is None or gets > best[0]:
                best = (gets, start)
            i = j
        if best is None:
            return None
        self.state[best[1]] = "active"
        return best[1]


class FileDownload:
    """One file into ``target``: what is there already, then the blocks still missing."""

    def __init__(
        self,
        url: str,
        target: Path,
        sha256: str | None,
        *,
        client: httpx.AsyncClient,
        meter: Meter,
        tuner: Tuner,
        clock: Clock = time.monotonic,
        sleep: Sleep = asyncio.sleep,
        block: int = BLOCK,
        window_s: float = WINDOW_S,
    ) -> None:
        self.url = url
        self.target = target
        self.sha256 = sha256.lower() if sha256 else None
        self.client = client
        self.meter = meter
        self.tuner = tuner
        self._clock = clock
        self._sleep = sleep
        self._block = block
        self._window = window_s
        self.part = target.with_name(target.name + ".part")
        self.record = target.with_name(target.name + ".part.json")
        self.key = str(target)
        self.remote: Remote | None = None
        self._prepared = False
        self._save_lock = asyncio.Lock()

    # ------------------------------------------------------------------ plan

    async def prepare(self) -> None:
        """Before the item starts: the file's size and how much of it is here (for the meter).
        A failed request leaves the size unknown; ``run`` reports the error."""
        self._prepared = True
        if await asyncio.to_thread(self.target.exists):
            size = (await asyncio.to_thread(self.target.stat)).st_size
            self.meter.expect(self.key, size, size)
            return
        try:
            self.remote = await probe(self.client, self.url)
        except (httpx.HTTPError, InstallError):
            self.meter.expect(self.key, None)
            return
        self.meter.expect(self.key, self.remote.size, await self._have())

    async def _have(self) -> int:
        """Bytes already in ``.part`` that count, by the record (or an old single-connection
        ``.part``)."""
        remote = self.remote
        if remote is None or remote.size is None or not remote.ranges:
            return 0
        blocks = await self._load_blocks(remote.size)
        return sum(blocks.end(i) - i * blocks.block for i in blocks.done_ids())

    async def _load_blocks(self, size: int) -> _Blocks:
        done: set[int] = set()

        def read() -> set[int]:
            if not self.part.exists():
                return set()
            if self.record.exists():
                try:
                    rec = json.loads(self.record.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    return set()
                if rec.get("size") != size or rec.get("block") != self._block:
                    return set()
                return {int(i) for i in rec.get("done", [])}
            # The old download wrote from the start, one connection: its full blocks count.
            have = self.part.stat().st_size
            full = min(have, size) // self._block
            if have >= size:
                full = math.ceil(size / self._block)
            return set(range(full))

        done = await asyncio.to_thread(read)
        return _Blocks.of(size, self._block, done)

    # ------------------------------------------------------------------ run

    async def run(self) -> None:
        if not self._prepared:
            await self.prepare()
        if await asyncio.to_thread(self.target.exists):
            if self.sha256 is None or await self._check(self.target):
                return
            self.meter.expect(self.key, None)  # wrong file there: fetch it again
            await asyncio.to_thread(self.target.unlink)
        await asyncio.to_thread(self.target.parent.mkdir, parents=True, exist_ok=True)
        if self.remote is None:
            try:
                self.remote = await probe(self.client, self.url)
            except httpx.HTTPError as exc:
                raise InstallError(
                    "download_failed", status=type(exc).__name__, file=self.target.name
                ) from None
        remote = self.remote
        self.meter.start()
        try:
            if remote.ranges and remote.size is not None:
                await self._blockwise(remote.size)
            else:
                await self._whole()
        finally:
            self.meter.stop()
        await self.meter.tick(force=True)
        if self.sha256 is not None and not await self._check(self.part):
            await asyncio.to_thread(self._drop_part)
            self.meter.expect(self.key, remote.size)
            raise InstallError("sha256_mismatch", file=self.target.name)
        await asyncio.to_thread(self.part.replace, self.target)
        await asyncio.to_thread(self.record.unlink, missing_ok=True)

    async def _check(self, path: Path) -> bool:
        await self.meter.verifying(True)
        try:
            return await sha256_of(path) == self.sha256
        finally:
            await self.meter.verifying(False)

    def _drop_part(self) -> None:
        self.part.unlink(missing_ok=True)
        self.record.unlink(missing_ok=True)

    async def _whole(self) -> None:
        """One connection from the start (the server ignores Range)."""
        self.meter.expect(self.key, self.remote.size if self.remote else None)
        await asyncio.to_thread(self.record.unlink, missing_ok=True)
        try:
            async with self.client.stream("GET", self.url) as resp:
                if resp.status_code != 200:
                    raise InstallError(
                        "download_failed", status=resp.status_code, file=self.target.name
                    )
                fh = await asyncio.to_thread(self.part.open, "wb")
                try:
                    async for chunk in resp.aiter_bytes(CHUNK):
                        await asyncio.to_thread(fh.write, chunk)
                        self.meter.got(self.key, len(chunk))
                        await self.meter.tick()
                finally:
                    await asyncio.to_thread(fh.close)
        except httpx.HTTPError as exc:
            raise InstallError(
                "download_failed", status=type(exc).__name__, file=self.target.name
            ) from None

    async def _blockwise(self, size: int) -> None:
        blocks = await self._load_blocks(size)
        have = sum(blocks.end(i) - i * blocks.block for i in blocks.done_ids())
        self.meter.expect(self.key, size, have)

        def open_part() -> None:
            self.part.touch()
            with self.part.open("r+b") as fh:
                _make_sparse(fh)

        await asyncio.to_thread(open_part)
        await self._save(blocks)  # an old single-connection .part gets its record now
        workers: dict[asyncio.Task[None], _Lease] = {}
        fails: dict[int, int] = {}
        mark_t, mark_b = self._clock(), self.meter.received
        try:
            while not blocks.finished:
                while len(workers) < self.tuner.n and (start := blocks.claim_start()) is not None:
                    lease = _Lease(start, start * blocks.block)
                    workers[asyncio.create_task(self._stream(blocks, lease, fails))] = lease
                if not workers:  # nothing free and nobody streaming: cannot happen
                    raise InstallError("download_failed", status="blocks", file=self.target.name)
                full = len(workers) == self.tuner.n
                done, _ = await asyncio.wait(
                    workers, timeout=self._window, return_when=asyncio.FIRST_COMPLETED
                )
                for t in done:
                    workers.pop(t)
                    t.result()  # a block that kept failing fails the file
                now = self._clock()
                if now - mark_t >= self._window:
                    if full and not self.tuner.settled:
                        speed = (self.meter.received - mark_b) / (now - mark_t)
                        self.tuner.judge(speed)
                        while len(workers) > self.tuner.n:
                            newest = list(workers)[-1]  # it goes; its block is free again
                            await self._stop(blocks, newest, workers.pop(newest))
                    mark_t, mark_b = now, self.meter.received
        finally:
            for t, lease in list(workers.items()):
                await self._stop(blocks, t, lease)

    async def _stop(self, blocks: _Blocks, task: asyncio.Task[None], lease: _Lease) -> None:
        """Cancel a connection and free its block, also when it never got to run."""
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task
        self._release(blocks, lease)

    async def _stream(self, blocks: _Blocks, lease: _Lease, fails: dict[int, int]) -> None:
        """Stream from the leased block on, claiming each next free block; stop at one taken.
        Cancelled, it leaves its block to ``_stop``."""
        i, pos = lease.i, lease.pos
        fh = await asyncio.to_thread(self.part.open, "r+b")
        try:
            headers = {"Range": f"bytes={pos}-{blocks.size - 1}"}
            async with self.client.stream("GET", self.url, headers=headers) as resp:
                if resp.status_code != 206 or not resp.headers.get("content-range", "").startswith(
                    f"bytes {pos}-"
                ):
                    raise _BlockError(resp.status_code)
                async for chunk in resp.aiter_bytes(CHUNK):
                    data = chunk
                    while data:
                        room = blocks.end(i) - pos
                        part, data = data[:room], data[room:]
                        await asyncio.to_thread(_write_at, fh, pos, part)
                        pos += len(part)
                        lease.pos = pos
                        self.meter.got(self.key, len(part))
                        if pos >= blocks.end(i):
                            await asyncio.to_thread(fh.flush)
                            blocks.state[i] = "done"
                            fails.pop(i, None)
                            lease.held = False
                            await self._save(blocks)
                            i += 1
                            if i >= len(blocks.state) or blocks.state[i] != "free":
                                return
                            blocks.state[i] = "active"
                            lease.i, lease.held = i, True
                    await self.meter.tick()
            if blocks.state[i] == "active":  # the stream ended early
                raise _BlockError("short")
        except (httpx.HTTPError, _BlockError) as exc:
            status = exc.status if isinstance(exc, _BlockError) else type(exc).__name__
            self._release(blocks, lease)
            fails[i] = fails.get(i, 0) + 1
            if fails[i] >= BLOCK_ATTEMPTS:
                raise InstallError(
                    "download_failed", status=status, file=self.target.name
                ) from None
            await self._sleep(RETRY_S * fails[i])
        finally:
            await asyncio.to_thread(fh.close)

    def _release(self, blocks: _Blocks, lease: _Lease) -> None:
        """The leased block goes back to free; what of it was counted comes off the meter."""
        if lease.held and blocks.state[lease.i] == "active":
            blocks.state[lease.i] = "free"
            self.meter.drop(self.key, lease.pos - lease.i * blocks.block)
        lease.held = False

    async def _save(self, blocks: _Blocks) -> None:
        rec = {"url": self.url, "size": blocks.size, "block": blocks.block}
        rec["done"] = blocks.done_ids()

        def write() -> None:
            tmp = self.record.with_name(self.record.name + ".tmp")
            tmp.write_text(json.dumps(rec), encoding="utf-8")
            tmp.replace(self.record)

        async with self._save_lock:
            await asyncio.to_thread(write)


@dataclass
class _Lease:
    """The block a connection is writing and how far it got."""

    i: int
    pos: int
    held: bool = True


class _BlockError(Exception):
    def __init__(self, status: int | str) -> None:
        super().__init__(status)
        self.status = status
