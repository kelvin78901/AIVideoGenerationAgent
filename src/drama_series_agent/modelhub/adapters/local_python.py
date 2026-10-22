"""Local models in a Python environment of their own (plan M3 「本地 Python 运行时」): Qwen3-TTS
auditions, IndexTTS dubbing, RapidOCR.

- **One worker per model**: ``<envs>/<env>/(Scripts|bin)/python -u workers/<worker>.py``. It
  loads the model once and keeps it (the model stays resident) until the VRAM lease asks it to
  go or the app stops; stdin closing makes it exit.
- **Protocol** (``workers/worker_protocol.py``): JSON lines. ``init`` with the model's ``args``
  first, then one request per call with an id; the reply carries the same id. Files go to a
  temporary folder and are read back at once.
- **Timeouts and cancels kill the worker**: the router's local timeout cancels the call, the
  worker is killed, and the next call starts a fresh one, so a late reply to an old request can
  never be taken for a new one.
- **Environment**: ``PYTHONUTF8=1``; ``HF_HUB_OFFLINE=1`` with ``HF_HOME`` under the models folder
  (the installer downloads everything first); library output goes to stderr, whose last lines
  explain a crash.
- **GPU models hold the VRAM lease** for the call (``modelhub/vram.py``); ``gpu: false`` models
  (RapidOCR) do not.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
import uuid
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger

from drama_series_agent.modelhub.adapters.base import (
    CallContext,
    Estimate,
    Health,
    ModelError,
    ModelRequest,
    ModelResult,
    ModelSpec,
    OutputFile,
    Usage,
)
from drama_series_agent.modelhub.vram import VramLease, shared_lease

WORKERS_DIR = Path(__file__).resolve().parents[2] / "workers"
STOP_GRACE_S = 5.0
STDERR_TAIL = 40


@dataclass(frozen=True)
class RuntimePaths:
    envs: Path
    models: Path | None  # the install folder chosen on the Setup page (None before setup)


PathsGetter = Callable[[], Awaitable[RuntimePaths]]


def venv_python(env_dir: Path) -> Path:
    return env_dir / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def _expand(value: Any, paths: RuntimePaths) -> Any:
    if isinstance(value, str):
        out = value.replace("{envs}", str(paths.envs))
        if paths.models is not None:
            out = out.replace("{models}", str(paths.models))
        return out
    if isinstance(value, dict):
        return {k: _expand(v, paths) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand(v, paths) for v in value]
    return value


def _read_files(reply: dict[str, Any]) -> list[OutputFile]:
    """The reply's files, read into memory (their folder goes right after)."""
    return [
        OutputFile(
            role=str(f.get("role") or "audio"),
            mime=str(f.get("mime") or "application/octet-stream"),
            data=Path(str(f["path"])).read_bytes(),
            duration_s=f.get("duration_s"),
        )
        for f in reply.get("files") or []
    ]


