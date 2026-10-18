from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import httpx
import pytest

from drama_series_agent.core import secrets
from drama_series_agent.core.paths import REPO_ROOT
from drama_series_agent.setup.detectors import (
    ScanContext,
    detect_item,
    meets,
    short_version,
    size_text,
)
from drama_series_agent.setup.manifest import Manifest, load_manifest
from drama_series_agent.setup.pathutil import dirname, is_absolute, join
from drama_series_agent.setup.probe import FakeProbe, RealProbe

ENVS = {"pc": "C:/Users/kelvin/.drama-studio/envs", "mac": "/Users/demo/.drama-studio/envs"}
Row = tuple[str, str, dict[str, Any], str | None, dict[str, Any] | None]


async def _scan(
    probe: FakeProbe, envs: str, manifest: Manifest | None = None, **kw: Any
) -> dict[str, Any]:
    m = manifest or load_manifest()
    items = m.for_platform((await probe.host()).os)
    ctx = await ScanContext.create(probe, items, mirrors=m.mirrors, envs=envs, **kw)
    return {x.id: (x, await detect_item(x, ctx)) for x in items}


async def scan(machine: str, probe: FakeProbe | None = None, **kw: Any) -> dict[str, Any]:
    return await _scan(probe or FakeProbe.load(machine), ENVS[machine], **kw)


def rows(result: dict[str, Any]) -> dict[str, Row]:
    out: dict[str, Row] = {}
    for item_id, (_, d) in result.items():
        fix = d.fix.public() if d.fix else None
        out[item_id] = (
            d.status,
            d.found.code,
            d.found.params,
            fix["code"] if fix else None,
            fix["params"] if fix else None,
        )
    return out


def counts(result: dict[str, Any]) -> Counter[str]:
    return Counter(d.status for _, d in result.values())


def _r(status: str, found: str, fix: str | None = None, **params: Any) -> Row:
    """Row with params split by prefix: ``f_<name>`` for found, ``x_<name>`` for fix."""
    fp = {k[2:]: v for k, v in params.items() if k.startswith("f_")}
    xp = {k[2:]: v for k, v in params.items() if k.startswith("x_")}
    return (status, found, fp, fix, xp if fix else None)


# Codes match web/src/mocks/fixtures/demo/setup.ts for the items both have; the rest are the
# manifest items the prototype left out (uv, node_dramastudio, eagle, resolve).
PC: dict[str, Row] = {
    "os": _r("ok", "os", f_name="Windows 11", f_bits=64),
    "gpu": _r("ok", "gpu_vram", f_name="NVIDIA RTX 5090", f_gb=32),
    "driver": _r("ok", "driver_cuda", f_cuda="13"),
    "ram": _r("ok", "ram", f_gb=64),
    "disk": _r("ok", "disk_free_on", f_drive="D:", f_free="1.2 TB"),
    "python": _r("ok", "version", f_version="3.12"),
    "uv": _r("ok", "installed"),
    "torch": _r("old", "torch_not_cuda", "torch_cuda", f_cuda="13", x_cuda="13.0"),
    "ffmpeg": _r("missing", "not_found", "install_named", x_name="FFmpeg"),
    "git": _r("ok", "installed"),
    "comfy": _r("old", "outdated", "update_latest"),
    "comfy_manager": _r("ok", "version", f_version="4.2.2"),
    "node_h3": _r("missing", "not_found", "install_nodes"),
    "node_vhs": _r("ok", "installed"),
    "node_seedvr2": _r("missing", "not_found", "install_nodes"),
    "node_flashvsr": _r("optional", "not_found", "install_nodes"),
    "node_ctrl": _r("optional", "not_found", "ctrl_later"),
    "sage": _r("optional", "not_found", "sage_build"),
    "node_dramastudio": _r("missing", "not_found", "install_nodes"),
    "w_h3": _r("missing", "not_found", "download"),
    "w_te": _r("missing", "not_found", "download"),
    "w_img": _r("missing", "not_found", "download"),
    "w_sr": _r("missing", "not_found", "download"),
    "w_tts": _r("missing", "not_found", "download"),
    "w_llm": _r("optional", "not_found", "llm_optional"),
    "hf": _r("warn", "hf_slow", "pick_mirror"),
    "llmsrv": _r("optional", "not_found", "install_llm_server"),
    "keys": _r("optional", "no_keys", "keys_later"),
    "eagle": _r("optional", "not_running", "eagle_later"),
    "resolve": _r("optional", "not_found", "resolve_later"),
}

