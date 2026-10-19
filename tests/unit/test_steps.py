"""Real install steps, with commands recorded instead of run and downloads from a mock server."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, get_args

import httpx
import pytest

from drama_series_agent.core.paths import REPO_ROOT
from drama_series_agent.setup.comfy import ModelDir
from drama_series_agent.setup.installer import InstallEnv, InstallError, Transfer
from drama_series_agent.setup.manifest import OS, Detect, Item, Step, load_manifest
from drama_series_agent.setup.pathutil import join
from drama_series_agent.setup.snapshots import SnapshotFailure
from drama_series_agent.setup.steps import (
    WINGET_ALREADY_INSTALLED,
    RealRunner,
    _python_in,
    speed_test_url,
)

MIRRORS = load_manifest().mirrors
KNOWN = {"uv", "git", "winget", "brew", "sudo"}


class Recorder:
    """Stands in for running commands: records them and fakes what they leave behind."""

    def __init__(
        self,
        os: OS = "windows",
        head: str = "",
        codes: dict[str, int] | None = None,
        torch: str = "2.12.1+cu130",
    ):
        self.os = os
        self.head = head
        self.codes = codes or {}
        self.torch = torch  # what `python -c "import torch; ..."` prints
        self.calls: list[list[str]] = []

    async def __call__(self, argv: list[str], *, cwd: str | None, on_line: Any) -> int:
        self.calls.append(argv)
        await on_line(f"$ {' '.join(argv[:3])}")
        self._leave_behind(argv)
        if "rev-parse" in argv and self.head:
            await on_line(self.head)
        if argv[1:2] == ["-c"] and "import torch" in argv[2]:
            await on_line(self.torch)
        return self.codes.get(argv[1] if len(argv) > 1 else argv[0], 0)

    def _leave_behind(self, argv: list[str]) -> None:
        if argv[1:3] == ["venv", "--python"]:
            py = Path(_python_in(argv[4], self.os))
            py.parent.mkdir(parents=True, exist_ok=True)
            py.touch()
        elif argv[1] == "clone":
            (Path(argv[-1]) / ".git").mkdir(parents=True)


def _which(name: str) -> str | None:
    return name if name in KNOWN else None


def _item(*steps: dict[str, Any], item_id: str = "x", group: str = "rt") -> Item:
    return Item.model_validate(
        {
            "id": item_id,
            "group": group,
            "name": {"zh": item_id, "en": item_id},
            "detect": {"type": "command", "cmd": "x"},
            "install": list(steps),
        }
    )


def _env(tmp_path: Path, os: OS = "windows", **kw: Any) -> InstallEnv:
    base: dict[str, Any] = {
        "os": os,
        "mirror": "official",
        "models": str(tmp_path / "models"),
        "envs": str(tmp_path / "envs"),
        "comfy": str(tmp_path / "ComfyUI"),
    }
    return InstallEnv(**{**base, **kw})


class Log:
    def __init__(self) -> None:
        self.lines: list[tuple[str, str, dict[str, Any]]] = []
        self.pct: list[float] = []
        self.transfers: list[Transfer] = []

    async def log(self, level: str, code: str, params: dict[str, Any]) -> None:
        self.lines.append((level, code, params))

    async def progress(self, pct: float, transfer: Transfer | None = None) -> None:
        self.pct.append(pct)
        if transfer is not None:
            self.transfers.append(transfer)


def _offline(request: httpx.Request) -> httpx.Response:
    raise AssertionError(f"a unit test reached the network: {request.url}")


async def _install(
    item: Item,
    env: InstallEnv,
    rec: Recorder | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    **kw: Any,
) -> tuple[Recorder, Log]:
    rec = rec or Recorder(env.os)
    log = Log()
    # Never the real network: a manifest with real addresses would download for real (tens of GB).
    transport = transport or httpx.MockTransport(_offline)
    runner = RealRunner(mirrors=MIRRORS, exec_=rec, which=_which, transport=transport, **kw)
    await runner.install(item, env, log.log, log.progress)
    return rec, log


# --------------------------------------------------------------------------- uv


async def test_uv_goes_into_our_envs_and_only_once(tmp_path: Path) -> None:
    env = _env(tmp_path)
    item = _item({"type": "uv_pip", "env": "comfy", "packages": ["torch", "torchvision"]})
    rec, log = await _install(item, env)
    venv = join(str(tmp_path / "envs"), "comfy")
    py = _python_in(venv, "windows")
    assert rec.calls == [
        ["uv", "venv", "--python", "3.12", venv],
        ["uv", "pip", "install", "--python", py, "torch", "torchvision"],
    ]
    assert ("info", "output", {"text": "$ uv pip install"}) in log.lines
    assert log.pct[-1] == 100
    rec2, _ = await _install(item, env)
    assert rec2.calls == [["uv", "pip", "install", "--python", py, "torch", "torchvision"]]


async def test_uv_uses_the_python_of_the_comfyui_we_found(tmp_path: Path) -> None:
    env = _env(tmp_path, comfy_python="D:/ComfyUI/venv/Scripts/python.exe")
    item = _item({"type": "uv_pip", "env": "comfy", "requirements": "{comfy}/requirements.txt"})
    rec, _ = await _install(item, env)
    req = f"{tmp_path / 'ComfyUI'}/requirements.txt"
    assert rec.calls == [
        ["uv", "pip", "install", "--python", "D:/ComfyUI/venv/Scripts/python.exe", "-r", req]
    ]


async def test_china_mirror_for_pypi(tmp_path: Path) -> None:
    item = _item({"type": "uv_pip", "env": "tts", "packages": ["indextts"]})
    rec, _ = await _install(item, _env(tmp_path, mirror="cn"))
    assert rec.calls[-1][-2:] == ["--index-url", "https://pypi.tuna.tsinghua.edu.cn/simple"]
    # A step with its own index (PyTorch's CUDA wheels) keeps it.
    torch = _item(
        {"type": "uv_pip", "env": "comfy", "packages": ["torch"], "index_url": "https://x/cu130"}
    )
    rec, _ = await _install(torch, _env(tmp_path, mirror="cn"))
    assert rec.calls[-1][-2:] == ["--index-url", "https://x/cu130"]


@pytest.mark.parametrize("os", ["windows", "macos", "linux"])
async def test_no_python_outside_our_envs(tmp_path: Path, os: OS) -> None:
    """Every manifest item: uv only ever targets ~/.drama-studio/envs (SPEC 12.2-5)."""
    env = _env(tmp_path, os=os)
    rec = Recorder(os)
    outcomes: dict[str, str] = {}
    urls: list[str] = []

    def junk(request: httpx.Request) -> httpx.Response:  # never the real weights
        urls.append(str(request.url))
        return httpx.Response(200, content=b"x")

    weights: list[str] = []
    for item in load_manifest().for_platform(os):
        if not item.can_install:  # the installer never runs them (our nodes, the local LLM)
            continue
        if item.group == "w":
            weights.append(item.id)
        try:
            await _install(item, env, rec, transport=httpx.MockTransport(junk))
            outcomes[item.id] = "ok"
        except InstallError as exc:
            outcomes[item.id] = exc.code
    envs = str(tmp_path / "envs")
    uv = [c for c in rec.calls if c[0] == "uv"]
    assert uv, outcomes
    for call in uv:
        if call[1] == "venv":
            assert call[-1].startswith(envs), call
        elif call[1] == "pip":
            assert call[call.index("--python") + 1].startswith(envs), call
        else:
            assert call[1:3] == ["python", "install"], call  # uv-managed, not the system's
    assert not [c for c in rec.calls if c[0] in ("pip", "pip3", "python", "python3")]
    # Step 8 filled in every installable item: none stops at a TODO.
    assert "manifest_todo" not in outcomes.values(), outcomes
    assert outcomes.get("ffmpeg") == "ok"
    # Weights come from a pinned Hugging Face revision and are checked against their sha256.
    assert weights and all(outcomes[w] == "sha256_mismatch" for w in weights), outcomes
    assert all(re.search(r"/resolve/[0-9a-f]{40}/", u) for u in urls), urls


def _sage(os: OS = "windows") -> Item:
    return next(x for x in load_manifest().for_platform(os) if x.id == "sage")


@pytest.mark.parametrize(
    ("torch", "triton"),
    [
        ("2.12.1+cu130", "triton-windows>=3.7.1,<3.8"),
        ("2.14.1+cu130", "triton-windows>=3.8.0,<3.9"),
    ],
)
async def test_sage_on_windows_follows_the_pytorch_there(
    tmp_path: Path, torch: str, triton: str
) -> None:
    """PyPI's sageattention needs triton, which Windows lacks: a prebuilt wheel plus the
    triton-windows that matches the PyTorch ComfyUI runs on, asked at install time."""
    py = "D:/ComfyUI/venv/Scripts/python.exe"
    env = _env(tmp_path, comfy_python=py)
    rec, _ = await _install(_sage(), env, Recorder(torch=torch))
    assert rec.calls[0] == [py, "-c", "import torch; print(torch.__version__)"]
    pip = rec.calls[-1]
    assert pip[:5] == ["uv", "pip", "install", "--python", py]
    assert pip[5] == triton
    assert pip[6].startswith("sageattention @ https://github.com/woct0rdho/SageAttention/")
    assert "+cu130torch2.10.0andhigher" in pip[6]

    for other in ("2.9.0+cu128", "2.12.1+cu128", "garbage"):
        with pytest.raises(InstallError) as err:
            await _install(_sage(), env, Recorder(torch=other))
        assert err.value.code == "torch_unsupported"
    assert [s.packages for s in _sage("linux").install] == [["sageattention"]]  # type: ignore[attr-defined]


async def test_checked_again_after_installing(tmp_path: Path) -> None:
    """All steps can succeed and leave something that does not work (sageattention without
    triton): what the detector can see at once is asked again."""
    calls: list[str] = []

    async def never(item: Item, env: InstallEnv) -> bool:
        calls.append(item.id)
        return False

    pip = {"type": "uv_pip", "env": "comfy", "packages": ["sageattention"]}
    item = _item(pip).model_copy(
        update={"detect": Detect(type="py_import", env="comfy", module="sageattention")}
    )
    with pytest.raises(InstallError) as err:
        await _install(item, _env(tmp_path), already=never)
    assert err.value.code == "not_detected" and calls == ["x", "x"]  # before and after
    # A package manager's PATH reaches new processes only: no check for commands.
    calls.clear()
    await _install(_item(pip), _env(tmp_path), already=never)
    assert calls == ["x"]


# --------------------------------------------------------------------------- git


async def test_git_clone_then_already_there(tmp_path: Path) -> None:
    env = _env(tmp_path, mirror="cn")
    step = {
        "type": "git_clone",
        "url": "https://github.com/numz/ComfyUI-SeedVR2_VideoUpscaler",
        "ref": "abc123",
        "dest": "{comfy}/custom_nodes/SeedVR2",
    }
    req = {"type": "uv_pip", "env": "comfy", "requirements": "{dest}/requirements.txt"}
    item = _item(step, req)
    dest = f"{tmp_path / 'ComfyUI'}/custom_nodes/SeedVR2"
    rec, _ = await _install(item, env)
    # The China mirror is a proxy prefix in front of the official URL.
    proxied = "https://gh-proxy.com/" + step["url"]
    assert rec.calls[0] == ["git", "clone", "--filter=blob:none", proxied, dest]
    # A pinned commit is a detached HEAD: git's advice about it stays out of the log.
    quiet = ["-c", "advice.detachedHead=false"]
    assert rec.calls[1] == ["git", "-C", dest, *quiet, "checkout", "--force", "abc123"]
    pip = rec.calls[-1]
    assert pip[pip.index("-r") + 1] == f"{dest}/requirements.txt"  # the clone's {dest}

    rec, _ = await _install(_item(step), env, Recorder(head="abc123"))
    assert rec.calls == [["git", "-C", dest, "rev-parse", "HEAD"]]
    rec, _ = await _install(_item(step), env, Recorder(head="0ld"))
    assert rec.calls[1:] == [
        ["git", "-C", dest, "fetch", "--depth", "1", "origin", "abc123"],
        ["git", "-C", dest, *quiet, "checkout", "--force", "FETCH_HEAD"],
    ]


async def test_git_clone_into_a_folder_with_other_files(tmp_path: Path) -> None:
    dest = tmp_path / "ComfyUI" / "custom_nodes" / "VHS"
    dest.mkdir(parents=True)
    (dest / "notes.txt").write_text("mine", encoding="utf-8")
    step = {"type": "git_clone", "url": "https://github.com/a/b", "ref": "r", "dest": str(dest)}
    with pytest.raises(InstallError) as err:
        await _install(_item(step), _env(tmp_path))
    assert err.value.code == "dest_not_empty"


# --------------------------------------------------------------------------- pkg, script, copy


async def test_pkg_per_platform(tmp_path: Path) -> None:
    step = {"type": "pkg", "winget": "Gyan.FFmpeg", "brew": "ffmpeg", "apt": "ffmpeg"}
    rec, _ = await _install(_item(step), _env(tmp_path, os="windows"))
    assert rec.calls[0][:4] == ["winget", "install", "--id", "Gyan.FFmpeg"]
    rec, _ = await _install(_item(step), _env(tmp_path, os="macos"))
    assert rec.calls == [["brew", "install", "ffmpeg"]]
    rec, _ = await _install(_item(step), _env(tmp_path, os="linux"))
    assert rec.calls == [["sudo", "-n", "apt-get", "install", "-y", "ffmpeg"]]
    # winget says it is already installed: fine.
    rec = Recorder(codes={"install": WINGET_ALREADY_INSTALLED})
    await _install(_item(step), _env(tmp_path), rec)
    with pytest.raises(InstallError) as err:
        await _install(_item({"type": "pkg", "brew": "uv"}), _env(tmp_path))
    assert err.value.code == "no_package" and err.value.params == {"manager": "winget"}


async def test_failures_carry_a_code(tmp_path: Path) -> None:
    pkg = _item({"type": "pkg", "winget": "Gyan.FFmpeg"})
    with pytest.raises(InstallError) as err:
        await _install(pkg, _env(tmp_path), Recorder(codes={"install": 1}))
    assert (err.value.code, err.value.params) == ("step_failed", {"step": "pkg", "exit": 1})
    script = _item({"type": "script", "run": "写入本地令牌和后端地址"})
    with pytest.raises(InstallError) as err:
        await _install(script, _env(tmp_path))
    assert err.value.code == "command_not_found"
    todo = _item({"type": "uv_pip", "env": "comfy", "packages": ["torch"], "index_url": "TODO"})
    with pytest.raises(InstallError) as err:
        await _install(todo, _env(tmp_path))
    assert err.value.params == {"field": "uv_pip.index_url"}
    with pytest.raises(InstallError) as err:
        await _install(_item(), _env(tmp_path))
    assert err.value.code == "not_installable"


async def test_script_and_copy(tmp_path: Path) -> None:
    rec, _ = await _install(
        _item({"type": "script", "run": "uv python install 3.12"}), _env(tmp_path)
    )
    assert rec.calls == [["uv", "python", "install", "3.12"]]
    copy = _item({"type": "copy", "from": "config", "dest": "{comfy}/custom_nodes/cfg"})
    for _ in range(2):  # the second copy overwrites in place
        await _install(copy, _env(tmp_path))
    assert (tmp_path / "ComfyUI" / "custom_nodes" / "cfg" / "setup-manifest.yaml").is_file()
    with pytest.raises(InstallError) as err:
        await _install(_item({"type": "copy", "from": "nope", "dest": "x"}), _env(tmp_path))
    assert err.value.code == "source_missing"


async def test_installed_by_hand_since_the_scan(tmp_path: Path) -> None:
    async def yes(item: Item, env: InstallEnv) -> bool:
        return True

    rec, log = await _install(
        _item({"type": "pkg", "winget": "Git.Git"}), _env(tmp_path), already=yes
    )
    assert rec.calls == [] and log.lines == [("info", "already", {"item": "x"})]


# --------------------------------------------------------------------------- download

BLOB = bytes(range(256)) * 4096  # 1 MiB
BLOB_SHA = hashlib.sha256(BLOB).hexdigest()


class Server:
    """A download server that honours Range, or not."""

    def __init__(self, *, ranges: bool = True, status: int = 200, body: bytes = BLOB) -> None:
        self.ranges = ranges
        self.status = status
        self.body = body
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.status != 200:
            return httpx.Response(self.status)
        m = re.fullmatch(r"bytes=(\d+)-(\d*)", request.headers.get("range", ""))
        if m and self.ranges:
            start = int(m.group(1))
            end = int(m.group(2)) if m.group(2) else len(self.body) - 1
            headers = {"content-range": f"bytes {start}-{end}/{len(self.body)}"}
            return httpx.Response(206, content=self.body[start : end + 1], headers=headers)
        return httpx.Response(200, content=self.body)

    def ranges_asked(self) -> list[str]:
        """The Range of each download request, leaving out the size probes."""
        asked = [r.headers.get("range", "") for r in self.requests]
        return [x for x in asked if x != "bytes=0-0"]


def _dl(**kw: Any) -> Item:
    step = {"type": "download", "hf_repo": "MiniMaxAI/MiniMax-H3", "files": "h3.safetensors"}
    return _item({**step, "dest": "{models}/h3", **kw}, group="w")


async def test_download_and_check(tmp_path: Path) -> None:
    server = Server()
    env = _env(tmp_path)
    _, log = await _install(_dl(sha256=BLOB_SHA), env, transport=httpx.MockTransport(server))
    target = tmp_path / "models" / "h3" / "h3.safetensors"
    assert target.read_bytes() == BLOB
    assert not target.with_name("h3.safetensors.part").exists()
    assert not target.with_name("h3.safetensors.part.json").exists()
    assert {str(r.url) for r in server.requests} == {
        "https://huggingface.co/MiniMaxAI/MiniMax-H3/resolve/main/h3.safetensors"
    }
    # By bytes: the size is known before the first byte, and the end is 99 % (done is 100).
    assert log.transfers[0] == Transfer(done=0, total=len(BLOB), speed=None)
    assert log.transfers[-1].done == len(BLOB) and log.pct[-1] == 99
    assert any(t.verifying for t in log.transfers)
    # Already there with the right checksum: no request.
    asked = len(server.requests)
    await _install(_dl(sha256=BLOB_SHA), env, transport=httpx.MockTransport(server))
    assert len(server.requests) == asked


async def test_download_resumes(tmp_path: Path) -> None:
    """A ``.part`` from the old single-connection download: its full blocks count."""
    part = tmp_path / "models" / "h3" / "h3.safetensors.part"
    part.parent.mkdir(parents=True)
    part.write_bytes(BLOB[:350_000])
    server = Server()
    transport = httpx.MockTransport(server)
    _, log = await _install(
        _dl(sha256=BLOB_SHA), _env(tmp_path), transport=transport, block=100_000
    )
    assert server.ranges_asked() == [f"bytes=300000-{len(BLOB) - 1}"]
    assert log.transfers[0].done == 300_000
    assert (tmp_path / "models" / "h3" / "h3.safetensors").read_bytes() == BLOB

    # A server that ignores Range: start over instead of appending.
    part.write_bytes(BLOB[:300_000])
    (tmp_path / "models" / "h3" / "h3.safetensors").unlink()
    await _install(
        _dl(sha256=BLOB_SHA), _env(tmp_path), transport=httpx.MockTransport(Server(ranges=False))
    )
    assert (tmp_path / "models" / "h3" / "h3.safetensors").read_bytes() == BLOB


async def test_download_errors(tmp_path: Path) -> None:
    with pytest.raises(InstallError) as err:
        await _install(
            _dl(sha256="0" * 64), _env(tmp_path), transport=httpx.MockTransport(Server())
        )
    assert (err.value.code, err.value.params) == ("sha256_mismatch", {"file": "h3.safetensors"})
    assert not list((tmp_path / "models" / "h3").iterdir())  # the bad .part is gone
    with pytest.raises(InstallError) as err:
        await _install(_dl(), _env(tmp_path), transport=httpx.MockTransport(Server(status=404)))
    assert err.value.code == "download_failed" and err.value.params["status"] == 404
    with pytest.raises(InstallError) as err:
        await _install(_dl(files="TODO"), _env(tmp_path))
    assert err.value.code == "manifest_todo"


async def test_download_into_comfyui_model_folders(tmp_path: Path) -> None:
    """``folder:`` files go where ComfyUI puts new ones: Desktop's shared models folder (the
    ``is_default`` one), else ComfyUI's own ``models/<folder>``; no ``dest`` needed."""
    shared = tmp_path / "Shared" / "models"
    env = _env(
        tmp_path,
        model_dirs=[
            ModelDir(folder="vae", path=str(shared / "vae"), default=True),
            ModelDir(folder="loras", path=str(tmp_path / "elsewhere" / "loras")),
        ],
    )
    files = [
        {"path": "split_files/vae/v.safetensors", "folder": "vae", "sha256": BLOB_SHA},
        {"path": "loras/l.safetensors", "folder": "loras", "sha256": BLOB_SHA},
    ]
    item = _item(
        {"type": "download", "hf_repo": "o/r", "revision": "a" * 40, "files": files}, group="w"
    )
    assert item.touches_comfy
    server = Server()
    _, log = await _install(item, env, transport=httpx.MockTransport(server))
    assert (shared / "vae" / "v.safetensors").read_bytes() == BLOB
    assert (tmp_path / "ComfyUI" / "models" / "loras" / "l.safetensors").read_bytes() == BLOB
    # The sizes are probed concurrently, so the requests come in either order.
    assert {str(r.url) for r in server.requests} == {
        f"https://huggingface.co/o/r/resolve/{'a' * 40}/split_files/vae/v.safetensors",
        f"https://huggingface.co/o/r/resolve/{'a' * 40}/loras/l.safetensors",
    }
    # Both sizes were asked for first: the total covers both files from the start.
    assert log.transfers[0] == Transfer(done=0, total=2 * len(BLOB), speed=None)
    assert (
        "info",
        "download",
        {"file": "v.safetensors", "path": str(shared / "vae" / "v.safetensors")},
    ) in log.lines


