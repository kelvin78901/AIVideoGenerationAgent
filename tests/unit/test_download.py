"""The download engine: byte meter, connection tuner, blocks, several connections, resume."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from drama_series_agent.setup import download
from drama_series_agent.setup.download import FileDownload, Meter, Tuner, _Blocks
from drama_series_agent.setup.installer import InstallError, Transfer

BLOB = bytes(range(256)) * 4096  # 1 MiB
BLOB_SHA = hashlib.sha256(BLOB).hexdigest()
BLOCK = 100_000  # 11 blocks of BLOB
URL = "https://huggingface.co/o/r/resolve/main/big.safetensors"


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


class Ticking(Clock):
    def __call__(self) -> float:
        self.t += 1.0  # each look at the clock is a second later
        return self.t


async def _no_sleep(_: float) -> None:
    return None


# --------------------------------------------------------------------------- meter


async def test_meter_reports_bytes_at_most_once_a_second() -> None:
    clock = Clock()
    seen: list[Transfer] = []

    async def report(t: Transfer) -> None:
        seen.append(t)

    m = Meter(report, clock=clock)
    m.expect("a", 1000, 100)  # resumed: 100 bytes were here already
    m.expect("b", None)
    assert m.total == 1000 and m.done == 100  # b's size is not known yet
    m.start()
    for _ in range(10):
        clock.t += 0.25
        m.got("a", 50)
        await m.tick()
    # 2.5 s: reports at 0.25 s (the first), 1.25 s and 2.25 s.
    assert [t.done for t in seen] == [150, 350, 550]
    assert seen[-1].speed == pytest.approx(200.0)  # 50 bytes every 0.25 s, the resumed 100 not
    m.expect("b", 500)
    assert m.total == 1500
    await m.verifying(True)
    assert seen[-1] == Transfer(done=600, total=1500, speed=None, verifying=True)
    m.drop("a", 200)  # a block that failed part way will come again
    assert m.done == 400
    m.stop()
    assert m.average() is None  # too little to go by


async def test_meter_speed_is_the_last_few_seconds() -> None:
    clock = Clock()

    async def report(t: Transfer) -> None:
        return None

    m = Meter(report, clock=clock, window_s=5.0)
    m.expect("a", 10**9)
    m.start()
    assert m.speed() is None
    for _ in range(20):  # 10 s at 1 MB/s
        clock.t += 0.5
        m.got("a", 500_000)
    for _ in range(20):  # then 10 s at 4 MB/s
        clock.t += 0.5
        m.got("a", 2_000_000)
    assert m.speed() == pytest.approx(4e6, rel=0.15)
    m.stop()
    clock.t += 60  # checking the file: not part of the speed
    m.start()
    clock.t += 1
    m.got("a", 1_500_000)
    m.stop()
    assert m.average() == pytest.approx(51.5e6 / 21)


# --------------------------------------------------------------------------- tuner


def test_tuner_keeps_one_connection_when_more_are_slower() -> None:
    """Kelvin's line, 2026-10-18: one connection 25–30 MB/s, more 16–24 MB/s."""
    t = Tuner()
    assert t.judge(27e6) == 2
    assert t.judge(22e6) == 1 and t.settled
    assert t.judge(40e6) == 1  # settled: stays


def test_tuner_adds_connections_while_the_speed_rises() -> None:
    t = Tuner()
    assert [t.judge(s) for s in (10e6, 18e6, 25e6)] == [2, 3, 4]
    assert t.judge(26e6) == 3 and t.settled  # 4 % is not worth a connection
    t = Tuner(max_n=3)
    assert [t.judge(s) for s in (10e6, 20e6, 30e6)] == [2, 3, 3]
    assert t.settled


# --------------------------------------------------------------------------- blocks


def test_a_new_connection_takes_the_middle_of_a_stream_s_run() -> None:
    b = _Blocks.of(10 * BLOCK, BLOCK, done={0, 1})
    assert b.claim_start() == 2  # free run 2..9 after a finished block: from its start
    assert b.claim_start() == 6  # 3..9 follows the stream at 2: split in the middle
    assert b.claim_start() == 4  # 3..5 follows 2 again: 4 gets 4..5
    b.state = ["done", "active", "free", "done", "active", "free"]
    assert b.claim_start() is None  # single free blocks right after a stream: theirs


def test_legacy_part_and_record(tmp_path: Path) -> None:
    assert _Blocks.of(BLOCK * 2 + 5, BLOCK, set()).state == ["free"] * 3


# --------------------------------------------------------------------------- files