class _Worker:
    """One running worker process."""

    def __init__(self, proc: asyncio.subprocess.Process, name: str) -> None:
        self.proc = proc
        self.name = name
        self.tail: deque[str] = deque(maxlen=STDERR_TAIL)
        self._drain = asyncio.create_task(self._read_stderr())

    @property
    def alive(self) -> bool:
        return self.proc.returncode is None

    async def ask(self, msg: dict[str, Any]) -> dict[str, Any]:
        assert self.proc.stdin is not None and self.proc.stdout is not None
        try:
            self.proc.stdin.write((json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8"))
            await self.proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            raise self._crashed() from None
        while True:
            raw = await self.proc.stdout.readline()
            if not raw:
                await self.proc.wait()
                raise self._crashed()
            try:
                reply = json.loads(raw.decode("utf-8"))
            except ValueError:
                logger.debug("worker {}: not a reply: {!r}", self.name, raw[:200])
                continue
            if isinstance(reply, dict) and reply.get("id") == msg["id"]:
                return reply

    async def stop(self) -> None:
        if self.alive:
            if self.proc.stdin is not None:
                self.proc.stdin.close()
            try:
                await asyncio.wait_for(self.proc.wait(), STOP_GRACE_S)
            except TimeoutError:
                self.kill()
                await self.proc.wait()
        self._drain.cancel()

    def kill(self) -> None:
        if self.alive:
            self.proc.kill()

    def _crashed(self) -> ModelError:
        detail = " | ".join(list(self.tail)[-5:])
        return ModelError(
            "worker_crashed", f"{self.name} exited ({self.proc.returncode}): {detail}"
        )

    async def _read_stderr(self) -> None:
        assert self.proc.stderr is not None
        async for raw in self.proc.stderr:
            line = raw.decode("utf-8", errors="replace").rstrip()
            if line:
                self.tail.append(line[:300])
                logger.debug("worker {}: {}", self.name, line[:300])


class LocalPythonAdapter:
    def __init__(
        self,
        spec: ModelSpec,
        *,
        paths: PathsGetter,
        lease: VramLease | None = None,
        python: Callable[[Path], Path] = venv_python,
        workers_dir: Path = WORKERS_DIR,
    ) -> None:
        self.spec = spec
        self._paths = paths
        self._lease = lease or shared_lease()
        self._python = python
        self._workers_dir = workers_dir
        self._worker: _Worker | None = None
        self._start_lock = asyncio.Lock()
        if spec.gpu:
            self._lease.register(self._owner, self.stop)

    @property
    def key(self) -> str:
        return self.spec.key

    @property
    def _owner(self) -> str:
        return f"python:{self.spec.key}"

    # ------------------------------------------------------------------ protocol

    def estimate(self, req: ModelRequest) -> Estimate:
        return Estimate(cost_usd=0.0, seconds=5.0 + len(req.text()) * 0.2)

    async def health(self) -> Health:
        """Installed: the environment's Python and the worker script exist (nothing started)."""
        try:
            python, script, _ = await self._command()
        except ModelError as exc:
            return Health(ok=False, detail=exc.code)
        if not python.is_file():
            return Health(ok=False, detail="not_installed")
        if not script.is_file():
            return Health(ok=False, detail="worker_missing")
        return Health(ok=True, models=[self.spec.key])

    async def run(self, req: ModelRequest, ctx: CallContext) -> ModelResult:
        if not self.spec.gpu:
            return await self._call(req)
        async with self._lease.hold(self._owner):
            return await self._call(req)

    async def stop(self) -> None:
        """Let the model go (the VRAM lease asks, or the app stops)."""
        worker, self._worker = self._worker, None
        if worker is not None:
            await worker.stop()
        self._lease.forget(self._owner)

    # ------------------------------------------------------------------ internals

    async def _command(self) -> tuple[Path, Path, RuntimePaths]:
        if not self.spec.worker or not self.spec.env:
            raise ModelError("worker_not_configured", f"{self.key}: worker / env in providers.yaml")
        paths = await self._paths()
        python = self._python(paths.envs / self.spec.env)
        return python, self._workers_dir / f"{self.spec.worker}.py", paths

    async def _ensure(self) -> _Worker:
        async with self._start_lock:
            if self._worker is not None and self._worker.alive:
                return self._worker
            python, script, paths = await self._command()
            if not python.is_file():
                raise ModelError("not_installed", f"{self.key}: no environment at {python.parent}")
            env = {
                **os.environ,
                "PYTHONUTF8": "1",
                "PYTHONUNBUFFERED": "1",
                "HF_HUB_OFFLINE": "1",
                # The worker imports worker_protocol from the app's workers folder.
                "PYTHONPATH": str(WORKERS_DIR),
            }
            if paths.models is not None:
                env["HF_HOME"] = str(paths.models / "hf")
            flags = 0
            if sys.platform == "win32":
                import subprocess

                flags = subprocess.CREATE_NO_WINDOW
            proc = await asyncio.create_subprocess_exec(
                str(python),
                "-u",
                str(script),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                creationflags=flags,
            )
            worker = _Worker(proc, self.spec.worker or self.key)
            self._worker = worker
            try:
                init = {"id": "init", "op": "init", "args": _expand(self.spec.worker_args, paths)}
                await self._checked(worker, init)
            except BaseException:
                await self._kill()
                raise
            return worker

    async def _call(self, req: ModelRequest) -> ModelResult:
        worker = await self._ensure()
        out = Path(tempfile.mkdtemp(prefix="drama-worker-"))
        try:
            msg = {
                "id": uuid.uuid4().hex,
                "op": "run",
                "kind": req.kind,
                "text": req.prompt or "",
                "params": req.params,
                "out": str(out),
            }
            try:
                reply = await self._checked(worker, msg)
            except (asyncio.CancelledError, TimeoutError):
                await asyncio.shield(self._kill())  # a late reply must never answer a new call
                raise
            files = await asyncio.to_thread(_read_files, reply)
        finally:
            await asyncio.to_thread(shutil.rmtree, out, ignore_errors=True)
        seconds = sum(float(f.duration_s or 0) for f in files) or None
        usage = Usage(
            chars=len(req.prompt or "") if req.kind != "ocr" else None,
            images=1 if req.kind == "ocr" else None,
            output_seconds=seconds,
        )
        return ModelResult(text=reply.get("text"), json=reply.get("json"), files=files, usage=usage)

    async def _checked(self, worker: _Worker, msg: dict[str, Any]) -> dict[str, Any]:
        reply = await worker.ask(msg)
        if not reply.get("ok"):
            raise ModelError(
                str(reply.get("code") or "worker_error"), str(reply.get("message") or "")
            )
        return reply

    async def _kill(self) -> None:
        worker, self._worker = self._worker, None
        if worker is not None:
            worker.kill()
            await worker.stop()
        self._lease.forget(self._owner)
