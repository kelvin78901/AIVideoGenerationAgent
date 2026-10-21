"""Capability filtering (SPEC 7.3): routes skip local models this machine cannot run."""

from __future__ import annotations

import pytest

from drama_series_agent.core.capabilities import Capabilities, local_model, unmet
from drama_series_agent.core.config import Override, get_config, resolve
from drama_series_agent.setup.manifest import load_manifest

# Every item a fully set-up 5090 has (the PC sample after installing everything).
PC_READY = Capabilities.of(
    cuda=True,
    found=[
        "os", "gpu", "driver", "python", "uv", "torch", "ffmpeg", "git", "comfy", "node_h3",
        "node_vhs", "node_seedvr2", "node_flashvsr", "node_ctrl", "node_dramastudio", "w_h3",
        "w_te", "w_img", "w_sr", "w_tts", "w_llm", "llmsrv",
    ],
)  # fmt: skip
# The Mac sample after its scan: no CUDA, no ComfyUI, no local LLM server.
MAC = Capabilities.of(cuda=False, found=["os", "gpu", "ram", "disk", "python", "uv", "git"])


def test_every_need_is_a_manifest_item() -> None:
    providers = get_config().providers
    ids = {x.id for x in load_manifest().items}
    local_llms = [m for p in providers.llm_providers if p.where == "local" for m in p.models]
    for model in [*providers.local_models, *local_llms]:
        assert set(model.needs) <= ids, model.key


def test_local_models_and_what_they_lack() -> None:
    providers = get_config().providers
    assert local_model(providers, "comfy/h3") is not None
    assert local_model(providers, "local/qwen3.6-27b") is not None  # a local LLM server model
    assert local_model(providers, "minimax/h3-api") is None
    assert unmet(providers, MAC, "comfy/h3") == ["cuda", "comfy", "node_h3", "w_h3", "w_te"]
    assert unmet(providers, MAC, "minimax/h3-api") == []  # API models always run
    assert unmet(providers, MAC, "local/qwen3-tts") == []  # no needs listed: assumed fine
    assert unmet(providers, PC_READY, "comfy/h3-fun-controlnet") == []


@pytest.mark.parametrize("component", ["vid", "kf", "up"])
def test_mac_sends_video_keyframes_and_upscaling_to_the_api(component: str) -> None:
    before = resolve(component, [])
    after = resolve(component, [], caps=MAC)
    assert before.values["mode"] in ("local", "hybrid")
    assert after.values["mode"] == "api"
    assert after.values["api_model"] == before.values["api_model"]
    assert after.values["local_model"] is None
    assert before.values["local_model"] in after.unavailable
    assert after.sources == before.sources  # still the preset's route, adjusted for the machine


def test_a_ready_5090_keeps_the_local_routes() -> None:
    expected = {"vid": "hybrid", "kf": "hybrid", "up": "local", "ctrl": "local"}
    for component, mode in expected.items():
        res = resolve(component, [], caps=PC_READY)
        assert res.values == resolve(component, []).values, component
        assert res.values["mode"] == mode
        assert res.unavailable == {}


def test_what_else_is_taken_off_the_route() -> None:
    up = resolve("up", [], caps=MAC)
    assert up.values["fallback"]["to"] is None  # FlashVSR needs CUDA too
    assert set(up.unavailable) == {"comfy/seedvr2", "comfy/flashvsr"}

    # ControlNet has no API version: the component is off rather than pointing nowhere.
    ctrl = resolve("ctrl", [], caps=MAC)
    assert ctrl.values["mode"] == "off" and ctrl.values["local_model"] is None

    # A machine without a local LLM server: writing goes to the API, alt_order loses the local.
    no_llm = Capabilities.of(cuda=True, found=PC_READY.found - {"llmsrv"})
    script = resolve("script", [], caps=no_llm)
    assert "local/qwen3.6-27b" in resolve("script", []).values["alt_order"]
    assert "local/qwen3.6-27b" not in script.values["alt_order"]
    assert script.unavailable == {"local/qwen3.6-27b": ["llmsrv"]}
    extract = resolve("extract", [], caps=no_llm)
    assert extract.values["mode"] == "api" and extract.values["api_model"] == "qwen/qwen3.8-flash"


def test_a_hand_picked_local_model_is_dropped_too() -> None:
    picked = [Override("component", None, "vid", {"mode": "local", "local_model": "comfy/wan-2.2"})]
    res = resolve("vid", picked, caps=MAC)
    assert res.values["mode"] == "api" and res.values["local_model"] is None
    assert res.unavailable == {"comfy/wan-2.2": ["cuda", "comfy"]}
    assert res.sources["mode"] == "component"
    # On a machine that has it, the user's choice stands.
    assert resolve("vid", picked, caps=PC_READY).values["local_model"] == "comfy/wan-2.2"


def test_an_api_component_loses_a_local_fallback_it_cannot_run() -> None:
    """台词配音 falls back to IndexTTS: kept where it is installed, dropped on a Mac."""
    assert resolve("dub", []).values["fallback"]["to"] == "local/indextts2"
    on_mac = resolve("dub", [], caps=MAC)
    assert on_mac.values["mode"] == "api" and on_mac.values["fallback"]["to"] is None


def test_components_on_the_api_keep_their_route() -> None:
    for component in ("enrich", "split", "world"):
        before, after = resolve(component, []).values, resolve(component, [], caps=MAC).values
        for key in ("mode", "api_model", "fallback"):
            assert after[key] == before[key], (component, key)
        # 「不满意换一个」 keeps its order, minus the local models this machine cannot run.
        gone = resolve(component, [], caps=MAC).unavailable
        assert after["alt_order"] == [k for k in before["alt_order"] if k not in gone], component
    # The unused local pick is still cleared, so the route only names what can run here.
    assert resolve("enrich", [], caps=MAC).values["local_model"] is None
    assert resolve("world", [], caps=MAC).unavailable == {}