def test_download_files_in_the_manifest() -> None:
    step = Step.model_validate(
        {"type": "download", "url": "https://x/a/b.bin", "sha256": "f" * 64, "dest": "{models}"}
    )
    assert [(f.path, f.sha256) for f in step.download_files()] == [("b.bin", "f" * 64)]
    step = Step.model_validate(
        {"type": "download", "hf_repo": "o/r", "files": ["a", "b"], "sha256": {"b": "e" * 64}}
    )
    assert [(f.path, f.sha256) for f in step.download_files()] == [("a", None), ("b", "e" * 64)]
    assert not _item({**step.model_dump(), "dest": "{models}/x"}, group="w").touches_comfy
    with pytest.raises(ValueError):
        Step.model_validate({"type": "download", "files": [{"path": "a", "folderr": "vae"}]})


@pytest.mark.parametrize(
    ("mirror", "hf_ms", "host"),
    [
        ("official", 2600, "huggingface.co"),
        ("cn", 100, "hf-mirror.com"),
        ("auto", 2600, "hf-mirror.com"),
        ("auto", 300, "huggingface.co"),
        ("auto", None, "hf-mirror.com"),
    ],
)
async def test_mirror_choice(tmp_path: Path, mirror: str, hf_ms: int | None, host: str) -> None:
    server = Server()
    facts = {"hf": {"latency_ms": {"hf": hf_ms}}}
    env = _env(tmp_path, mirror=mirror, facts=facts)
    await _install(_dl(), env, transport=httpx.MockTransport(server))
    assert server.requests[0].url.host == host