MAC: dict[str, Row] = {
    "os": _r("ok", "os_apple", f_name="macOS"),
    "gpu": _r("warn", "gpu_unified", "no_cuda_video_api", f_name="Apple M4 Pro"),
    "ram": _r("ok", "ram_unified", f_gb=48),
    "disk": _r("ok", "disk_free", f_free="600 GB"),
    "python": _r("ok", "version", f_version="3.12"),
    "uv": _r("ok", "installed"),
    "torch": _r("missing", "not_found", "install_torch_mps"),
    "ffmpeg": _r("missing", "not_found", "install_named", x_name="FFmpeg"),
    "git": _r("ok", "installed"),
    "comfy": _r("optional", "not_found", "comfy_images_only"),
    "comfy_manager": _r("optional", "not_found", "install_nodes"),
    "node_h3": _r("skip", "needs_cuda", "unsupported_skip"),
    "node_vhs": _r("optional", "not_found", "install_nodes"),
    "node_seedvr2": _r("skip", "needs_cuda", "unsupported_upscale_api"),
    "node_flashvsr": _r("skip", "needs_cuda", "unsupported_upscale_api"),
    "node_ctrl": _r("skip", "needs_cuda", "unsupported_skip"),
    "sage": _r("skip", "needs_cuda", "unsupported_skip"),
    "node_dramastudio": _r("optional", "not_found", "install_nodes"),
    "w_h3": _r("skip", "needs_cuda", "unsupported_skip"),
    "w_te": _r("skip", "needs_cuda", "unsupported_skip"),
    "w_img": _r("optional", "not_found", "mac_image_slow"),
    "w_sr": _r("skip", "needs_cuda", "unsupported_upscale_api"),
    "w_tts": _r("optional", "not_found", "mac_voice_slow"),
    "w_llm": _r("missing", "not_found", "download_local_writing"),
    "hf": _r("warn", "hf_slow", "pick_mirror"),
    "llmsrv": _r("missing", "not_found", "install_ollama_mlx"),
    "keys": _r("warn", "no_keys", "keys_video_api"),
    "eagle": _r("optional", "not_running", "eagle_later"),
    "resolve": _r("optional", "not_found", "resolve_later"),
}


# --------------------------------------------------------------------------- sample machines


async def test_pc_scan() -> None:
    result = await scan("pc")
    assert rows(result) == PC
    assert counts(result) == {"ok": 10, "missing": 9, "old": 2, "optional": 8, "warn": 1}


async def test_pc_flags_match_the_prototype() -> None:
    result = await scan("pc")
    picked = {i for i, (_, d) in result.items() if d.installable}
    for item_id in ("torch", "ffmpeg", "comfy", "node_h3", "node_seedvr2", "w_h3", "w_tts"):
        assert result[item_id][0].required and result[item_id][1].installable, item_id
    for item_id in ("node_flashvsr", "node_ctrl", "sage", "w_llm", "llmsrv"):
        assert not result[item_id][0].required and result[item_id][1].installable, item_id
    for item_id in ("hf", "keys", "eagle", "resolve", "os", "git"):
        assert item_id not in picked, item_id


async def test_pc_facts() -> None:
    result = await scan("pc")
    comfy = result["comfy"][1]
    assert comfy.version == "0.3.40"
    assert comfy.facts["root"] == "D:\\ComfyUI"
    assert comfy.facts["url"] == "http://127.0.0.1:8188"
    assert comfy.facts["python"] == "D:\\ComfyUI\\venv\\Scripts\\python.exe"
    assert result["torch"][1].facts["cuda"] == "12.8"
    assert result["hf"][1].facts["latency_ms"] == {"hf": 2600, "pypi": 180, "github": 240}
    assert result["disk"][1].facts == {"path": "D:\\DramaStudio", "free_gb": 1228.8}


