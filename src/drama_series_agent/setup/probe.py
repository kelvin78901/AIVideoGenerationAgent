"""What the detectors may ask of the machine (SPEC 12.2-1: the scan is read-only).

``RealProbe`` looks at this machine; ``FakeProbe`` answers from a fixture file
(``tests/fixtures/setup/{pc,mac}.yaml``, the prototype's two sample machines). Mock mode and
the tests use the fake one, so nothing real is scanned there.

Paths are plain strings: detectors join them with ``/``, which Windows accepts too.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import plistlib
import posixpath
import re
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol
from urllib.parse import urlsplit

import httpx
import yaml
from loguru import logger

from drama_series_agent.core import secrets
from drama_series_agent.core.paths import REPO_ROOT
from drama_series_agent.setup.manifest import OS

FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "setup"
GB = 1024**3


@dataclass(frozen=True)
class HostInfo:
    os: OS
    os_name: str  # "Windows 11", "macOS", "Ubuntu 24.04.1 LTS"
    bits: int
    arch: str
    ram_gb: float
    home: str

    @property
    def apple_silicon(self) -> bool:
        return self.os == "macos" and self.arch in ("arm64", "aarch64")


@dataclass(frozen=True)
class GpuInfo:
    name: str  # as the vendor reports it, e.g. "NVIDIA GeForce RTX 5090"
    vram_gb: float  # unified memory on Apple silicon
    backend: Literal["cuda", "mps"]
    cuda_driver: str | None = None  # highest CUDA version the driver supports, e.g. "13.0"


@dataclass(frozen=True)
class DiskInfo:
    drive: str | None  # "D:" on Windows
    free_gb: float


@dataclass(frozen=True)
class CommandResult:
    code: int
    out: str


@dataclass(frozen=True)
class HttpResult:
    status: int
    ms: float
    body: Any  # parsed JSON, else text


@dataclass(frozen=True)
class PyModule:
    version: str | None
    cuda: str | None  # ``<module>.version.cuda`` (PyTorch's CUDA build), else None


@dataclass(frozen=True)
class AppInfo:
    version: str
    edition: Literal["free", "studio"]


class Probe(Protocol):
    simulated: bool

    async def host(self) -> HostInfo: ...
    async def gpu(self) -> GpuInfo | None: ...
    async def disk(self, path: str) -> DiskInfo | None: ...
    async def default_dir(self) -> str: ...
    async def run(self, cmd: str) -> CommandResult | None: ...
    async def http_get(self, url: str, timeout_s: float = 3.0) -> HttpResult | None: ...
    async def exists(self, path: str) -> bool: ...
    async def read_text(self, path: str) -> str | None: ...
    async def py_module(self, python: str, module: str) -> PyModule | None: ...
    async def has_secret(self, name: str) -> bool: ...
    async def resolve_app(self) -> AppInfo | None: ...


# --------------------------------------------------------------------------- real

_PY_MODULE_SCRIPT = """
import importlib, json, sys
try:
    m = importlib.import_module(sys.argv[1])
except Exception:
    print("null"); sys.exit(0)
