"""The ComfyUI the scan found, read without touching it (SPEC 6.4.1).

Locating it (``ScanContext.comfy()`` in detectors.py) asks a running server first, then looks
in the usual folders, Comfy Desktop's own list of installations first. After the scan,
``identify()`` reads:

- ComfyUI's version and git commit, its Python and PyTorch, and ComfyUI-Manager;
- every node pack in ``custom_nodes``: git ones by HEAD commit and remote, read straight from
  ``.git`` (no git command); Registry ones by ``pyproject.toml`` and the ``.tracking`` file
  ComfyUI-Manager leaves there. With the server running, ``/object_info`` tells which node
  classes each pack provides;
- the model folders (``models/`` plus every ``extra_model_paths.yaml`` in use) and their files,
  path and size only, no hashing (SPEC 12.2). With the server running its ``/models`` lists
  are what count, matched to the files on disk for path and size.

Everything goes through the ``Probe``: nothing is written and nothing is run.
"""

from __future__ import annotations

import hashlib
import json
import re
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal
from urllib.parse import quote

import yaml
from pydantic import BaseModel, Field

from drama_series_agent.setup.pathutil import dirname, is_absolute, join, norm
from drama_series_agent.setup.probe import HostInfo, Probe

# Ports a ComfyUI may answer on when none is configured: its own default, then the first
# Desktop app's. Our backend also defaults to 8000; it never answers /system_stats like
# ComfyUI does, so it is not mistaken for one.
COMFY_PORTS = (8188, 8000)
MODEL_EXTS = frozenset(
    {".safetensors", ".ckpt", ".pt", ".pt2", ".pth", ".bin", ".pkl", ".sft", ".gguf", ".onnx"}
)
MAX_MODEL_FILES = 5000
MAX_MODEL_DEPTH = 4
Kind = Literal["desktop", "portable", "folder", "server"]
_SHA = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?")
_DIST = re.compile(r"^(?P<name>.+?)-(?P<version>[^-]+)\.dist-info$")


# --------------------------------------------------------------------------- locating


@dataclass(frozen=True)
class DesktopInstall:
    """A local installation listed in Comfy Desktop's ``installations.json``."""

    id: str
    root: str  # the ComfyUI folder (main.py) inside the installation
    model_paths: str  # the extra_model_paths file Desktop writes for it
    launch_args: str
    comfyui_version: str | None
    comfyui_commit: str | None
    python: str | None
    torch: str | None


@dataclass(frozen=True)
class ComfyInstall:
    root: str | None  # None when only the running server was found and its argv was relative
    version: str | None
    url: str | None  # set while a server answers
    python: str | None  # the interpreter ComfyUI runs on (portable, its venv, or ours)
    port: int | None = None
    kind: Kind = "folder"
    argv: tuple[str, ...] = ()
    system: dict[str, Any] = field(default_factory=dict)  # /system_stats → "system"
    desktop: DesktopInstall | None = None


def desktop_dir(host: HostInfo) -> str:
    """Where Comfy Desktop keeps its settings (Electron's per-user data folder)."""
    if host.os == "windows":
        return join(host.home, "AppData", "Roaming", "Comfy Desktop")
    if host.os == "macos":
        return join(host.home, "Library", "Application Support", "Comfy Desktop")
    return join(host.home, ".config", "Comfy Desktop")


def _version_tag(tag: Any) -> str | None:
    return str(tag).removeprefix("v") if tag else None