@pytest.mark.parametrize(("hf_ms", "host"), [(300, "huggingface.co"), (2600, "hf-mirror.com")])
def test_speed_test_url(hf_ms: int, host: str) -> None:
    """The scan times the first weight file the install would fetch, from the site it would use."""
    items = load_manifest().for_platform("windows")
    url = speed_test_url(items, MIRRORS, {"hf": {"latency_ms": {"hf": hf_ms}}})
    assert url is not None
    assert url.startswith(f"https://{host}/Comfy-Org/MiniMax-H3/resolve/")
    assert url.endswith("/diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors")
    assert (
        speed_test_url([_item({"type": "uv_pip", "env": "x", "packages": ["a"]})], MIRRORS, {})
        is None
    )


# --------------------------------------------------------------------------- word list


@pytest.mark.parametrize("lang", ["zh-CN", "en"])
def test_install_codes_are_in_the_word_list(lang: str) -> None:
    path = REPO_ROOT / "web" / "src" / "locales" / lang / "setup.json"
    words = json.loads(path.read_text(encoding="utf-8"))
    src = REPO_ROOT / "src" / "drama_series_agent" / "setup"
    text = "\n".join(p.read_text(encoding="utf-8") for p in src.glob("*.py"))
    errors = set(re.findall(r'InstallError\(\s*"(\w+)"', text))
    errors |= {"dependency_failed", "dependency_missing", "interrupted", "internal", "no_wheel"}
    errors |= {f"snapshot_{r}" for r in get_args(SnapshotFailure)}  # built from the reason
    assert errors - set(words["error"]) == set()
    logs = set(re.findall(r'_log\(\s*"\w+",\s*"(\w+)"', text))
    logs |= set(re.findall(r'await log\(\s*"\w+",\s*"(\w+)"', text))
    logs |= {"start", "done", "fail", "fail_optional"}
    assert logs and logs - set(words["log"]) == set()
    reasons = {"admin", "large_download", "comfy_change"}
    assert reasons - set(words["confirmReason"]) == set()
