"""Real install steps (SPEC 12.1): ``uv_venv``, ``uv_pip``, ``git_clone``, ``download``,
``pkg``, ``script``, ``copy``.

Every step is idempotent: a venv that exists, a checkout already at its ref, a file whose
sha256 matches are left alone, so a retry or a resumed install only does what is missing.
Python packages only go into ``{envs}/<name>`` or the interpreter of the ComfyUI we found,
never into the system Python (SPEC 12.2-5). Commands run without a shell, through an
``Exec`` that tests replace; their output is logged line by line (``setup:log.output``).

A manifest value still marked ``TODO`` stops the item with ``manifest_todo``.
"""

from __future__ import annotations

import asyncio
import hashlib
import shlex
import shutil
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Protocol

import httpx

from drama_series_agent.core.paths import REPO_ROOT
from drama_series_agent.setup.comfy import model_target
from drama_series_agent.setup.installer import (
    Installed,
    InstallEnv,
    InstallError,
    LogFn,
    ProgressFn,
)
from drama_series_agent.setup.manifest import PKG_MANAGER, TODO, Item, Step
from drama_series_agent.setup.pathutil import join

LineFn = Callable[[str], Awaitable[None]]

# winget's APPINSTALLER_CLI_ERROR_PACKAGE_ALREADY_INSTALLED (0x8A15002B as a signed int).
WINGET_ALREADY_INSTALLED = -1978335189
CHUNK = 1 << 20
MAX_LINE = 500


class Exec(Protocol):
    async def __call__(self, argv: list[str], *, cwd: str | None, on_line: LineFn) -> int: ...


async def run_process(argv: list[str], *, cwd: str | None, on_line: LineFn) -> int:
    """Run ``argv`` (no shell), streaming its output; returns the exit code."""
    if sys.platform == "win32":
        import subprocess

        flags = subprocess.CREATE_NO_WINDOW
    else:
        flags = 0
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=cwd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            creationflags=flags,
        )
    except FileNotFoundError:
        raise InstallError("command_not_found", command=argv[0]) from None
    assert proc.stdout is not None
    try:
        async for raw in proc.stdout:
            line = raw.decode(errors="replace").rstrip()
            if line:
                await on_line(line[:MAX_LINE])
        return await proc.wait()
    except asyncio.CancelledError:
        proc.kill()
        await proc.wait()
        raise


async def _exists(path: str | Path) -> bool:
    return await asyncio.to_thread(Path(path).exists)


def _has_files(path: Path) -> bool:
    return path.is_dir() and any(path.iterdir())


def _python_in(venv: str, os: str) -> str:
    if os == "windows":
        return join(venv, "Scripts", "python.exe")
    return join(venv, "bin", "python")


class RealRunner:
    """Runs an item's install steps on this machine."""

    def __init__(
        self,
        *,
        mirrors: dict[str, dict[str, Any]],
        exec_: Exec = run_process,
        transport: httpx.AsyncBaseTransport | None = None,
        already: Callable[[Item, InstallEnv], Awaitable[bool]] | None = None,
        which: Callable[[str], str | None] = shutil.which,
    ) -> None:
        self.mirrors = mirrors
        self._exec = exec_
        self._transport = transport
        self._already = already
        self._which = which

    async def install(
        self, item: Item, env: InstallEnv, log: LogFn, progress: ProgressFn
    ) -> Installed:
        # Installed by hand since the scan: nothing to do.
        if self._already is not None and await self._already(item, env):
            await log("info", "already", {"item": item.id})
            return Installed()
        if not item.install:
            raise InstallError("not_installable")
        paths: list[str] = []
        names: dict[str, str] = {}
        span = 100 / len(item.install)
        for i, step in enumerate(item.install):

            async def sub(pct: float, base: float = i * span) -> None:
                await progress(base + pct * span / 100)

            run = _StepRun(self, step, env, names, log, sub)
            paths += await run.go()
            await progress((i + 1) * span)
        return Installed(paths=paths)

    # ------------------------------------------------------------------ mirrors

    def base(self, env: InstallEnv, site: str) -> str:
        """Where to fetch ``site`` (hf / pypi / github) from, by the user's mirror choice."""
        official = str(self.mirrors.get("official", {}).get(site, ""))
        cn = str(self.mirrors.get("cn", {}).get(site) or "")
        if not cn or TODO in cn or env.mirror == "official":
            return official
        if env.mirror == "cn":
            return cn
        # Automatic: the scan timed the official sites; a slow or unreachable one goes to cn.
        latency = env.facts.get("hf", {}).get("latency_ms", {}).get(site)
        return cn if latency is None or latency > 1500 else official


