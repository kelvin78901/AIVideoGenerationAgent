from __future__ import annotations

from pathlib import Path

import pytest

from drama_series_agent.core.config import Defaults, Override, get_config, load_config, resolve
from drama_series_agent.core.paths import REPO_ROOT
from drama_series_agent.modelhub.catalog import model_options


def test_factory_yaml_parses() -> None:
    cfg = load_config(REPO_ROOT / "config")
    ids = [c.id for c in cfg.components.components]
    assert ids[:4] == ["extract", "enrich", "split", "script"]
    assert "vid" in ids
    deepseek = cfg.providers.provider("deepseek")
    assert deepseek is not None
    assert deepseek.key_name == "DEEPSEEK_API_KEY"
    pro = next(m for m in deepseek.models if m.key == "deepseek/v4-pro")
    assert pro.price is not None and pro.price.in_ == pytest.approx(1.32)
    local = cfg.providers.provider("local_llm")
    assert local is not None and local.where == "local"


def test_factory_defaults_follow_balanced_preset() -> None:
    res = resolve("script", [], config=get_config())
    assert res.values["mode"] == "api"
    assert res.values["api_model"] == "deepseek/v4-pro"
    assert res.values["fallback"]["to"] == "qwen/qwen3.8-max"
    assert res.values["alt_order"][0] == "moonshot/kimi-k3.1-pro"
    assert res.sources["api_model"] == "preset"


def test_hybrid_when_both_sides_exist() -> None:
    res = resolve("img", [])
    assert res.values["mode"] == "hybrid"
    assert res.values["local_model"] == "comfy/qwen-image"


def test_layers_apply_in_order_and_report_source() -> None:
    overrides = [
        # stored out of order on purpose
        Override("item", "shot:1-05", "script", {"api_model": "item/model"}),
        Override("project", None, None, {"per_call_cap_usd": 0.5, "fallback": {"notify": "ask"}}),
        Override("component", None, "script", {"api_model": "comp/model", "mode": "hybrid"}),
        Override("component", None, "vid", {"mode": "local"}),  # other component: ignored
    ]
    plain = resolve("script", overrides)
    assert plain.values["api_model"] == "comp/model"
    assert plain.sources["api_model"] == "component"
    assert plain.values["mode"] == "hybrid"
    assert plain.values["per_call_cap_usd"] == 0.5
    assert plain.sources["per_call_cap_usd"] == "project"
    # nested merge keeps sibling preset values
    assert plain.values["fallback"]["notify"] == "ask"
    assert plain.sources["fallback.notify"] == "project"
    assert plain.values["fallback"]["to"] == "qwen/qwen3.8-max"
    assert plain.sources["fallback.to"] == "preset"

    shot = resolve("script", overrides, item="shot:1-05")
    assert shot.values["api_model"] == "item/model"
    assert shot.sources["api_model"] == "item"
    other_shot = resolve("script", overrides, item="shot:1-06")
    assert other_shot.values["api_model"] == "comp/model"


def test_unknown_component_raises() -> None:
    with pytest.raises(KeyError):
        resolve("nope", [])


def test_config_dir_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "providers.yaml").write_text("llm_providers: []\n", encoding="utf-8")
    (tmp_path / "components.yaml").write_text(
        "components:\n  - {id: x, stage: s, name: {zh: 甲, en: X}, kind: llm, api: [a/b]}\n",
        encoding="utf-8",
    )
    (tmp_path / "spec.yaml").write_text("platforms: []\n", encoding="utf-8")
    monkeypatch.setenv("DRAMA_CONFIG_DIR", str(tmp_path))
    get_config.cache_clear()
    try:
        cfg = get_config()
        assert [c.id for c in cfg.components.components] == ["x"]
        assert resolve("x", [], config=cfg).values["mode"] == "api"
    finally:
        get_config.cache_clear()


def test_presets() -> None:
    """SPEC 7.2: the four presets as the prototype's presetCfg() computes them."""
    quality = resolve("enrich", [], defaults=Defaults(preset="quality")).values
    assert (quality["mode"], quality["api_model"]) == ("api", "deepseek/v4-pro")
    assert quality["fallback"]["to"] == "local/qwen3.6-27b" and quality["fallback"]["enabled"]
    assert quality["alt_order"][0] == "local/qwen3.6-27b"

    cheap = resolve("enrich", [], defaults=Defaults(preset="cheap")).values
    assert (cheap["mode"], cheap["local_model"]) == ("local", "local/qwen3.6-27b")
    assert cheap["fallback"]["to"] == "deepseek/v4.1-flash"

    local = resolve("enrich", [], defaults=Defaults(preset="local")).values
    assert local["mode"] == "local" and not local["fallback"]["enabled"]
    assert local["alt_order"] == ["local/qwen3-30b-a3b"]
    assert resolve("world", [], defaults=Defaults(preset="local")).values["mode"] == "off"

    balanced = resolve("extract", []).values
    assert (balanced["mode"], balanced["local_model"]) == ("local", "local/qwen3.6-27b")
    assert balanced["alt_order"][0] == "qwen/qwen3.8-flash"  # the fallback target first

    asked = resolve("enrich", [], defaults=Defaults(fallback_notify="ask")).values
    assert asked["fallback"]["notify"] == "ask"
    assert asked["fallback"]["timeout_s"] == 600


def test_per_call_caps() -> None:
    assert resolve("extract", []).values["per_call_cap_usd"] == 0.2
    assert resolve("dub", []).values["per_call_cap_usd"] == 0.5  # components.yaml default
    assert resolve("ctrl", []).values["per_call_cap_usd"] is None  # local only: nothing to pay


def test_component_models_are_all_known() -> None:
    """Every model a component lists exists in providers.yaml (except the custom placeholder)."""
    cfg = get_config()
    known = {m.key for m in model_options(cfg)}
    for comp in cfg.components.components:
        refs = {*comp.api, *comp.local, *(comp.alt_order or [])}
        refs |= {k for k in (comp.balanced.api, comp.balanced.local, comp.cheap_api) if k}
        refs |= {comp.balanced.fallback_to} if comp.balanced.fallback_to else set()
        assert refs - known <= {"custom"}, comp.id
