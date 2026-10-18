"""Identifying the ComfyUI already on the machine, read-only (SPEC 6.4.1, step 4c)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import httpx

from drama_series_agent.setup.comfy import (
    Identified,
    ModelFile,
    argv_port,
    extra_model_dirs,
    flag_values,
    identify,
    read_git,
)
from drama_series_agent.setup.detectors import ScanContext
from drama_series_agent.setup.manifest import load_manifest
from drama_series_agent.setup.probe import FakeProbe, HostInfo, Probe, RealProbe

VHS_COMMIT = "8a3f6c1e9b2d4f70a5c8e1b3d6f9a2c4e7b0d1f3"


async def _context(probe: Probe, **kw: Any) -> ScanContext:
    m = load_manifest()
    items = m.for_platform((await probe.host()).os)
    return await ScanContext.create(probe, items, mirrors=m.mirrors, envs="C:/x/envs", **kw)


async def _identify(probe: Probe) -> Identified | None:
    ctx = await _context(probe)
    inst = await ctx.comfy()
    return None if inst is None else await identify(probe, ctx.host, inst, await ctx.object_info())


def _models(found: Identified) -> dict[tuple[str, str], tuple[str | None, int | None]]:
    return {(m.folder, m.name): (m.path, m.size_bytes) for m in found.scan.models}


async def test_the_pc_sample_running() -> None:
    found = await _identify(FakeProbe.load("pc"))
    assert found is not None
    scan, env = found.scan, found.env
    assert (scan.root, scan.kind, scan.url, scan.port) == (
        "D:\\ComfyUI",
        "folder",
        "http://127.0.0.1:8188",
        8188,
    )
    assert scan.python_path == "D:\\ComfyUI\\venv\\Scripts\\python.exe"  # argv's separators
    assert (env.comfyui_version, env.comfyui_commit, env.python, env.torch) == (
        "0.3.40",
        None,
        "3.12.9",
        "2.7.1+cu128",
    )
    assert scan.manager is None

    packs = {p.name: p for p in env.node_packs}
    assert list(packs) == ["ComfyUI-KJNodes", "ComfyUI-VideoHelperSuite", "websocket_image_save"]
    vhs, kj = packs["ComfyUI-VideoHelperSuite"], packs["ComfyUI-KJNodes"]
    assert (vhs.source, vhs.commit, vhs.version) == ("git", VHS_COMMIT, "1.7.9")
    assert vhs.remote == "https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite"
    assert vhs.classes == ["VHS_LoadVideo", "VHS_VideoCombine"]
    assert (kj.source, kj.version, kj.commit) == ("registry", "1.2.6", None)
    assert kj.classes == ["GetImageSizeAndCount", "ImageResizeKJ"]
    assert packs["websocket_image_save"].source == "manual"

    dirs = {(d.folder, d.path) for d in scan.model_dirs}
    assert dirs == {
        ("checkpoints", "D:\\ComfyUI\\models\\checkpoints"),
        ("vae", "D:\\ComfyUI\\models\\vae"),
        ("checkpoints", "D:/AI/models/checkpoints"),
        ("loras", "D:/AI/models/loras"),
    }
    # The server's lists count; the files on disk give path and size.
    assert _models(found) == {
        ("checkpoints", "sd_xl_base_1.0.safetensors"): (
            "D:\\ComfyUI\\models\\checkpoints\\sd_xl_base_1.0.safetensors",
            6938078334,
        ),
        ("loras", "rain/rain_style.safetensors"): (
            "D:/AI/models/loras/rain/rain_style.safetensors",
            228456789,
        ),
        ("vae", "ae.safetensors"): ("D:\\ComfyUI\\models\\vae\\ae.safetensors", 335304388),
    }
    assert scan.env_hash == env.content_hash()


async def test_the_pc_sample_not_running_reads_the_disk() -> None:
    probe = FakeProbe.load("pc")
    probe.data["http"] = {}
    probe.texts["D:/ComfyUI/comfyui_version.py"] = '__version__ = "0.3.40"\n'
    found = await _identify(probe)
    assert found is not None
    assert (found.scan.url, found.scan.port, found.scan.root) == (None, None, "D:/ComfyUI")
    # Python from pyvenv.cfg, PyTorch from its dist-info folder.
    assert (found.env.python, found.env.torch) == ("3.12.9", "2.7.1+cu128")
    assert all(p.classes == [] for p in found.env.node_packs)  # classes need the server
    assert set(_models(found)) == {
        ("checkpoints", "sd_xl_base_1.0.safetensors"),  # put_checkpoints_here is not a model
        ("loras", "rain/rain_style.safetensors"),
        ("vae", "ae.safetensors"),
    }


async def test_the_environment_hash_follows_the_node_packs() -> None:
    a = await _identify(FakeProbe.load("pc"))
    b = await _identify(FakeProbe.load("pc"))
    assert a is not None and b is not None and a.scan.env_hash == b.scan.env_hash
    probe = FakeProbe.load("pc")
    probe.texts["D:/ComfyUI/custom_nodes/ComfyUI-KJNodes/pyproject.toml"] = (
        '[project]\nname = "comfyui-kjnodes"\nversion = "1.2.7"\n'
    )
    c = await _identify(probe)
    assert c is not None and c.scan.env_hash != a.scan.env_hash
    # Model files are not part of the environment.
    probe = FakeProbe.load("pc")
    probe.sizes["D:/ComfyUI/models/vae/other.safetensors"] = 1
    d = await _identify(probe)
    assert d is not None and d.scan.env_hash == a.scan.env_hash


async def test_the_mac_sample_has_no_comfyui() -> None:
    assert await _identify(FakeProbe.load("mac")) is None


async def test_git_details() -> None:
    sha = "0123456789abcdef0123456789abcdef01234567"
    probe = FakeProbe(
        {
            "texts": {
                # detached at a pinned commit, remote with a token in it
                "/n/a/.git/HEAD": sha + "\n",
                "/n/a/.git/config": '[remote "origin"]\n  url = https://bob:ghp_x@github.com/o/a\n',
                # a loose ref
                "/n/b/.git/HEAD": "ref: refs/heads/dev\n",
                "/n/b/.git/refs/heads/dev": sha + "\n",
                "/n/b/.git/config": '[remote "fork"]\n  url = git@github.com:o/b.git\n',
                # a submodule: .git is a file pointing elsewhere
                "/n/c/.git": "gitdir: ../.git/modules/c\n",
                "/n/.git/modules/c/HEAD": sha + "\n",
            }
        }
    )
    a = await read_git(probe, "/n/a")
    assert a is not None and (a.commit, a.remote) == (sha, "https://github.com/o/a")
    b = await read_git(probe, "/n/b")
    assert b is not None and (b.commit, b.remote) == (sha, "git@github.com:o/b.git")
    c = await read_git(probe, "/n/c")
    assert c is not None and (c.commit, c.remote) == (sha, None)
    assert await read_git(probe, "/n/d") is None


def test_extra_model_paths_files() -> None:
    desktop = (
        "comfy.desktop_0:\n"
        "  base_path: 'C:\\Users\\k\\Comfy-Desktop\\ComfyUI-Shared\\models'\n"
        "  is_default: true\n"
        "  'checkpoints': 'checkpoints/'\n"
        "  'controlnet': |-\n    controlnet/\n    t2i_adapter/\n"
    )
    got = [(d.folder, d.path) for d in extra_model_dirs(desktop, "C:\\x")]
    shared = "C:\\Users\\k\\Comfy-Desktop\\ComfyUI-Shared\\models"
    assert got == [
        ("checkpoints", f"{shared}\\checkpoints"),
        ("controlnet", f"{shared}\\controlnet"),
        ("controlnet", f"{shared}\\t2i_adapter"),
    ]
    relative = "a1111:\n  base_path: ../sd\n  loras: models/Lora\n"
    assert [(d.folder, d.path) for d in extra_model_dirs(relative, "/srv/comfy")] == [
        ("loras", "/srv/comfy/../sd/models/Lora")
    ]
    assert extra_model_dirs("not: [valid", "/x") == []


def test_reading_argv() -> None:
    argv = ["main.py", "--port", "8190", "--extra-model-paths-config", "a.yaml", "b.yaml", "--x"]
    assert argv_port(argv) == 8190
    assert flag_values(argv, "--extra-model-paths-config") == ["a.yaml", "b.yaml"]
    assert flag_values(["--port=9000"], "--port") == ["9000"]
    assert argv_port(["main.py"]) is None


# --------------------------------------------------------------------------- real probe

INSTALL_ID = "inst-1792192213598"


def _desktop_machine(home: Path) -> tuple[Path, Path]:
    """Comfy Desktop 2's layout, as seen on Kelvin's PC (2026-10-18). Returns (root, shared)."""
    install = home / "AppData" / "Local" / "Comfy-Desktop" / "ComfyUI-Installs" / "ComfyUI"
    root = install / "ComfyUI"
    shared = home / "AppData" / "Local" / "Comfy-Desktop" / "ComfyUI-Shared" / "models"
    settings = home / "AppData" / "Roaming" / "Comfy Desktop"
    site = root / ".venv" / "Lib" / "site-packages"
    files: dict[Path, str] = {
        root / "main.py": "",
        root / "comfyui_version.py": '__version__ = "0.41.2"\n',
        root / ".comfy_environment": "local-desktop2-standalone\n",
        root / ".git" / "HEAD": "b53f77a74e21091cbdebfdf7b85fc80326932646\n",
        root / ".venv" / "Scripts" / "python.exe": "",
        root / ".venv" / "pyvenv.cfg": "home = x\nversion_info = 3.13.12\n",
        site / "torch-2.12.1+cu130.dist-info" / "METADATA": "",
        site / "comfyui_manager-4.2.2.dist-info" / "METADATA": "",
        root / "custom_nodes" / "websocket_image_save.py": "",
        root / "custom_nodes" / "example_node.py.example": "",
        root / "custom_nodes" / "ComfyUI-Foo" / "__init__.py": "",
        root / "custom_nodes" / "ComfyUI-Foo" / ".git" / "HEAD": "ref: refs/heads/main\n",
        root / "custom_nodes" / "ComfyUI-Foo" / ".git" / "refs" / "heads" / "main": "1" * 40 + "\n",
        root / "custom_nodes" / ".disabled" / "Old" / "__init__.py": "",
        root / "models" / "vae" / "put_vae_here": "",
        shared / "checkpoints" / "flux" / "flux2.safetensors": "x" * 1234,
        shared / "loras" / "a.safetensors": "x" * 10,
        settings / "installations.json": json.dumps(
            [
                {
                    "id": INSTALL_ID,
                    "name": "ComfyUI",
                    "installPath": str(install),
                    "sourceId": "standalone",
                    "pythonVersion": "3.13.12",
                    "launchArgs": "--enable-manager",
                    "status": "installed",
                    "comfyVersion": {"commit": "b53f77a7" + "0" * 32, "baseTag": "v0.41.2"},
                    "lastVerifiedTorchStack": {"packages": {"torch": "2.12.1+cu130"}},
                },
                {"id": "inst-cloud", "name": "Comfy Cloud", "sourceId": "cloud"},
            ]
        ),
        settings / "instance-model-paths" / f"{INSTALL_ID}.yaml": (
            "comfy.desktop_0:\n"
            f"  base_path: '{shared}'\n"
            "  is_default: true\n"
            "  'checkpoints': 'checkpoints/'\n"
            "  'loras': 'loras/'\n"
        ),
    }
    for path, text in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode())
    return root, shared


def _snapshot(base: Path) -> dict[str, tuple[int, int, str]]:
    return {
        str(p): (p.stat().st_size, p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest())
        for p in sorted(base.rglob("*"))
        if p.is_file()
    }


def _host(home: Path) -> HostInfo:
    return HostInfo(
        os="windows", os_name="Windows 11", bits=64, arch="amd64", ram_gb=32, home=str(home)
    )


async def _real_identify(probe: RealProbe, home: Path, urls: list[str]) -> Identified:
    m = load_manifest()
    ctx = ScanContext(
        probe,
        _host(home),
        None,
        m.for_platform("windows"),
        mirrors={},
        variables={"envs": str(home / ".drama-studio" / "envs"), "models": str(home / "m")},
        comfy_urls=urls,
    )
    inst = await ctx.comfy()
    assert inst is not None
    return await identify(probe, ctx.host, inst, await ctx.object_info())


async def test_real_probe_reads_comfy_desktop_without_writing(tmp_path: Path) -> None:
    root, shared = _desktop_machine(tmp_path)
    before = _snapshot(tmp_path)
    found = await _real_identify(RealProbe(), tmp_path, urls=[])  # not running
    assert _snapshot(tmp_path) == before  # nothing written, nothing changed

    scan, env = found.scan, found.env
    assert (scan.root, scan.kind, scan.url) == (str(root), "desktop", None)
    assert scan.python_path == str(root / ".venv" / "Scripts" / "python.exe")
    assert (env.comfyui_version, env.python, env.torch) == ("0.41.2", "3.13.12", "2.12.1+cu130")
    assert env.comfyui_commit == "b53f77a74e21091cbdebfdf7b85fc80326932646"  # its own .git
    assert scan.manager is not None
    assert scan.manager.model_dump() == {"source": "pip", "version": "4.2.2", "enabled": True}
    packs = {p.name: (p.source, p.commit) for p in env.node_packs}
    assert packs == {"ComfyUI-Foo": ("git", "1" * 40), "websocket_image_save": ("manual", None)}
    sep = "\\" if "\\" in str(shared) else "/"
    assert {(m.folder, m.name, m.size_bytes) for m in scan.models} == {
        ("checkpoints", "flux/flux2.safetensors", 1234),
        ("loras", "a.safetensors", 10),
    }
    flux = next(m for m in scan.models if m.folder == "checkpoints")
    assert flux.path == sep.join([str(shared), "checkpoints", "flux", "flux2.safetensors"])


async def test_real_probe_matches_a_running_desktop_by_its_model_paths(tmp_path: Path) -> None:
    root, _ = _desktop_machine(tmp_path)
    config = tmp_path / "AppData" / "Roaming" / "Comfy Desktop" / "instance-model-paths"
    argv = [
        "ComfyUI\\main.py",  # relative: Desktop starts it from the installation folder
        "--enable-manager",
        "--extra-model-paths-config",
        str(config / f"{INSTALL_ID}.yaml"),
        "--port",
        "8190",
    ]
    replies: dict[str, Any] = {
        "/system_stats": {
            "system": {
                "comfyui_version": "0.41.2",
                "python_version": "3.13.12 (main, Feb 12 2026, 00:38:53) [MSC v.1944 64 bit]",
                "pytorch_version": "2.12.1+cu130",
                "argv": argv,
            }
        },
        "/object_info": {
            "KSampler": {"python_module": "nodes"},
            "FooNode": {"python_module": "custom_nodes.ComfyUI-Foo"},
            "BarNode": {"python_module": "custom_nodes.ComfyUI-Bar"},  # loaded from elsewhere
        },
        "/models": ["checkpoints", "loras"],
        "/models/checkpoints": ["flux\\flux2.safetensors", "gone.safetensors"],
        "/models/loras": [],
    }

    def answer(request: httpx.Request) -> httpx.Response:
        body = replies.get(request.url.path)
        return httpx.Response(404) if body is None else httpx.Response(200, json=body)

    before = _snapshot(tmp_path)
    probe = RealProbe(httpx.MockTransport(answer))
    found = await _real_identify(probe, tmp_path, urls=["http://127.0.0.1:8190"])
    assert _snapshot(tmp_path) == before

    scan, env = found.scan, found.env
    assert (scan.root, scan.kind, scan.port) == (str(root), "desktop", 8190)
    assert env.python == "3.13.12"
    packs = {p.name: (p.source, p.classes) for p in env.node_packs}
    assert packs["ComfyUI-Foo"] == ("git", ["FooNode"])
    assert packs["ComfyUI-Bar"] == ("unknown", ["BarNode"])
    assert {(m.folder, m.name, m.size_bytes) for m in scan.models} == {
        ("checkpoints", "flux/flux2.safetensors", 1234),
        ("checkpoints", "gone.safetensors", None),  # listed by the server, not on disk
    }
    assert ModelFile(folder="checkpoints", name="gone.safetensors", path=None, size_bytes=None) in (
        scan.models
    )