async def desktop_installs(probe: Probe, host: HostInfo) -> list[DesktopInstall]:
    base = desktop_dir(host)
    text = await probe.read_text(join(base, "installations.json"))
    try:
        rows = json.loads(text) if text else []
    except ValueError:
        return []
    out: list[DesktopInstall] = []
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, dict) or not r.get("installPath") or not r.get("id"):
            continue  # Comfy Cloud and other remote entries have no folder
        if r.get("status", "installed") != "installed":
            continue
        ver: dict[str, Any] = r["comfyVersion"] if isinstance(r.get("comfyVersion"), dict) else {}
        stack = r.get("lastVerifiedTorchStack") or {}
        packages = stack.get("packages") if isinstance(stack, dict) else None
        inst_id = str(r["id"])
        out.append(
            DesktopInstall(
                id=inst_id,
                root=join(str(r["installPath"]), "ComfyUI"),
                model_paths=join(base, "instance-model-paths", f"{inst_id}.yaml"),
                launch_args=str(r.get("launchArgs") or ""),
                comfyui_version=_version_tag(ver.get("baseTag") or r.get("comfyVersionTag")),
                comfyui_commit=ver.get("commit"),
                python=r.get("pythonVersion"),
                torch=packages.get("torch") if isinstance(packages, dict) else None,
            )
        )
    return out


def flag_values(argv: Sequence[str], flag: str) -> list[str]:
    """Values given to ``flag``: ``--flag a b`` (up to the next option) or ``--flag=a``."""
    out: list[str] = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        i += 1
        if arg == flag:
            while i < len(argv) and not argv[i].startswith("--"):
                out.append(argv[i])
                i += 1
        elif arg.startswith(flag + "="):
            out.append(arg.split("=", 1)[1])
    return out


def argv_port(argv: Sequence[str]) -> int | None:
    values = flag_values(argv, "--port")
    return int(values[-1]) if values and values[-1].isdigit() else None


def main_script(argv: Sequence[str]) -> str | None:
    return next((a for a in argv if a.replace("\\", "/").endswith("main.py")), None)


async def kind_of(probe: Probe, root: str | None, desktop: DesktopInstall | None) -> Kind:
    if root is None:
        return "server"
    marker = await probe.read_text(join(root, ".comfy_environment"))  # Desktop builds say so
    if desktop is not None or (marker and "desktop" in marker):
        return "desktop"
    if await probe.exists(join(dirname(root), "python_embeded")):
        return "portable"
    return "folder"


# --------------------------------------------------------------------------- what it holds


class NodePack(BaseModel):
    name: str  # folder (or module file) under custom_nodes; the server's module name
    # git: a clone; registry: installed by ComfyUI-Manager from the Registry; manual: copied in
    # by hand or a single .py file; unknown: the server loaded it from a folder we did not read.
    source: Literal["git", "registry", "manual", "unknown"]
    version: str | None = None  # pyproject.toml
    commit: str | None = None
    remote: str | None = None  # credentials removed
    classes: list[str] = Field(default_factory=list)


class ComfyEnvInfo(BaseModel):
    """What ``comfy_env`` keeps under its content hash: which ComfyUI and nodes made a take."""

    comfyui_version: str | None
    comfyui_commit: str | None
    python: str | None  # version
    torch: str | None
    node_packs: list[NodePack]

    def content_hash(self) -> str:
        blob = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode()).hexdigest()


class Manager(BaseModel):
    source: Literal["pip", "custom_node"]  # pip: the comfyui_manager package (--enable-manager)
    version: str | None
    enabled: bool | None  # pip: started with --enable-manager; None when that is unknown


class ModelDir(BaseModel):
    folder: str  # ComfyUI's folder name: checkpoints, loras, vae …
    path: str


class ModelFile(BaseModel):
    folder: str
    name: str  # as ComfyUI lists it, "/"-separated within the folder
    path: str | None  # None: the server lists it but we did not find it on disk
    size_bytes: int | None


class ComfyScan(BaseModel):
    """Where the found ComfyUI is and what it can load (``machine_profile`` → ``comfy``)."""

    root: str | None
    kind: Kind
    url: str | None
    port: int | None
    python_path: str | None
    manager: Manager | None
    model_dirs: list[ModelDir]
    models: list[ModelFile]
    models_truncated: bool = False  # more than MAX_MODEL_FILES model files
    env_hash: str


@dataclass(frozen=True)
class Identified:
    scan: ComfyScan
    env: ComfyEnvInfo