class _StepRun:
    """One step of one item: template values filled, then the step type's handler."""

    def __init__(
        self,
        runner: RealRunner,
        step: Step,
        env: InstallEnv,
        names: dict[str, str],
        log: LogFn,
        progress: ProgressFn,
    ) -> None:
        self.r = runner
        self.step = step
        self.env = env
        self.names = names  # {dest} of an earlier step, for requirements: "{dest}/..."
        self.log = log
        self.progress = progress
        self.extra: dict[str, Any] = dict(step.model_extra or {})

    async def go(self) -> list[str]:
        handler = getattr(self, f"_{self.step.type}")
        result: list[str] = await handler()
        return result

    # ------------------------------------------------------------------ helpers

    def value(self, key: str, *, required: bool = True) -> Any:
        v = self.extra.get(key)
        if v is None:
            if required:
                raise InstallError("manifest_todo", field=f"{self.step.type}.{key}")
            return None
        if isinstance(v, str) and TODO in v:
            raise InstallError("manifest_todo", field=f"{self.step.type}.{key}")
        if isinstance(v, list) and any(isinstance(x, str) and TODO in x for x in v):
            raise InstallError("manifest_todo", field=f"{self.step.type}.{key}")
        return v

    def expand(self, template: str) -> str:
        values = {
            "comfy": self.env.comfy,
            "envs": self.env.envs,
            "models": self.env.models,
            **self.names,
        }
        try:
            return template.format_map(values)
        except KeyError as exc:
            raise InstallError("manifest_todo", field=str(exc.args[0])) from None

    async def run(
        self, argv: list[str], *, cwd: str | None = None, ok: tuple[int, ...] = (0,)
    ) -> None:
        exe = self.r._which(argv[0])
        if exe is None:
            raise InstallError("command_not_found", command=argv[0])

        async def line(text: str) -> None:
            await self.log("info", "output", {"text": text})

        code = await self.r._exec([exe, *argv[1:]], cwd=cwd, on_line=line)
        if code not in ok:
            raise InstallError("step_failed", step=self.step.type, exit=code)

    def python_for(self, env_name: str) -> tuple[str, str | None]:
        """(interpreter, venv to create first). ``comfy`` is the found ComfyUI's own Python."""
        if env_name == "comfy" and self.env.comfy_python:
            return self.env.comfy_python, None
        venv = join(self.env.envs, env_name)
        return _python_in(venv, self.env.os), venv

    async def ensure_venv(self, venv: str) -> None:
        if await _exists(_python_in(venv, self.env.os)):
            return
        await self.run(["uv", "venv", "--python", "3.12", venv])

    # ------------------------------------------------------------------ steps

    async def _uv_venv(self) -> list[str]:
        venv = join(self.env.envs, str(self.value("env")))
        python = self.extra.get("python") or "3.12"
        if not await _exists(_python_in(venv, self.env.os)):
            await self.run(["uv", "venv", "--python", str(python), venv])
        return [venv]

    async def _uv_pip(self) -> list[str]:
        python, venv = self.python_for(str(self.value("env")))
        if venv is not None:
            await self.ensure_venv(venv)
        argv = ["uv", "pip", "install", "--python", python]
        requirements = self.value("requirements", required=False)
        packages = self.value("packages", required=False) or []
        if not requirements and not packages:
            raise InstallError("manifest_todo", field="uv_pip.packages")
        if requirements:
            argv += ["-r", self.expand(str(requirements))]
        argv += [str(p) for p in packages]
        index = self.value("index_url", required=False)
        if index:
            argv += ["--index-url", str(index)]
        elif self.r.base(self.env, "pypi") != self.r.mirrors.get("official", {}).get("pypi"):
            argv += ["--index-url", self.r.base(self.env, "pypi")]
        await self.run(argv)
        return []

    async def _git_clone(self) -> list[str]:
        url = str(self.value("url"))
        ref = str(self.value("ref"))
        dest = self.expand(str(self.value("dest")))
        self.names["dest"] = dest
        official = str(self.r.mirrors.get("official", {}).get("github", ""))
        base = self.r.base(self.env, "github")
        if official and url.startswith(official) and base != official:
            url = base.rstrip("/") + url[len(official) :]
        d = Path(dest)
        if await _exists(d / ".git"):
            head: list[str] = []

            async def keep(text: str) -> None:
                head.append(text)

            exe = self.r._which("git") or "git"
            await self.r._exec([exe, "-C", dest, "rev-parse", "HEAD"], cwd=None, on_line=keep)
            if head and head[-1].strip() == ref:
                return [dest]
            await self.run(["git", "-C", dest, "fetch", "--depth", "1", "origin", ref])
            await self.run(["git", "-C", dest, "checkout", "--force", "FETCH_HEAD"])
            return [dest]
        if await asyncio.to_thread(_has_files, d):
            raise InstallError("dest_not_empty", path=dest)
        await self.run(["git", "clone", "--filter=blob:none", url, dest])
        await self.run(["git", "-C", dest, "checkout", "--force", ref])
        return [dest]

    async def _download(self) -> list[str]:
        files = self.step.download_files()
        if not files:
            raise InstallError("manifest_todo", field="download.files")
        if any(TODO in f.path or TODO in (f.sha256 or "") for f in files):
            raise InstallError("manifest_todo", field="download.files")
        # Files for a ComfyUI model folder go where ComfyUI puts new ones (Desktop's shared
        # models folder); the rest under `dest`, which is needed only then.
        dest = (
            self.expand(str(self.value("dest"))) if any(f.folder is None for f in files) else None
        )
        if dest is not None:
            self.names["dest"] = dest
        if url := self.value("url", required=False):
            urls = [str(url)]
        else:
            repo = str(self.value("hf_repo"))
            revision = str(self.value("revision", required=False) or "main")
            hf = self.r.base(self.env, "hf").rstrip("/")
            urls = [f"{hf}/{repo}/resolve/{revision}/{f.path}" for f in files]
        out: list[str] = []
        for i, (url_, f) in enumerate(zip(urls, files, strict=True)):
            if f.folder is not None:
                target = Path(model_target(f.folder, self.env.model_dirs, self.env.comfy), f.name)
            else:
                assert dest is not None
                target = Path(dest) / f.path

            async def sub(pct: float, i: int = i) -> None:
                await self.progress((i + pct / 100) / len(files) * 100)

            await self.log("info", "download", {"file": f.name, "path": str(target)})
            await _fetch(url_, target, f.sha256, self.r._transport, sub)
            out.append(str(target))
        return out

    async def _pkg(self) -> list[str]:
        manager = PKG_MANAGER[self.env.os]
        name = self.extra.get(manager)
        if not name:
            raise InstallError("no_package", manager=manager)
        if TODO in str(name):
            raise InstallError("manifest_todo", field=f"pkg.{manager}")
        if manager == "winget":
            argv = [
                "winget", "install", "--id", str(name), "--exact", "--silent",
                "--accept-source-agreements", "--accept-package-agreements",
            ]  # fmt: skip
            await self.run(argv, ok=(0, WINGET_ALREADY_INSTALLED))
        elif manager == "brew":
            await self.run(["brew", "install", str(name)])
        else:
            # -n: never prompt; the user approved elevation before the install started.
            await self.run(["sudo", "-n", "apt-get", "install", "-y", str(name)])
        return []

    async def _script(self) -> list[str]:
        argv = shlex.split(str(self.value("run")), posix=self.env.os != "windows")
        if not argv:
            raise InstallError("manifest_todo", field="script.run")
        await self.run([self.expand(a) for a in argv])
        return []

    async def _copy(self) -> list[str]:
        src = REPO_ROOT / str(self.value("from"))
        dest = self.expand(str(self.value("dest")))
        self.names["dest"] = dest
        if not await _exists(src):
            raise InstallError("source_missing", path=str(self.value("from")))
        await asyncio.to_thread(shutil.copytree, src, dest, dirs_exist_ok=True)
        return [dest]