async def test_mac_scan() -> None:
    result = await scan("mac")
    assert rows(result) == MAC
    assert counts(result) == {"ok": 6, "warn": 3, "missing": 4, "optional": 8, "skip": 8}
    assert "driver" not in result
    assert result["w_llm"][0].name.en == "Qwen3.6-27B (MLX)"
    assert result["w_llm"][1].installable


async def test_mac_skips_everything_that_needs_cuda() -> None:
    result = await scan("mac")
    skipped = {i for i, (x, d) in result.items() if d.status == "skip"}
    assert skipped == {i for i, (x, _) in result.items() if x.requires_cuda}
    assert all(not result[i][1].installable for i in skipped)


async def test_rescan_after_install() -> None:
    probe = FakeProbe.load("pc")
    probe.add_files(
        "D:/ComfyUI/custom_nodes/ComfyUI-SeedVR2_VideoUpscaler",
        "D:/ComfyUI/custom_nodes/comfyui-dramastudio/__init__.py",
    )
    probe.data["commands"]["ffmpeg -version"] = "ffmpeg version 8.0-full_build"
    probe.python["D:/ComfyUI/venv/Scripts/python.exe"]["sageattention"] = {"version": "2.2.0"}
    probe.python["D:/ComfyUI/venv/Scripts/python.exe"]["torch"]["cuda"] = "13.0"
    result = rows(await scan("pc", probe))
    for item_id in ("node_seedvr2", "node_dramastudio", "ffmpeg", "torch"):
        assert result[item_id][0] == "ok", item_id
    assert result["sage"][:3] == ("ok", "version", {"version": "2.2.0"})


# --------------------------------------------------------------------------- ComfyUI


def _pc(**changes: Any) -> FakeProbe:
    probe = FakeProbe.load("pc")
    probe.data.update(changes)
    return probe


async def test_comfy_relative_argv_falls_back_to_folders() -> None:
    probe = _pc()
    stats = probe.data["http"]["http://127.0.0.1:8188/system_stats"]
    stats["body"]["system"]["argv"] = ["main.py", "--listen"]
    result = await scan("pc", probe)
    assert result["comfy"][1].facts["root"] == "D:/ComfyUI"
    assert result["comfy"][1].version == "0.3.40"  # still from the running server


async def test_comfy_not_running_reads_version_file() -> None:
    probe = _pc()
    del probe.data["http"]["http://127.0.0.1:8188/system_stats"]
    probe.texts["D:/ComfyUI/comfyui_version.py"] = '__version__ = "0.4.2"\n'
    result = await scan("pc", probe)
    comfy = result["comfy"][1]
    assert (comfy.status, comfy.version, comfy.facts["url"]) == ("ok", "0.4.2", None)
    assert rows(result)["comfy"] == _r("ok", "version", f_version="0.4.2")


async def test_comfy_portable_build_and_its_python() -> None:
    probe = FakeProbe(
        {
            **FakeProbe.load("pc").data,
            "http": {},
            "files": [
                "E:/ComfyUI_windows_portable/ComfyUI/main.py",
                "E:/ComfyUI_windows_portable/python_embeded/python.exe",
            ],
            "python": {
                "E:/ComfyUI_windows_portable/python_embeded/python.exe": {
                    "torch": {"version": "2.9.0+cu130", "cuda": "13.0"}
                }
            },
        }
    )
    result = await scan("pc", probe)
    assert result["comfy"][1].facts["python"] == (
        "E:/ComfyUI_windows_portable/python_embeded/python.exe"
    )
    assert result["torch"][1].status == "ok"