v = getattr(m, "__version__", None)
cuda = getattr(getattr(m, "version", None), "cuda", None)
print(json.dumps({"version": str(v) if v else None, "cuda": cuda}))
"""

_LOOPBACK = {"127.0.0.1", "localhost", "::1"}

# No console window flashing up for each command on Windows.
if sys.platform == "win32":
    NO_WINDOW = subprocess.CREATE_NO_WINDOW
else:
    NO_WINDOW = 0


def _host_os() -> OS:
    if sys.platform == "win32":
        return "windows"
    return "macos" if sys.platform == "darwin" else "linux"


def _total_ram_bytes() -> int:
    if sys.platform == "win32":
        import ctypes

        class MemoryStatusEx(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        stat = MemoryStatusEx()
        stat.dwLength = ctypes.sizeof(MemoryStatusEx)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
        return int(stat.ullTotalPhys)
    return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")


def _fixed_drives() -> list[str]:
    """Local fixed drives on Windows, e.g. ``["C:", "D:"]``; empty elsewhere."""
    if sys.platform != "win32":
        return []
    import ctypes

    drives = []
    for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
        root = f"{letter}:\\"
        if ctypes.windll.kernel32.GetDriveTypeW(root) == 3:  # DRIVE_FIXED
            drives.append(f"{letter}:")
    return drives


class RealProbe:
    """Reads this machine. Never writes anything (SPEC 12.2-1)."""

    simulated = False

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def host(self) -> HostInfo:
        import platform

        os_ = _host_os()
        if sys.platform == "win32":
            build = sys.getwindowsversion().build
            name = "Windows 11" if build >= 22000 else f"Windows {platform.release()}"
        elif os_ == "macos":
            name = "macOS"
        else:
            try:
                name = platform.freedesktop_os_release().get("PRETTY_NAME", "Linux")
            except OSError:
                name = "Linux"
        return HostInfo(
            os=os_,
            os_name=name,
            bits=64 if sys.maxsize > 2**32 else 32,
            arch=platform.machine().lower(),
            ram_gb=_total_ram_bytes() / GB,
            home=str(Path.home()),
        )

    async def gpu(self) -> GpuInfo | None:
        info = await asyncio.to_thread(self._nvml)
        if info is None:
            info = await self._nvidia_smi()
        if info is None and (await self.host()).apple_silicon:
            out = await self.run("sysctl -n machdep.cpu.brand_string")
            name = out.out.strip() if out and out.code == 0 else "Apple silicon"
            return GpuInfo(name=name, vram_gb=(await self.host()).ram_gb, backend="mps")
        return info

    @staticmethod
    def _nvml() -> GpuInfo | None:
        try:
            import pynvml

            pynvml.nvmlInit()
        except Exception:
            return None
        try:
            best: tuple[str, int] | None = None
            for i in range(pynvml.nvmlDeviceGetCount()):
                handle = pynvml.nvmlDeviceGetHandleByIndex(i)
                name = pynvml.nvmlDeviceGetName(handle)
                name = name.decode() if isinstance(name, bytes) else str(name)
                total = int(pynvml.nvmlDeviceGetMemoryInfo(handle).total)
                if best is None or total > best[1]:
                    best = (name, total)
            if best is None:
                return None
            drv = int(pynvml.nvmlSystemGetCudaDriverVersion())  # e.g. 13000
            return GpuInfo(
                name=best[0],
                vram_gb=best[1] / GB,
                backend="cuda",
                cuda_driver=f"{drv // 1000}.{drv % 1000 // 10}",
            )
        except Exception:
            logger.opt(exception=True).debug("NVML query failed")
            return None
        finally:
            with contextlib.suppress(Exception):
                pynvml.nvmlShutdown()

    async def _nvidia_smi(self) -> GpuInfo | None:
        query = await self.run(
            "nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits"
        )
        if query is None or query.code != 0:
            return None
        rows = [line.rsplit(",", 1) for line in query.out.strip().splitlines() if "," in line]
        if not rows:
            return None
        name, mib = max(rows, key=lambda r: float(r[1]))
        header = await self.run("nvidia-smi")
        cuda = re.search(r"CUDA Version:\s*(\d+\.\d+)", header.out) if header else None
        return GpuInfo(
            name=name.strip(),
            vram_gb=float(mib) / 1024,
            backend="cuda",
            cuda_driver=cuda.group(1) if cuda else None,
        )

    async def disk(self, path: str) -> DiskInfo | None:
        return await asyncio.to_thread(_disk_usage, path)

    async def default_dir(self) -> str:
        """The fixed drive with the most free space on Windows (if not C:), else the home folder."""
        best: tuple[float, str] | None = None
        for drive in _fixed_drives():
            info = await self.disk(drive + "\\")
            if info and (best is None or info.free_gb > best[0]):
                best = (info.free_gb, drive)
        if best and best[1] != "C:":
            return f"{best[1]}\\DramaStudio"
        return str(Path.home() / "DramaStudio")

    async def run(self, cmd: str, timeout_s: float = 20.0) -> CommandResult | None:
        argv = shlex.split(cmd, posix=True)
        exe = shutil.which(argv[0]) if argv else None
        if exe is None:
            return None
        return await self._exec([exe, *argv[1:]], timeout_s)

    async def _exec(self, argv: list[str], timeout_s: float) -> CommandResult | None:
        flags = NO_WINDOW
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                creationflags=flags,
            )
        except OSError:
            return None
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), timeout_s)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            return None
        return CommandResult(code=proc.returncode or 0, out=out.decode(errors="replace"))

    async def http_get(self, url: str, timeout_s: float = 3.0) -> HttpResult | None:
        # A system proxy must not swallow requests to local services (ComfyUI, Ollama, Eagle).
        local = urlsplit(url).hostname in _LOOPBACK
        try:
            async with httpx.AsyncClient(
                timeout=timeout_s,
                follow_redirects=True,
                trust_env=not local,
                transport=self._transport,
            ) as client:
                start = time.perf_counter()
                resp = await client.get(url)
                ms = (time.perf_counter() - start) * 1000
        except httpx.HTTPError:
            return None
        body: Any
        try:
            body = resp.json()
        except ValueError:
            body = resp.text[:4096]
        return HttpResult(status=resp.status_code, ms=ms, body=body)

    async def exists(self, path: str) -> bool:
        return await asyncio.to_thread(_exists, path)

    async def read_text(self, path: str) -> str | None:
        return await asyncio.to_thread(_read_head, path)

    async def py_module(self, python: str, module: str) -> PyModule | None:
        # Importing torch takes a while on a cold start.
        res = await self._exec([python, "-c", _PY_MODULE_SCRIPT, module], timeout_s=90)
        if res is None or res.code != 0 or not res.out.strip():
            return None
        try:
            data = json.loads(res.out.strip().splitlines()[-1])
        except ValueError:
            return None
        if not isinstance(data, dict):
            return None
        return PyModule(version=data.get("version"), cuda=data.get("cuda"))

    async def has_secret(self, name: str) -> bool:
        return await asyncio.to_thread(secrets.has_secret, name) != "none"

    async def resolve_app(self) -> AppInfo | None:
        if sys.platform == "darwin":
            return await asyncio.to_thread(_resolve_mac)
        if sys.platform == "win32":
            if not await asyncio.to_thread(_exists, _RESOLVE_WIN):
                return None
            ps = (
                f"(Get-Item '{_RESOLVE_WIN}').VersionInfo"
                " | ForEach-Object { $_.ProductVersion; $_.ProductName }"
            )
            res = await self._exec(["powershell", "-NoProfile", "-Command", ps], timeout_s=20)
            lines = res.out.strip().splitlines() if res and res.code == 0 else []
            version = lines[0].strip() if lines else "?"
            studio = len(lines) > 1 and "studio" in lines[1].lower()
            return AppInfo(version=version, edition="studio" if studio else "free")
        if await asyncio.to_thread(_exists, "/opt/resolve/bin/resolve"):
            return AppInfo(version="?", edition="free")
        return None


# Blocking file-system helpers; the async probe runs them in a worker thread.

_RESOLVE_WIN = r"C:\Program Files\Blackmagic Design\DaVinci Resolve\Resolve.exe"


def _exists(path: str) -> bool:
    return Path(path).expanduser().exists()


def _read_head(path: str) -> str | None:
    try:
        with Path(path).expanduser().open(encoding="utf-8", errors="replace") as fh:
            return fh.read(65536)
    except OSError:
        return None


def _disk_usage(path: str) -> DiskInfo | None:
    """Free space of the volume ``path`` would be on (its nearest existing parent)."""
    p = Path(path).expanduser()
    while not p.exists() and p.parent != p:
        p = p.parent
    try:
        usage = shutil.disk_usage(p)
    except OSError:
        return None
    return DiskInfo(drive=p.drive or None, free_gb=usage.free / GB)


def _resolve_mac() -> AppInfo | None:
    base = Path("/Applications/DaVinci Resolve")
    editions: tuple[tuple[str, Literal["free", "studio"]], ...] = (
        ("DaVinci Resolve Studio.app", "studio"),
        ("DaVinci Resolve.app", "free"),
    )
    for app, edition in editions:
        plist = base / app / "Contents" / "Info.plist"
        if plist.is_file():
            with plist.open("rb") as fh:
                version = str(plistlib.load(fh).get("CFBundleShortVersionString", "?"))
            return AppInfo(version=version, edition=edition)
    return None


# --------------------------------------------------------------------------- fake


def _norm(path: str) -> str:
    return posixpath.normpath(path.replace("\\", "/"))


class FakeProbe:
    """Answers from a fixture: the prototype's sample machines (Mock mode and tests)."""

    simulated = True

    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data
        self.files = {_norm(p) for p in data.get("files", [])}
        self.texts = {_norm(p): t for p, t in (data.get("texts") or {}).items()}
        self.python = {_norm(p): mods for p, mods in (data.get("python") or {}).items()}

    @classmethod
    def load(cls, machine: str, directory: Path | None = None) -> FakeProbe:
        path = (directory or FIXTURES_DIR) / f"{machine}.yaml"
        with path.open(encoding="utf-8") as fh:
            return cls(yaml.safe_load(fh))

    def add_files(self, *paths: str) -> None:
        """Tests: make things appear, as if installed."""
        self.files.update(_norm(p) for p in paths)

    async def host(self) -> HostInfo:
        return HostInfo(**self.data["host"])

    async def gpu(self) -> GpuInfo | None:
        gpu = self.data.get("gpu")
        return GpuInfo(**gpu) if gpu else None

    async def disk(self, path: str) -> DiskInfo | None:
        disks: dict[str, float] = self.data.get("disks") or {}
        drive = path[:2] if len(path) > 1 and path[1] == ":" else None
        free = disks.get(drive or "/")
        return None if free is None else DiskInfo(drive=drive, free_gb=float(free))

    async def default_dir(self) -> str:
        return str(self.data["default_dir"])

    async def run(self, cmd: str) -> CommandResult | None:
        out = (self.data.get("commands") or {}).get(cmd)
        return None if out is None else CommandResult(code=0, out=str(out))

    async def http_get(self, url: str, timeout_s: float = 3.0) -> HttpResult | None:
        res = (self.data.get("http") or {}).get(url)
        if res is None or res.get("ms", 0) > timeout_s * 1000:
            return None
        return HttpResult(status=res.get("status", 200), ms=res.get("ms", 1), body=res.get("body"))

    async def exists(self, path: str) -> bool:
        p = _norm(path)
        return p in self.files or any(f.startswith(p + "/") for f in self.files)

    async def read_text(self, path: str) -> str | None:
        return self.texts.get(_norm(path))

    async def py_module(self, python: str, module: str) -> PyModule | None:
        if not await self.exists(python):
            return None
        mod = self.python.get(_norm(python), {}).get(module)
        return PyModule(version=mod.get("version"), cuda=mod.get("cuda")) if mod else None

    async def has_secret(self, name: str) -> bool:
        return name in (self.data.get("secrets") or [])

    async def resolve_app(self) -> AppInfo | None:
        app = self.data.get("resolve")
        return AppInfo(**app) if app else None
