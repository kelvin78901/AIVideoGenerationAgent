"""The local Python runtime against a fake worker that speaks the real protocol: one resident
process per model, timeouts kill it, the VRAM lease makes the previous model let go."""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator
from dataclasses import replace
from pathlib import Path

import pytest

from drama_series_agent.core.paths import REPO_ROOT
from drama_series_agent.modelhub.adapters.base import (
    CallContext,
    ModelError,
    ModelRequest,
    ModelSpec,
)
from drama_series_agent.modelhub.adapters.local_python import LocalPythonAdapter, RuntimePaths
from drama_series_agent.modelhub.vram import VramLease

FAKE_WORKERS = REPO_ROOT / "tests" / "fixtures" / "workers"
# The base interpreter, not the venv launcher: on Windows the launcher's child outlives a kill.
PYTHON = Path(getattr(sys, "_base_executable", sys.executable))

SPEC = ModelSpec(
    key="local/fake-tts",
    kind="tts",
    where="local",
    display="Fake TTS",
    runtime="python",
    worker="worker_fake",
    env="fake",
    worker_args={"model_dir": "{models}/Fake-1", "env": "{envs}/fake"},
)


@pytest.fixture
async def made(tmp_path: Path) -> AsyncIterator[list[LocalPythonAdapter]]:
    adapters: list[LocalPythonAdapter] = []
    yield adapters
    for adapter in adapters:
        await adapter.stop()


def _adapter(
    made: list[LocalPythonAdapter], tmp_path: Path, lease: VramLease, spec: ModelSpec = SPEC
) -> LocalPythonAdapter:
    async def paths() -> RuntimePaths:
        return RuntimePaths(envs=tmp_path / "envs", models=tmp_path / "models")

    adapter = LocalPythonAdapter(
        spec, paths=paths, lease=lease, python=lambda _env: PYTHON, workers_dir=FAKE_WORKERS
    )
    made.append(adapter)
    return adapter


def _say(text: str, **params: object) -> ModelRequest:
    return ModelRequest(kind="tts", prompt=text, params=params)


async def test_a_worker_answers_and_stays_loaded(
    made: list[LocalPythonAdapter], tmp_path: Path
) -> None:
    adapter = _adapter(made, tmp_path, VramLease())
    first = await adapter.run(_say("三年了。", voice="x"), CallContext())
    second = await adapter.run(_say("他凭什么。"), CallContext())
    assert first.json["pid"] == second.json["pid"]  # the model stays resident
    assert first.json["args"] == {
        "model_dir": f"{tmp_path / 'models'}/Fake-1",
        "env": f"{tmp_path / 'envs'}/fake",
    }
    assert (first.json["text"], first.json["params"]) == ("三年了。", {"voice": "x"})
    (f,) = first.files
    assert f.mime == "audio/wav" and f.data is not None and f.data[:4] == b"RIFF"
    assert f.duration_s == 0.5
    assert first.usage.chars == 4 and first.usage.output_seconds == 0.5
    assert (await adapter.health()).ok


async def test_a_timeout_kills_the_worker_and_the_next_call_starts_fresh(
    made: list[LocalPythonAdapter], tmp_path: Path
) -> None:
    adapter = _adapter(made, tmp_path, VramLease())
    before = (await adapter.run(_say("一"), CallContext())).json["pid"]
    with pytest.raises(TimeoutError):
        async with asyncio.timeout(1.0):
            await adapter.run(_say("hang"), CallContext())
    after = await adapter.run(_say("二"), CallContext())
    assert after.json["pid"] != before and after.json["text"] == "二"


async def test_worker_errors_and_crashes(made: list[LocalPythonAdapter], tmp_path: Path) -> None:
    adapter = _adapter(made, tmp_path, VramLease())
    with pytest.raises(ModelError) as exc:
        await adapter.run(_say("fail"), CallContext())
    assert exc.value.code == "bad_line"
    with pytest.raises(ModelError) as exc:
        await adapter.run(_say("crash"), CallContext())
    assert exc.value.code == "worker_crashed" and "out of memory" in str(exc.value)
    assert (await adapter.run(_say("还在"), CallContext())).json["text"] == "还在"

    broken = _adapter(made, tmp_path, VramLease(), replace(SPEC, worker_args={"init_fail": True}))
    with pytest.raises(ModelError) as exc:
        await broken.run(_say("一"), CallContext())
    assert exc.value.code == "model_load_failed"


async def test_the_vram_lease_makes_the_previous_model_let_go(
    made: list[LocalPythonAdapter], tmp_path: Path
) -> None:
    lease = VramLease()
    a = _adapter(made, tmp_path, lease)
    b = _adapter(made, tmp_path, lease, replace(SPEC, key="local/fake-b"))
    ocr = _adapter(
        made, tmp_path, lease, replace(SPEC, key="local/fake-ocr", kind="ocr", gpu=False)
    )
    await a.run(_say("一"), CallContext())
    proc = a._worker.proc if a._worker else None
    assert lease.resident == "python:local/fake-tts" and proc is not None
    await b.run(_say("二"), CallContext())
    assert a._worker is None and proc.returncode is not None  # A let go before B loaded
    assert lease.resident == "python:local/fake-b"
    read = await ocr.run(ModelRequest(kind="ocr", params={"path": "x.png"}), CallContext())
    assert read.text == "便利贴" and read.usage.images == 1
    assert lease.resident == "python:local/fake-b"  # the CPU model does not take the GPU


async def test_stop_closes_stdin_and_the_worker_exits(
    made: list[LocalPythonAdapter], tmp_path: Path
) -> None:
    adapter = _adapter(made, tmp_path, VramLease())
    await adapter.run(_say("一"), CallContext())
    proc = adapter._worker.proc if adapter._worker else None
    assert proc is not None
    await adapter.stop()
    assert proc.returncode == 0


async def test_not_installed(tmp_path: Path) -> None:
    async def paths() -> RuntimePaths:
        return RuntimePaths(envs=tmp_path / "envs", models=None)

    adapter = LocalPythonAdapter(SPEC, paths=paths, lease=VramLease(), workers_dir=FAKE_WORKERS)
    assert (await adapter.health()).detail == "not_installed"
    with pytest.raises(ModelError) as exc:
        await adapter.run(_say("一"), CallContext())
    assert exc.value.code == "not_installed"
