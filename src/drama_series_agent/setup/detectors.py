"""Detectors (SPEC 12.1): one per ``detect.type``, all read-only, all through a ``Probe``.

A detector reports what it saw (``Outcome``); ``detect_item()`` then turns that into the
item's status and fix using the manifest (``required``, ``if_missing``, ``fix``). Codes are
``setup:found.<code>`` / ``setup:fix.<code>`` in the front end's word list.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from loguru import logger

from drama_series_agent.core.config import get_config
from drama_series_agent.setup.comfy import (
    COMFY_PORTS,
    ComfyInstall,
    argv_port,
    desktop_installs,
    find_manager,
    flag_values,
    kind_of,
    main_script,
)
from drama_series_agent.setup.manifest import TODO, Item, Message, Status
from drama_series_agent.setup.pathutil import dirname, is_absolute, join, same_path
from drama_series_agent.setup.probe import GpuInfo, HostInfo, Probe

COMFY_URL = "http://127.0.0.1:8188"
SITE_NAMES = {"hf": "Hugging Face", "pypi": "PyPI", "github": "GitHub"}


def msg(code: str, **params: Any) -> Message:
    return Message(code=code, params=params)


class _Unset:
    pass


UNSET = _Unset()


@dataclass
class Outcome:
    """What a detector saw, before the manifest decides the status."""

    kind: Literal["present", "absent", "old", "warn", "skip"]
    found: Message
    version: str | None = None
    fix: Message | _Unset | None = UNSET  # a detector-specific fix; the manifest's still wins
    facts: dict[str, Any] = field(default_factory=dict)


@dataclass
class Detection:
    status: Status
    found: Message
    fix: Message | None
    installable: bool
    version: str | None = None
    facts: dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------- helpers


def parse_version(text: str | None) -> tuple[int, ...] | None:
    if not text:
        return None
    m = re.search(r"\d+(?:\.\d+)*", text)
    return tuple(int(p) for p in m.group(0).split(".")) if m else None


def meets(have: str | None, spec: str) -> bool | None:
    """``meets("13.0", ">=13.0")``; None when ``have`` is unknown or ``spec`` unparsable."""
    m = re.fullmatch(r"\s*(>=|>|==|<=|<)?\s*([\d.]+)\s*", spec)
    a, b = parse_version(have), parse_version(m.group(2) if m else None)
    if m is None or a is None or b is None:
        return None
    width = max(len(a), len(b))
    a, b = a + (0,) * (width - len(a)), b + (0,) * (width - len(b))
    op = m.group(1) or ">="
    return {">=": a >= b, ">": a > b, "==": a == b, "<=": a <= b, "<": a < b}[op]


def short_version(text: str) -> str:
    """``"13.0"`` → ``"13"``, ``"12.8"`` stays."""
    return re.sub(r"(\.0)+$", "", text)


def threshold(spec: str) -> float:
    m = re.search(r"[\d.]+", spec)
    return float(m.group(0)) if m else 0.0


def size_text(gb: float) -> str:
    return f"{gb / 1024:.1f} TB" if gb >= 1024 else f"{gb:.0f} GB"


# --------------------------------------------------------------------------- context


class ScanContext:
    """Machine facts every detector shares; ComfyUI is located once, on first use."""

    def __init__(
        self,
        probe: Probe,
        host: HostInfo,
        gpu: GpuInfo | None,
        items: list[Item],
        *,
        mirrors: dict[str, dict[str, Any]],
        variables: dict[str, str],
        comfy_setting: str | None = None,
        comfy_urls: Sequence[str] = (COMFY_URL,),
    ) -> None:
        self.probe = probe
        self.host = host
        self.gpu = gpu
        self.items = {x.id: x for x in items}
        self.mirrors = mirrors
        self.vars = dict(variables)  # envs, models; comfy once located
        self.comfy_setting = comfy_setting
        self.comfy_urls = list(dict.fromkeys(comfy_urls))  # tried in order, duplicates dropped
        self._comfy: ComfyInstall | _Unset | None = UNSET
        self._object_info: dict[str, Any] | None = None

    @classmethod
    async def create(
        cls,
        probe: Probe,
        items: list[Item],
        *,
        mirrors: dict[str, dict[str, Any]],
        envs: str,
        models: str | None = None,
        comfy_setting: str | None = None,
    ) -> ScanContext:
        comfy = next((x for x in items if x.detect.type == "comfy"), None)
        configured = comfy.detect.url if comfy and comfy.detect.url else COMFY_URL
        return cls(
            probe,
            await probe.host(),
            await probe.gpu(),
            items,
            mirrors=mirrors,
            variables={"envs": envs, "models": models or await probe.default_dir()},
            comfy_setting=comfy_setting,
            comfy_urls=[configured, *(f"http://127.0.0.1:{port}" for port in COMFY_PORTS)],
        )

    @property
    def has_cuda(self) -> bool:
        return self.gpu is not None and self.gpu.backend == "cuda"

    def expand(self, template: str | None) -> str | None:
        """Fill ``{comfy}`` / ``{envs}`` / ``{models}``; None if a value is unknown or TODO."""
        if not template or TODO in template:
            return None
        try:
            return template.format_map(self.vars)
        except KeyError:
            return None

    async def comfy(self) -> ComfyInstall | None:
        if isinstance(self._comfy, _Unset):
            self._comfy = await self._locate_comfy()
            if self._comfy is not None and self._comfy.root:
                self.vars["comfy"] = self._comfy.root
        return self._comfy

    async def _running(self) -> tuple[str, dict[str, Any]] | None:
        """The first URL that answers like ComfyUI does, with its ``system_stats`` system."""
        for url in self.comfy_urls:
            res = await self.probe.http_get(f"{url}/system_stats")
            if res is None or res.status != 200 or not isinstance(res.body, dict):
                continue
            system = res.body.get("system")
            if isinstance(system, dict) and ("comfyui_version" in system or "argv" in system):
                return url, system
        return None

    async def _locate_comfy(self) -> ComfyInstall | None:
        """Running server first (its argv names main.py), then Comfy Desktop's installations,
        then common folders, then the setting."""
        desktops = await desktop_installs(self.probe, self.host)
        running = await self._running()
        url, system = running if running else (None, {})
        argv = tuple(str(a) for a in system.get("argv") or [])
        root: str | None = None
        main = main_script(argv)
        if main and is_absolute(main):
            root = dirname(main)
        # Desktop starts ComfyUI with a relative main.py and its own model-paths file.
        configs = flag_values(argv, "--extra-model-paths-config")
        desktop = next(
            (d for d in desktops if any(same_path(c, d.model_paths) for c in configs)), None
        )
        if root is None and desktop is not None:
            root = desktop.root
        if root is None:
            for cand in [*(d.root for d in desktops), *self._comfy_candidates()]:
                if await self.probe.exists(join(cand, "main.py")):
                    root = cand
                    break
        if root is None and url is None:
            return None
        if desktop is None and root is not None:
            desktop = next((d for d in desktops if same_path(d.root, root)), None)
        version = system.get("comfyui_version")
        if root is not None and version is None:
            text = await self.probe.read_text(join(root, "comfyui_version.py"))
            m = re.search(r"__version__\s*=\s*['\"]([^'\"]+)", text or "")
            version = m.group(1) if m else None
        if version is None and desktop is not None:
            version = desktop.comfyui_version
        return ComfyInstall(
            root=root,
            version=version,
            url=url,
            python=await self._comfy_python(root),
            port=argv_port(argv) or (int(url.rsplit(":", 1)[1]) if url else None),
            kind=await kind_of(self.probe, root, desktop),
            argv=argv,
            system=system,
            desktop=desktop,
        )

    def _comfy_candidates(self) -> list[str]:
        home = self.host.home
        cands = [join(home, "ComfyUI"), join(home, "Documents", "ComfyUI")]
        if self.host.os == "windows":
            for drive in ("C:", "D:", "E:", "F:"):
                cands += [f"{drive}/ComfyUI", f"{drive}/ComfyUI_windows_portable/ComfyUI"]
        cands.append(join(dirname(self.vars["envs"]), "ComfyUI"))  # where we install it
        if self.comfy_setting:
            cands.append(self.comfy_setting)
        return cands

    async def _comfy_python(self, root: str | None) -> str | None:
        win = self.host.os == "windows"
        cands: list[str] = []
        if root:
            if win:
                cands += [
                    join(dirname(root), "python_embeded", "python.exe"),  # portable build
                    join(root, "venv", "Scripts", "python.exe"),
                    join(root, ".venv", "Scripts", "python.exe"),
                ]
            else:
                cands += [join(root, "venv", "bin", "python"), join(root, ".venv", "bin", "python")]
        cands.append(self.env_python_path("comfy"))
        for cand in cands:
            if await self.probe.exists(cand):
                return cand
        return None

    def env_python_path(self, env: str) -> str:
        if self.host.os == "windows":
            return join(self.vars["envs"], env, "Scripts", "python.exe")
        return join(self.vars["envs"], env, "bin", "python")

    async def env_python(self, env: str) -> str | None:
        """The interpreter of ``env``; for ``comfy``, the one the found ComfyUI runs on.

        Without a ComfyUI yet, ``comfy`` is our own env: PyTorch goes in before ComfyUI does.
        """
        if env == "comfy":
            inst = await self.comfy()
            if inst is not None:
                return inst.python
        path = self.env_python_path(env)
        return path if await self.probe.exists(path) else None

    async def object_info(self) -> dict[str, Any]:
        """``/object_info`` of the running ComfyUI: node class → info (empty when not running)."""
        if self._object_info is None:
            inst = await self.comfy()
            self._object_info = {}
            if inst and inst.url:
                res = await self.probe.http_get(f"{inst.url}/object_info", timeout_s=15)
                if res is not None and res.status == 200 and isinstance(res.body, dict):
                    self._object_info = res.body
        return self._object_info


# --------------------------------------------------------------------------- detectors

Detector = Callable[[Item, ScanContext], Awaitable[Outcome]]

NOT_FOUND = msg("not_found")


async def _platform(item: Item, ctx: ScanContext) -> Outcome:
    host = ctx.host
    if item.detect.field == "ram":
        gb = round(host.ram_gb)
        return Outcome(
            "present", msg("ram_unified", gb=gb) if host.apple_silicon else msg("ram", gb=gb)
        )
    if item.detect.field == "disk_free":
        path = ctx.expand(item.detect.path) or ctx.vars["models"]
        disk = await ctx.probe.disk(path)
        if disk is None:
            return Outcome("warn", msg("check_failed"), fix=None)
        free = size_text(disk.free_gb)
        found = (
            msg("disk_free_on", drive=disk.drive, free=free)
            if disk.drive
            else msg("disk_free", free=free)
        )
        facts = {"path": path, "free_gb": round(disk.free_gb, 1)}
        need = item.require.get("free_gb")
        if need and disk.free_gb < threshold(str(need)):
            return Outcome(
                "warn", found, fix=msg("disk_low", gb=int(threshold(str(need)))), facts=facts
            )
        return Outcome("present", found, facts=facts)
    if host.apple_silicon:
        return Outcome("present", msg("os_apple", name=host.os_name))
    return Outcome("present", msg("os", name=host.os_name, bits=host.bits))


async def _nvml(item: Item, ctx: ScanContext) -> Outcome:
    gpu = ctx.gpu
    if item.detect.field == "cuda_driver_version":
        if gpu is None or gpu.backend != "cuda" or not gpu.cuda_driver:
            return Outcome("skip", msg("no_gpu"), fix=None)
        found = msg("driver_cuda", cuda=short_version(gpu.cuda_driver))
        need = item.require.get("cuda")
        if need and meets(gpu.cuda_driver, str(need)) is False:
            return Outcome("old", found, fix=msg("update_driver", cuda=f"{threshold(str(need)):g}"))
        return Outcome("present", found, version=gpu.cuda_driver)
    if gpu is None:
        return Outcome("warn", msg("no_gpu"))
    if gpu.backend == "mps":
        return Outcome("warn", msg("gpu_unified", name=gpu.name))
    return Outcome("present", msg("gpu_vram", name=gpu.name, gb=round(gpu.vram_gb)))


async def _command(item: Item, ctx: ScanContext) -> Outcome:
    cmd = ctx.expand(item.detect.cmd)
    res = await ctx.probe.run(cmd) if cmd else None
    if res is None or res.code != 0:
        return Outcome("absent", NOT_FOUND)
    if item.detect.version_regex:
        m = re.search(item.detect.version_regex, res.out)
        if m:
            return Outcome("present", msg("version", version=m.group(1)), version=m.group(1))
    return Outcome("present", msg("installed"), version=parse_version_text(res.out))


def parse_version_text(out: str) -> str | None:
    m = re.search(r"\d+\.\d+(?:\.\d+)?", out)
    return m.group(0) if m else None


async def _py_import(item: Item, ctx: ScanContext) -> Outcome:
    python = await ctx.env_python(item.detect.env or "comfy")
    module = item.detect.module
    mod = await ctx.probe.py_module(python, module) if python and module else None
    if mod is None:
        return Outcome("absent", NOT_FOUND)
    facts = {"python": python, "cuda": mod.cuda}
    build = item.require.get("cuda_build")
    if build and ctx.has_cuda and mod.cuda != str(build):
        return Outcome(
            "old",
            msg("torch_not_cuda", cuda=short_version(str(build))),
            version=mod.version,
            facts=facts,
        )
    found = msg("version", version=mod.version) if mod.version else msg("installed")
    return Outcome("present", found, version=mod.version, facts=facts)


async def _file(item: Item, ctx: ScanContext) -> Outcome:
    # sha256 is checked by the installer after a download, not here: hashing tens of GB would
    # make the scan take minutes.
    path = ctx.expand(item.detect.path)
    if path and await ctx.probe.exists(path):
        return Outcome("present", msg("installed"), facts={"path": path})
    return Outcome("absent", NOT_FOUND)


async def _comfy(item: Item, ctx: ScanContext) -> Outcome:
    inst = await ctx.comfy()
    if inst is None:
        return Outcome("absent", NOT_FOUND)
    facts = {
        "root": inst.root,
        "url": inst.url,
        "port": inst.port,
        "kind": inst.kind,
        "python": inst.python,
        "version": inst.version,
    }
    need = item.require.get("version")
    if need and meets(inst.version, str(need)) is False:
        return Outcome("old", msg("outdated"), version=inst.version, facts=facts)
    found = msg("version", version=inst.version) if inst.version else msg("installed")
    return Outcome("present", found, version=inst.version, facts=facts)


async def _comfy_manager(item: Item, ctx: ScanContext) -> Outcome:
    inst = await ctx.comfy()
    manager = await find_manager(ctx.probe, ctx.host, inst) if inst is not None else None
    if manager is None:
        return Outcome("absent", NOT_FOUND)
    found = msg("version", version=manager.version) if manager.version else msg("installed")
    return Outcome("present", found, version=manager.version, facts={"source": manager.source})


async def _comfy_node(item: Item, ctx: ScanContext) -> Outcome:
    inst = await ctx.comfy()
    if inst is None:
        return Outcome("absent", NOT_FOUND)
    d = item.detect
    if d.dir and d.dir != TODO:
        if inst.root and await ctx.probe.exists(join(inst.root, "custom_nodes", d.dir)):
            return Outcome("present", msg("installed"))
        return Outcome("absent", NOT_FOUND)
    if isinstance(d.classes, list) and d.classes:
        known = await ctx.object_info()
        if all(c in known for c in d.classes):
            return Outcome("present", msg("installed"))
    return Outcome("absent", NOT_FOUND)


async def _http(item: Item, ctx: ScanContext) -> Outcome:
    d = item.detect
    if d.speedtest:
        limit = d.max_latency_ms or 1500
        official = ctx.mirrors.get("official", {})
        ms: dict[str, float | None] = {}
        for site in d.speedtest:
            url = official.get(site)
            res = await ctx.probe.http_get(str(url), timeout_s=5) if url else None
            ms[site] = round(res.ms) if res is not None else None
        slow = [s for s, v in ms.items() if v is None or v > limit]
        facts = {"latency_ms": ms}
        if "hf" in slow:
            return Outcome("warn", msg("hf_slow"), facts=facts)
        if slow:
            return Outcome(
                "warn", msg("site_slow", site=SITE_NAMES.get(slow[0], slow[0])), facts=facts
            )
        return Outcome("present", msg("reachable"), facts=facts)
    url = ctx.expand(d.url)
    res = await ctx.probe.http_get(url) if url else None
    if res is not None and res.status == 200:
        return Outcome("present", msg("running"))
    return Outcome("absent", msg("not_running"))


async def _service_urls(urls: list[str], ctx: ScanContext) -> tuple[str, Any] | None:
    for url in urls:
        res = await ctx.probe.http_get(url)
        if res is not None and res.status == 200:
            return url, res.body
    return None


async def _service(item: Item, ctx: ScanContext) -> Outcome:
    hit = await _service_urls(item.detect.urls, ctx)
    if hit is None:
        return Outcome("absent", NOT_FOUND)
    return Outcome("present", msg("running"), facts={"url": hit[0]})


async def _service_model(item: Item, ctx: ScanContext) -> Outcome:
    model = item.detect.model
    server = ctx.items.get(item.detect.server or "")
    if not model or model == TODO or server is None:
        return Outcome("absent", NOT_FOUND)
    hit = await _service_urls(server.detect.urls, ctx)
    body = hit[1] if hit else None
    ids = {str(m.get("id")) for m in body.get("data", [])} if isinstance(body, dict) else set()
    if model in ids:
        return Outcome("present", msg("installed"))
    return Outcome("absent", NOT_FOUND)


async def _keyring(item: Item, ctx: ScanContext) -> Outcome:
    names = sorted({p.key_name for p in get_config().providers.llm_providers if p.key_name})
    count = 0
    for name in names:
        count += await ctx.probe.has_secret(name)
    if count:
        return Outcome("present", msg("keys_set", count=count))
    return Outcome("absent", msg("no_keys"))


async def _resolve(item: Item, ctx: ScanContext) -> Outcome:
    app = await ctx.probe.resolve_app()
    if app is None:
        return Outcome("absent", NOT_FOUND)
    code = "resolve_studio" if app.edition == "studio" else "resolve_free"
    return Outcome("present", msg(code, version=app.version), version=app.version)


DETECTORS: dict[str, Detector] = {
    "platform": _platform,
    "nvml": _nvml,
    "command": _command,
    "py_import": _py_import,
    "file": _file,
    "comfy": _comfy,
    "comfy_manager": _comfy_manager,
    "comfy_node": _comfy_node,
    "http": _http,
    "service": _service,
    "service_model": _service_model,
    "keyring": _keyring,
    "resolve": _resolve,
}


# --------------------------------------------------------------------------- item status

_KIND_STATUS: dict[str, Status] = {"present": "ok", "old": "old", "warn": "warn", "skip": "skip"}


def _default_fix(item: Item, status: Status) -> Message | None:
    if status in ("missing", "optional"):
        if not item.can_install:
            return None
        if item.detect.type in ("comfy_node", "comfy_manager"):
            return msg("install_nodes")
        if item.group == "w":
            return msg("download")
        return msg("install_named", name=item.name.en)
    if status == "old":
        return msg("update_latest")
    if status == "skip":
        return msg("unsupported_skip")
    return None


def finish(item: Item, out: Outcome) -> Detection:
    """Status and fix for ``item`` from what its detector saw."""
    if out.kind == "absent":
        status: Status = item.if_missing or ("missing" if item.required else "optional")
    else:
        status = _KIND_STATUS[out.kind]
    fix: Message | None
    if status == "ok":
        fix = None
    elif status in item.fix:
        fix = item.fix[status]
    elif not isinstance(out.fix, _Unset):
        fix = out.fix
    else:
        fix = _default_fix(item, status)
    installable = item.can_install and status in ("missing", "old", "optional")
    return Detection(
        status=status,
        found=out.found,
        fix=fix,
        installable=installable,
        version=out.version,
        facts=out.facts,
    )


async def detect_item(item: Item, ctx: ScanContext) -> Detection:
    if item.requires_cuda and not ctx.has_cuda:
        return finish(item, Outcome("skip", msg("needs_cuda")))
    try:
        out = await DETECTORS[item.detect.type](item, ctx)
    except Exception:
        logger.exception("setup detector {} failed for {}", item.detect.type, item.id)
        out = Outcome("warn", msg("check_failed"), fix=None)
    return finish(item, out)