async def identify(
    probe: Probe, host: HostInfo, inst: ComfyInstall, object_info: dict[str, Any]
) -> Identified:
    desk = inst.desktop
    dists = await installed_dists(probe, inst.python, host) if inst.python else {}
    python = (
        _leading_version(inst.system.get("python_version"))
        or await _venv_version(probe, inst.python)
        or (desk.python if desk else None)
    )
    torch = (
        inst.system.get("pytorch_version") or dists.get("torch") or (desk.torch if desk else None)
    )
    git = await read_git(probe, inst.root) if inst.root else None
    packs = await node_packs(probe, inst.root, object_info)
    env = ComfyEnvInfo(
        comfyui_version=inst.version,
        comfyui_commit=(git.commit if git else None) or (desk.comfyui_commit if desk else None),
        python=python,
        torch=str(torch) if torch else None,
        node_packs=packs,
    )
    dirs = await model_dirs(probe, inst)
    models, truncated = await model_files(probe, inst.url, dirs)
    return Identified(
        scan=ComfyScan(
            root=inst.root,
            kind=inst.kind,
            url=inst.url,
            port=inst.port,
            python_path=inst.python,
            manager=_manager(inst, dists, packs),
            model_dirs=dirs,
            models=models,
            models_truncated=truncated,
            env_hash=env.content_hash(),
        ),
        env=env,
    )


def _leading_version(text: Any) -> str | None:
    m = re.match(r"\d+(?:\.\d+)*", str(text)) if text else None
    return m.group(0) if m else None


async def _venv_version(probe: Probe, python: str | None) -> str | None:
    if not python:
        return None
    text = await probe.read_text(join(dirname(dirname(python)), "pyvenv.cfg"))
    m = re.search(r"^\s*version(?:_info)?\s*=\s*(\d+\.\d+\.\d+)", text or "", re.MULTILINE)
    return m.group(1) if m else None


def _canon(name: str) -> str:
    return re.sub(r"[-_.]+", "_", name).lower()


async def installed_dists(probe: Probe, python: str, host: HostInfo) -> dict[str, str]:
    """Package → version, from the ``*.dist-info`` folders next to ``python``."""
    env = dirname(dirname(python))  # venv/Scripts/python.exe, venv/bin/python
    if host.os == "windows":
        # A venv, or the portable build's python_embeded/python.exe.
        cands = [join(env, "Lib", "site-packages"), join(dirname(python), "Lib", "site-packages")]
    else:
        libs = await probe.list_dir(join(env, "lib")) or []
        cands = [
            join(env, "lib", e.name, "site-packages")
            for e in libs
            if e.is_dir and e.name.startswith("python")
        ]
    for cand in cands:
        entries = await probe.list_dir(cand)
        if entries is not None:
            return {
                _canon(m["name"]): m["version"]
                for e in entries
                if e.is_dir and (m := _DIST.match(e.name))
            }
    return {}


@dataclass(frozen=True)
class GitInfo:
    commit: str | None
    remote: str | None


async def read_git(probe: Probe, folder: str) -> GitInfo | None:
    """HEAD commit and remote of a clone, from the files in ``.git`` (git itself is not run)."""
    dot = join(folder, ".git")
    if not await probe.exists(dot):
        return None
    gitdir = dot
    pointer = await probe.read_text(dot)  # worktrees and submodules: a file "gitdir: <path>"
    if pointer and pointer.startswith("gitdir:"):
        target = pointer.split(":", 1)[1].strip()
        gitdir = target if is_absolute(target) else join(folder, target)
    head = (await probe.read_text(join(gitdir, "HEAD")) or "").strip()
    commit: str | None = None
    if head.startswith("ref:"):
        ref = head[4:].strip()
        loose = (await probe.read_text(join(gitdir, *ref.split("/"))) or "").strip()
        commit = loose if _SHA.fullmatch(loose) else None
        if commit is None:
            for line in (await probe.read_text(join(gitdir, "packed-refs")) or "").splitlines():
                sha, _, name = line.partition(" ")
                if name.strip() == ref and _SHA.fullmatch(sha):
                    commit = sha
                    break
    elif _SHA.fullmatch(head):
        commit = head  # detached, e.g. checked out at a pinned commit
    return GitInfo(commit=commit, remote=_remote(await probe.read_text(join(gitdir, "config"))))