class Server:
    """Range server; the body can come in small pieces, some starts can fail or cut short."""

    def __init__(
        self,
        body: bytes = BLOB,
        *,
        piece: int | None = None,
        fail: dict[int, int] | None = None,
        cut: dict[int, int] | None = None,
    ) -> None:
        self.body = body
        self.piece = piece
        self.fail = dict(fail or {})  # start -> times to answer 500
        self.cut = dict(cut or {})  # start -> times to send only half
        self.ranges: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        asked = request.headers.get("range", "")
        if asked != "bytes=0-0":
            self.ranges.append(asked)
        m = re.fullmatch(r"bytes=(\d+)-(\d*)", asked)
        assert m, "every request has a range"
        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) else len(self.body) - 1
        probe = asked == "bytes=0-0"
        if self.fail.get(start) and not probe:
            self.fail[start] -= 1
            return httpx.Response(500)
        data = self.body[start : end + 1]
        if self.cut.get(start) and not probe:
            self.cut[start] -= 1
            data = data[: len(data) // 2]
        headers = {"content-range": f"bytes {start}-{end}/{len(self.body)}"}
        if self.piece is None:
            return httpx.Response(206, content=data, headers=headers)
        return httpx.Response(206, content=_pieces(data, self.piece), headers=headers)


async def _pieces(data: bytes, size: int) -> AsyncIterator[bytes]:
    for i in range(0, len(data), size):
        yield data[i : i + size]


async def _fetch(
    tmp_path: Path,
    server: Server,
    *,
    tuner: Tuner | None = None,
    clock: Clock | None = None,
    sha256: str | None = BLOB_SHA,
    window_s: float = 5.0,
) -> tuple[Path, list[Transfer]]:
    seen: list[Transfer] = []

    async def report(t: Transfer) -> None:
        seen.append(t)

    clock = clock or Clock()
    target = tmp_path / "big.safetensors"
    async with httpx.AsyncClient(transport=httpx.MockTransport(server)) as client:
        meter = Meter(report, clock=clock)
        fd = FileDownload(
            URL,
            target,
            sha256,
            client=client,
            meter=meter,
            tuner=tuner or Tuner(),
            clock=clock,
            sleep=_no_sleep,
            block=BLOCK,
            window_s=window_s,
        )
        await fd.prepare()  # as RealRunner does: sizes and what is here first
        await meter.tick(force=True)
        await fd.run()
    return target, seen


async def test_several_connections_fill_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(download, "CHUNK", 10_000)
    server = Server(piece=10_000)
    target, seen = await _fetch(tmp_path, server, tuner=Tuner(n=3, settled=True))
    assert target.read_bytes() == BLOB
    assert not (tmp_path / "big.safetensors.part").exists()
    assert not (tmp_path / "big.safetensors.part.json").exists()
    starts = sorted(int(re.match(r"bytes=(\d+)-", r).group(1)) for r in server.ranges)  # type: ignore[union-attr]
    assert len(starts) >= 3 and all(s % BLOCK == 0 for s in starts)
    assert seen[-1].done == len(BLOB) and seen[-1].total == len(BLOB)


async def test_resume_from_the_record(tmp_path: Path) -> None:
    part = tmp_path / "big.safetensors.part"
    data = bytearray(len(BLOB))
    for i in (0, 1, 2, 5, 6):
        data[i * BLOCK : (i + 1) * BLOCK] = BLOB[i * BLOCK : (i + 1) * BLOCK]
    part.write_bytes(bytes(data))
    record = {"url": URL, "size": len(BLOB), "block": BLOCK, "done": [0, 1, 2, 5, 6]}
    (tmp_path / "big.safetensors.part.json").write_text(json.dumps(record))
    server = Server()
    target, seen = await _fetch(tmp_path, server)
    assert target.read_bytes() == BLOB
    # The longest gap first (7..10), then 3..4; the stream stops at block 5, which is done.
    assert server.ranges == [f"bytes=700000-{len(BLOB) - 1}", f"bytes=300000-{len(BLOB) - 1}"]
    assert seen[0].done == 5 * BLOCK


async def test_a_record_for_another_size_starts_over(tmp_path: Path) -> None:
    (tmp_path / "big.safetensors.part").write_bytes(b"x" * 300_000)
    record = {"url": URL, "size": 5, "block": BLOCK, "done": [0, 1, 2]}
    (tmp_path / "big.safetensors.part.json").write_text(json.dumps(record))
    server = Server()
    target, _ = await _fetch(tmp_path, server)
    assert target.read_bytes() == BLOB
    assert server.ranges == [f"bytes=0-{len(BLOB) - 1}"]


async def test_a_failed_block_is_tried_again(tmp_path: Path) -> None:
    server = Server(fail={0: 2}, cut={0: 0})
    target, _ = await _fetch(tmp_path, server)
    assert target.read_bytes() == BLOB
    assert len(server.ranges) == 3
    # Cut short: what came of the block is fetched again, the bytes are not counted twice.
    server = Server(cut={0: 1})
    target.unlink()
    target, seen = await _fetch(tmp_path, server)
    assert target.read_bytes() == BLOB
    assert seen[-1].done == len(BLOB)


async def test_a_block_that_keeps_failing_fails_the_file(tmp_path: Path) -> None:
    with pytest.raises(InstallError) as err:
        await _fetch(tmp_path, Server(fail={0: 5}))
    assert err.value.code == "download_failed" and err.value.params["status"] == 500
    # What finished is kept for next time.
    assert (tmp_path / "big.safetensors.part.json").exists()


async def test_the_tuner_decides_how_many_connections(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every window the tuner is told the speed and more connections start."""
    monkeypatch.setattr(download, "CHUNK", 5_000)
    judged: list[int] = []

    class Scripted(Tuner):
        def judge(self, speed: float) -> int:
            judged.append(self.n)
            return super().judge(10e6 * self.n)  # each connection adds as much again

    tuner = Scripted(max_n=3)
    server = Server(piece=5_000)
    target, _ = await _fetch(tmp_path, server, tuner=tuner, clock=Ticking(), window_s=0.0)
    assert target.read_bytes() == BLOB
    assert judged == [1, 2, 3] and tuner.n == 3 and tuner.settled
    assert len(server.ranges) >= 3


async def test_a_connection_that_does_not_help_is_dropped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(download, "CHUNK", 5_000)

    class Slower(Tuner):
        def judge(self, speed: float) -> int:
            return super().judge(10e6 / self.n)  # the second connection makes it slower

    tuner = Slower()
    target, seen = await _fetch(
        tmp_path, Server(piece=5_000), tuner=tuner, clock=Ticking(), window_s=0.0
    )
    assert target.read_bytes() == BLOB
    assert tuner.n == 1 and tuner.settled
    assert seen[-1].done == len(BLOB)  # the dropped connection's bytes are not counted twice