async def test_comfy_from_setting_path() -> None:
    probe = FakeProbe(
        {**FakeProbe.load("pc").data, "http": {}, "files": ["G:/Tools/Comfy/main.py"]}
    )
    assert (await scan("pc", probe))["comfy"][1].status == "missing"
    result = await scan("pc", probe, comfy_setting="G:/Tools/Comfy")
    assert result["comfy"][1].facts["root"] == "G:/Tools/Comfy"


async def test_comfy_where_we_install_it() -> None:
    probe = FakeProbe(
        {
            **FakeProbe.load("pc").data,
            "http": {},
            "files": [
                "C:/Users/kelvin/.drama-studio/ComfyUI/main.py",
                "C:/Users/kelvin/.drama-studio/envs/comfy/Scripts/python.exe",
            ],
        }
    )
    comfy = (await scan("pc", probe))["comfy"][1]
    assert comfy.facts["root"] == "C:/Users/kelvin/.drama-studio/ComfyUI"
    assert comfy.facts["python"] == "C:/Users/kelvin/.drama-studio/envs/comfy/Scripts/python.exe"


async def test_torch_in_our_env_before_comfy_is_installed() -> None:
    probe = FakeProbe.load("mac")
    py = "/Users/demo/.drama-studio/envs/comfy/bin/python"
    probe.add_files(py)
    probe.python[py] = {"torch": {"version": "2.9.0", "cuda": None}}
    result = await scan("mac", probe)
    assert result["torch"][1].status == "ok"  # MPS build: the CUDA check does not apply
    assert result["comfy"][1].status == "optional"


async def test_node_detected_by_classes() -> None:
    m = load_manifest()
    data = m.model_dump()
    for x in data["items"]:
        if x["id"] == "node_h3":
            x["detect"]["classes"] = ["MiniMaxH3Loader", "MiniMaxH3Sampler"]
    manifest = Manifest.model_validate(data)
    probe = FakeProbe.load("pc")
    info = probe.data["http"]["http://127.0.0.1:8188/object_info"]["body"]
    info["MiniMaxH3Loader"] = {}
    assert rows(await _scan(probe, ENVS["pc"], manifest))["node_h3"][0] == "missing"
    info["MiniMaxH3Sampler"] = {}
    probe2 = FakeProbe(probe.data)
    assert rows(await _scan(probe2, ENVS["pc"], manifest))["node_h3"][0] == "ok"


# --------------------------------------------------------------------------- other detectors


async def test_no_gpu_on_windows() -> None:
    result = rows(await scan("pc", _pc(gpu=None)))
    assert result["gpu"] == _r("warn", "no_gpu", "no_cuda_video_api")
    assert result["driver"] == _r("skip", "no_gpu")
    assert result["node_h3"][:2] == ("skip", "needs_cuda")


async def test_old_driver() -> None:
    gpu = {**FakeProbe.load("pc").data["gpu"], "cuda_driver": "12.8"}
    result = rows(await scan("pc", _pc(gpu=gpu)))
    assert result["driver"] == _r("old", "driver_cuda", "update_driver", f_cuda="12.8", x_cuda="13")


async def test_low_disk() -> None:
    result = rows(await scan("pc", _pc(disks={"D:": 120})))
    assert result["disk"] == _r(
        "warn", "disk_free_on", "disk_low", f_drive="D:", f_free="120 GB", x_gb=200
    )


async def test_disk_unknown() -> None:
    assert rows(await scan("pc", _pc(disks={})))["disk"] == _r("warn", "check_failed")


async def test_models_folder_is_the_users_choice() -> None:
    result = rows(await scan("pc", models="C:/Models"))
    assert result["disk"][2] == {"drive": "C:", "free": "182 GB"}


async def test_keys_set() -> None:
    result = rows(await scan("pc", _pc(secrets=["DEEPSEEK_API_KEY", "GEMINI_API_KEY"])))
    assert result["keys"] == _r("ok", "keys_set", f_count=2)