def _remote(config: str | None) -> str | None:
    urls: dict[str, str] = {}
    section: str | None = None
    for raw in (config or "").splitlines():
        line = raw.strip()
        if line.startswith("["):
            m = re.match(r'\[remote\s+"([^"]+)"\]', line)
            section = m.group(1) if m else None
        elif section and (m := re.match(r"url\s*=\s*(\S+)", line)):
            urls.setdefault(section, m.group(1))
    url = urls.get("origin") or next(iter(urls.values()), None)
    return re.sub(r"(?<=//)[^/@\s]+@", "", url) if url else None  # never keep a token


async def pyproject_version(probe: Probe, folder: str) -> str | None:
    text = await probe.read_text(join(folder, "pyproject.toml"))
    if not text:
        return None
    try:
        version = (tomllib.loads(text).get("project") or {}).get("version")
    except tomllib.TOMLDecodeError:
        m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
        version = m.group(1) if m else None
    return str(version) if version else None


async def node_packs(probe: Probe, root: str | None, object_info: dict[str, Any]) -> list[NodePack]:
    classes: dict[str, list[str]] = {}
    for name, info in object_info.items():
        module = info.get("python_module") if isinstance(info, dict) else None
        if isinstance(module, str) and module.startswith("custom_nodes."):
            classes.setdefault(module.split(".")[1], []).append(name)
    packs: list[NodePack] = []
    entries = await probe.list_dir(join(root, "custom_nodes")) if root else None
    for e in entries or []:
        if e.name.startswith((".", "__")) or e.name.endswith(".disabled"):
            continue
        if not e.is_dir:
            if e.name.endswith(".py"):  # ComfyUI loads single-file nodes too
                stem = e.name[:-3]
                packs.append(NodePack(name=stem, source="manual", classes=classes.pop(stem, [])))
            continue
        folder = join(root or "", "custom_nodes", e.name)
        git = await read_git(probe, folder)
        registry = git is None and await probe.exists(join(folder, ".tracking"))
        packs.append(
            NodePack(
                name=e.name,
                source="git" if git else "registry" if registry else "manual",
                version=await pyproject_version(probe, folder),
                commit=git.commit if git else None,
                remote=git.remote if git else None,
                classes=classes.pop(e.name, []),
            )
        )
    # Loaded by the server from somewhere we did not read: known by name only.
    packs += [NodePack(name=n, source="unknown", classes=c) for n, c in classes.items()]
    for p in packs:
        p.classes.sort()
    return sorted(packs, key=lambda p: p.name.lower())


def _manager(inst: ComfyInstall, dists: dict[str, str], packs: list[NodePack]) -> Manager | None:
    if version := dists.get("comfyui_manager"):
        args = list(inst.argv) or (inst.desktop.launch_args.split() if inst.desktop else [])
        return Manager(source="pip", version=version, enabled=("--enable-manager" in args) or None)
    pack = next((p for p in packs if p.name.lower() == "comfyui-manager"), None)
    if pack is None:
        return None
    version = pack.version or (pack.commit[:7] if pack.commit else None)
    return Manager(source="custom_node", version=version, enabled=True)


async def model_dirs(probe: Probe, inst: ComfyInstall) -> list[ModelDir]:
    dirs: list[ModelDir] = []
    configs: list[str] = []
    if inst.root:
        base = join(inst.root, "models")
        dirs += [
            ModelDir(folder=e.name, path=join(base, e.name))
            for e in await probe.list_dir(base) or []
            if e.is_dir
        ]
        configs += [
            c if is_absolute(c) else join(inst.root, c)
            for c in flag_values(inst.argv, "--extra-model-paths-config")
        ]
        configs.append(join(inst.root, "extra_model_paths.yaml"))  # ComfyUI reads it if there
    elif inst.argv:
        configs += [
            c for c in flag_values(inst.argv, "--extra-model-paths-config") if is_absolute(c)
        ]
    if inst.desktop:
        configs.append(inst.desktop.model_paths)
    seen: set[str] = set()
    for config in configs:
        if norm(config) in seen:
            continue
        seen.add(norm(config))
        text = await probe.read_text(config)
        if text:
            dirs += extra_model_dirs(text, dirname(config))
    unique: dict[tuple[str, str], ModelDir] = {}
    for d in dirs:
        unique.setdefault((d.folder, norm(d.path)), d)
    return list(unique.values())