async def _sha256(path: Path) -> str:
    def digest() -> str:
        h = hashlib.sha256()
        with path.open("rb") as fh:
            while chunk := fh.read(CHUNK):
                h.update(chunk)
        return h.hexdigest()

    return await asyncio.to_thread(digest)


async def _fetch(
    url: str,
    target: Path,
    sha256: str | None,
    transport: httpx.AsyncBaseTransport | None,
    progress: ProgressFn,
) -> None:
    """Download ``url`` to ``target``: resumes a ``.part`` file, checks sha256, then renames."""
    if await _exists(target) and (sha256 is None or await _sha256(target) == sha256.lower()):
        return
    part = target.with_name(target.name + ".part")
    await asyncio.to_thread(target.parent.mkdir, parents=True, exist_ok=True)
    have = (await asyncio.to_thread(part.stat)).st_size if await _exists(part) else 0
    headers = {"Range": f"bytes={have}-"} if have else {}
    try:
        async with (
            httpx.AsyncClient(
                transport=transport, follow_redirects=True, timeout=httpx.Timeout(30, read=120)
            ) as client,
            client.stream("GET", url, headers=headers) as resp,
        ):
            if resp.status_code == 416:  # the .part is already complete
                pass
            elif resp.status_code not in (200, 206):
                raise InstallError("download_failed", status=resp.status_code, file=target.name)
            else:
                if resp.status_code == 200:
                    have = 0  # the server ignored the range: start over
                total = int(resp.headers.get("content-length", 0)) + have
                mode = "ab" if have else "wb"
                fh = await asyncio.to_thread(part.open, mode)
                try:
                    async for chunk in resp.aiter_bytes(CHUNK):
                        await asyncio.to_thread(fh.write, chunk)
                        have += len(chunk)
                        if total:
                            await progress(min(99.0, have / total * 100))
                finally:
                    await asyncio.to_thread(fh.close)
    except httpx.HTTPError as exc:
        raise InstallError("download_failed", status=type(exc).__name__, file=target.name) from None
    if sha256 is not None and await _sha256(part) != sha256.lower():
        await asyncio.to_thread(part.unlink)
        raise InstallError("sha256_mismatch", file=target.name)
    await asyncio.to_thread(part.replace, target)