async def test_slow_site_other_than_hf() -> None:
    probe = _pc()
    probe.data["http"]["https://huggingface.co"] = {"ms": 300}
    del probe.data["http"]["https://github.com"]
    result = await scan("pc", probe)
    assert rows(result)["hf"] == _r("warn", "site_slow", "pick_mirror", f_site="GitHub")
    assert result["hf"][1].facts["latency_ms"]["github"] is None


async def test_network_fine() -> None:
    probe = _pc()
    probe.data["http"]["https://huggingface.co"] = {"ms": 300}
    assert rows(await scan("pc", probe))["hf"] == _r("ok", "reachable")


async def test_services_running() -> None:
    probe = _pc()
    probe.data["http"].update(
        {
            "http://127.0.0.1:8080/v1/models": {"body": {"data": [{"id": "qwen3.6-27b"}]}},
            "http://localhost:41595/api/application/info": {"body": {"status": "success"}},
        }
    )
    probe.data["resolve"] = {"version": "21.1.2", "edition": "studio"}
    result = rows(await scan("pc", probe))
    assert result["llmsrv"] == _r("ok", "running")
    assert result["eagle"] == _r("ok", "running")
    assert result["resolve"] == _r("ok", "resolve_studio", f_version="21.1.2")


async def test_local_llm_model_on_the_server() -> None:
    data = load_manifest().model_dump()
    for x in data["items"]:
        if x["id"] == "w_llm":
            x["detect"]["model"] = "qwen3.6-27b"
    manifest = Manifest.model_validate(data)
    probe = _pc()
    url = "http://127.0.0.1:11434/v1/models"
    probe.data["http"][url] = {"body": {"data": [{"id": "llama4"}]}}
    assert rows(await _scan(probe, ENVS["pc"], manifest))["w_llm"][0] == "optional"
    probe.data["http"][url] = {"body": {"data": [{"id": "qwen3.6-27b"}]}}
    assert rows(await _scan(probe, ENVS["pc"], manifest))["w_llm"][0] == "ok"


async def test_a_failing_detector_is_a_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    probe = FakeProbe.load("pc")

    async def broken(cmd: str) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(probe, "run", broken)
    result = rows(await scan("pc", probe))
    assert result["git"] == _r("warn", "check_failed")
    assert result["os"][0] == "ok"  # the other detectors carry on


async def test_file_detector() -> None:
    m = Manifest.model_validate(
        {
            "items": [
                {
                    "id": "w",
                    "group": "w",
                    "name": {"zh": "w", "en": "w"},
                    "required": True,
                    "detect": {"type": "file", "path": "{models}/h3/model.safetensors"},
                    "install": [{"type": "download"}],
                }
            ]
        }
    )
    probe = FakeProbe.load("pc")
    assert rows(await _scan(probe, ENVS["pc"], m))["w"] == _r("missing", "not_found", "download")
    probe.add_files("D:/DramaStudio/h3/model.safetensors")
    assert rows(await _scan(probe, ENVS["pc"], m))["w"] == _r("ok", "installed")


# --------------------------------------------------------------------------- helpers


@pytest.mark.parametrize(
    ("have", "spec", "ok"),
    [
        ("13.0", ">=13.0", True),
        ("12.8", ">=13.0", False),
        ("13", ">=13.0", True),
        ("0.3.40", ">=0.4.0", False),
        ("0.4.10", ">=0.4.2", True),
        ("2.7.1+cu128", "==2.7.1", True),
        ("3.12", "<3.13", True),
        (None, ">=1", None),
        ("1.0", "latest", None),
    ],
)
def test_meets(have: str | None, spec: str, ok: bool | None) -> None:
    assert meets(have, spec) is ok


def test_path_helpers() -> None:
    assert join("D:\\ComfyUI\\", "custom_nodes", "/x/") == "D:\\ComfyUI\\custom_nodes\\x"
    assert join("C:/Users/kelvin", "ComfyUI") == "C:/Users/kelvin/ComfyUI"
    assert dirname("D:\\ComfyUI\\main.py") == "D:\\ComfyUI"
    assert dirname("/opt/comfy/main.py") == "/opt/comfy"
    assert is_absolute("D:\\x") and is_absolute("/x") and is_absolute("~/x")
    assert not is_absolute("ComfyUI\\main.py")
    assert short_version("13.0") == "13" and short_version("12.8") == "12.8"
    assert size_text(1228.8) == "1.2 TB" and size_text(600) == "600 GB"