def extra_model_dirs(text: str, config_dir: str) -> list[ModelDir]:
    """Folders an ``extra_model_paths.yaml`` adds: per section, ``base_path`` + one path a line."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return []
    out: list[ModelDir] = []
    for section in data.values() if isinstance(data, dict) else []:
        if not isinstance(section, dict):
            continue
        base = str(section.get("base_path") or "")
        if base and not is_absolute(base):
            base = join(config_dir, base)  # relative to the file, as ComfyUI reads it
        for key, value in section.items():
            if key in ("base_path", "is_default") or not isinstance(value, str):
                continue
            for line in value.splitlines():
                path = line.strip()
                if not path:
                    continue
                full = path.rstrip("/\\") if is_absolute(path) else join(base or config_dir, path)
                out.append(ModelDir(folder=str(key), path=full))
    return out


def _is_model(name: str) -> bool:
    dot = name.rfind(".")
    return dot > 0 and name[dot:].lower() in MODEL_EXTS


async def _walk(probe: Probe, path: str, budget: int) -> tuple[list[tuple[str, int | None]], bool]:
    """Model files under ``path`` (relative, "/"-separated) and whether ``budget`` ran out."""
    out: list[tuple[str, int | None]] = []

    async def visit(folder: str, prefix: str, depth: int) -> bool:
        for e in await probe.list_dir(folder) or []:
            if e.name.startswith("."):
                continue
            if e.is_dir:
                if depth > 1 and await visit(join(folder, e.name), f"{prefix}{e.name}/", depth - 1):
                    return True
            elif _is_model(e.name):
                if len(out) >= budget:
                    return True
                out.append((f"{prefix}{e.name}", e.size))
        return False

    more = await visit(path, "", MAX_MODEL_DEPTH)
    return out, more


async def _served(probe: Probe, url: str) -> dict[str, list[str]] | None:
    """``/models`` and ``/models/{folder}`` of the running server; None when it has no such API."""
    res = await probe.http_get(f"{url}/models", timeout_s=10)
    if res is None or res.status != 200 or not isinstance(res.body, list):
        return None
    out: dict[str, list[str]] = {}
    for folder in res.body:
        if not isinstance(folder, str):
            continue
        r = await probe.http_get(f"{url}/models/{quote(folder)}", timeout_s=10)
        names = r.body if r is not None and r.status == 200 and isinstance(r.body, list) else []
        out[folder] = [str(n).replace("\\", "/") for n in names if isinstance(n, str)]
    return out


async def model_files(
    probe: Probe, url: str | None, dirs: list[ModelDir]
) -> tuple[list[ModelFile], bool]:
    disk: dict[tuple[str, str], ModelFile] = {}
    truncated = False
    for d in dirs:
        files, more = await _walk(probe, d.path, MAX_MODEL_FILES - len(disk))
        for rel, size in files:
            path = join(d.path, *rel.split("/"))
            disk.setdefault(
                (d.folder, rel), ModelFile(folder=d.folder, name=rel, path=path, size_bytes=size)
            )
        if more:
            truncated = True
            break
    served = await _served(probe, url) if url else None
    if served is None:
        return list(disk.values()), truncated
    models: list[ModelFile] = []
    for folder, names in served.items():
        for name in names:
            if len(models) >= MAX_MODEL_FILES:
                return models, True
            models.append(
                disk.get((folder, name))
                or ModelFile(folder=folder, name=name, path=None, size_bytes=None)
            )
    return models, truncated