async def test_fake_probe_paths_ignore_slash_style() -> None:
    probe = FakeProbe({"files": ["D:\\ComfyUI\\main.py"]})
    assert await probe.exists("D:/ComfyUI/main.py")
    assert await probe.exists("D:/ComfyUI")
    assert not await probe.exists("D:/Comfy")


# --------------------------------------------------------------------------- real probe


async def test_real_probe_reads_files(tmp_path: Path) -> None:
    probe = RealProbe()
    f = tmp_path / "comfyui_version.py"
    f.write_text('__version__ = "0.4.2"\n', encoding="utf-8")
    assert await probe.exists(str(f))
    assert not await probe.exists(str(tmp_path / "nope"))
    assert await probe.read_text(str(f)) == '__version__ = "0.4.2"\n'
    assert await probe.read_text(str(tmp_path / "nope")) is None
    disk = await probe.disk(str(tmp_path / "not" / "yet"))
    assert disk is not None and disk.free_gb > 0


async def test_real_probe_commands() -> None:
    probe = RealProbe()
    assert await probe.run("definitely-not-a-command-xyz --version") is None
    mod = await probe.py_module(sys.executable, "json")
    assert mod is not None and mod.version
    assert await probe.py_module(sys.executable, "no_such_module_xyz") is None


async def test_real_probe_http() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json={"system": {"comfyui_version": "0.4.2"}})

    probe = RealProbe(transport=httpx.MockTransport(handler))
    res = await probe.http_get("http://127.0.0.1:8188/system_stats")
    assert res is not None and res.status == 200
    assert res.body["system"]["comfyui_version"] == "0.4.2"
    assert seen == ["http://127.0.0.1:8188/system_stats"]


async def test_real_probe_http_unreachable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    probe = RealProbe(transport=httpx.MockTransport(handler))
    assert await probe.http_get("http://127.0.0.1:1/") is None


async def test_real_probe_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DRAMA_TEST_PROBE_KEY", raising=False)
    probe = RealProbe()
    assert not await probe.has_secret("DRAMA_TEST_PROBE_KEY")
    secrets.set_secret("DRAMA_TEST_PROBE_KEY", "sk-test-123")
    assert await probe.has_secret("DRAMA_TEST_PROBE_KEY")


# --------------------------------------------------------------------------- word list


def _setup_words(lang: str) -> dict[str, Any]:
    path = REPO_ROOT / "web" / "src" / "locales" / lang / "setup.json"
    with path.open(encoding="utf-8") as fh:
        words: dict[str, Any] = json.load(fh)
    return words


@pytest.mark.parametrize("lang", ["zh-CN", "en"])
def test_every_code_is_in_the_word_list(lang: str) -> None:
    words = _setup_words(lang)
    fixes: set[str] = set()
    for x in load_manifest().items:
        overrides = [o for o in (x.windows, x.macos, x.linux) if o and o.fix]
        for fix_map in [x.fix, *(o.fix for o in overrides if o.fix)]:
            fixes |= {m.code for m in fix_map.values() if m}
    assert fixes - set(words["fix"]) == set()
    # Codes the detectors emit themselves, found or fix.
    source = (REPO_ROOT / "src/drama_series_agent/setup/detectors.py").read_text(encoding="utf-8")
    emitted = set(re.findall(r'msg\(\s*"(\w+)"', source)) | {"resolve_free", "resolve_studio"}
    assert emitted - set(words["found"]) - set(words["fix"]) == set()
    # And every row of the two sample machines.
    for row in [*PC.values(), *MAC.values()]:
        assert row[1] in words["found"], row
        assert row[3] is None or row[3] in words["fix"], row
