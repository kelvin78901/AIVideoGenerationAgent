"""Configuration: factory defaults from ``config/*.yaml`` plus user overrides from the database.

Resolution order for a component setting (SPEC 7.1), later layers win:

``factory`` (components.yaml) → ``project`` → ``component`` → ``item`` (a single shot / asset).

Every resolved field carries the layer it came from so the UI can show "来自哪一级".
"""

from __future__ import annotations

import copy
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from drama_series_agent.core.paths import config_dir

Layer = Literal["factory", "project", "component", "item"]
LAYERS: tuple[Layer, ...] = ("factory", "project", "component", "item")


class _Loose(BaseModel):
    """YAML rows carry notes and vendor-specific fields we don't model yet; keep them."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)


# --------------------------------------------------------------------------- providers.yaml


class TokenPrice(_Loose):
    in_: float = Field(alias="in")
    out: float
    currency: str = "USD"


class LlmModel(_Loose):
    key: str
    display: str
    model_id: str | None = None
    price: TokenPrice | None = None
    offpeak: dict[str, Any] | None = None
    json_mode: bool = False
    verify: bool = False


class LlmProvider(_Loose):
    id: str
    name: str
    base_url: str | None = None
    key_name: str | None = None
    where: Literal["local", "api"] = "api"
    docs: str | None = None
    verify: bool = False
    models: list[LlmModel] = Field(default_factory=list)


class MediaModel(_Loose):
    key: str
    kind: str
    display: str
    unit: str | None = None
    currency: str = "USD"
    caps: dict[str, Any] = Field(default_factory=dict)
    verify: bool = False


class LocalModel(_Loose):
    key: str
    kind: str
    display: str
    runtime: str | None = None
    workflow: str | None = None
    verify: bool = False


class ProvidersConfig(_Loose):
    as_of: str | None = None
    currency_rates: dict[str, float] = Field(default_factory=dict)
    llm_providers: list[LlmProvider] = Field(default_factory=list)
    llm_ui_order: list[str] = Field(default_factory=list)
    media_models: list[MediaModel] = Field(default_factory=list)
    local_models: list[LocalModel] = Field(default_factory=list)

    def provider(self, provider_id: str) -> LlmProvider | None:
        return next((p for p in self.llm_providers if p.id == provider_id), None)


# --------------------------------------------------------------------------- components.yaml


class BalancedRoute(_Loose):
    mode: str | None = None
    api: str | None = None
    local: str | None = None
    fallback_to: str | None = None


class ComponentDefault(_Loose):
    id: str
    stage: str
    name: dict[str, str]
    kind: str
    api: list[str] = Field(default_factory=list)
    local: list[str] = Field(default_factory=list)
    balanced: BalancedRoute = Field(default_factory=BalancedRoute)
    alt_order: list[str] | None = None
    cheap_api: str | None = None
    candidates: int | None = None
    gate: str | None = None
    follows_output_spec: bool = False


class FallbackDefaults(_Loose):
    on: list[str] = Field(default_factory=lambda: ["error", "timeout"])
    qa_fail_n: int = 2
    local_timeout_s: int = 600
    notify: str = "after"


class ComponentsConfig(_Loose):
    fallback_defaults: FallbackDefaults = Field(default_factory=FallbackDefaults)
    components: list[ComponentDefault] = Field(default_factory=list)

    def component(self, component_id: str) -> ComponentDefault:
        for comp in self.components:
            if comp.id == component_id:
                return comp
        raise KeyError(f"unknown component: {component_id}")


@dataclass(frozen=True)
class StudioConfig:
    providers: ProvidersConfig
    components: ComponentsConfig


class _Yaml12BoolLoader(yaml.SafeLoader):
    """SafeLoader that only treats true/false as booleans.

    YAML 1.1 turns ``on`` / ``off`` / ``yes`` / ``no`` into booleans, which breaks keys like
    ``fallback.on`` and values like ``mode: off`` in components.yaml.
    """


_Yaml12BoolLoader.yaml_implicit_resolvers = {
    first: [(tag, regexp) for tag, regexp in resolvers if tag != "tag:yaml.org,2002:bool"]
    for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
_Yaml12BoolLoader.add_implicit_resolver(
    "tag:yaml.org,2002:bool",
    re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"),
    list("tTfF"),
)


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        data = yaml.load(fh, Loader=_Yaml12BoolLoader) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a mapping at the top level")
    return data


def load_config(directory: Path | None = None) -> StudioConfig:
    base = directory or config_dir()
    return StudioConfig(
        providers=ProvidersConfig.model_validate(_read_yaml(base / "providers.yaml")),
        components=ComponentsConfig.model_validate(_read_yaml(base / "components.yaml")),
    )


@lru_cache(maxsize=1)
def get_config() -> StudioConfig:
    """Process-wide factory config (tests changing ``DRAMA_CONFIG_DIR`` call cache_clear)."""
    return load_config()


# --------------------------------------------------------------------------- resolution


def factory_settings(comp: ComponentDefault, fallback: FallbackDefaults) -> dict[str, Any]:
    """Per-component defaults derived from the balanced preset (SPEC 7.2, ``presetCfg()``)."""
    bal = comp.balanced
    api_model = bal.api or (comp.api[0] if comp.api else None)
    local_model = bal.local or (comp.local[0] if comp.local else None)
    mode = bal.mode
    if mode is None:
        if api_model and local_model:
            mode = "hybrid"
        else:
            mode = "api" if api_model else "local"
    alt_order = comp.alt_order or [m for m in comp.api if m != api_model]
    return {
        "mode": mode,
        "api_model": api_model,
        "local_model": local_model,
        "fallback": {
            "enabled": bal.fallback_to is not None,
            "on": list(fallback.on),
            "qa_fail_n": fallback.qa_fail_n,
            "to": bal.fallback_to,
            "notify": fallback.notify,
            "local_timeout_s": fallback.local_timeout_s,
        },
        "alt_order": alt_order,
        "per_call_cap_usd": None,
    }


@dataclass(frozen=True)
class Override:
    """One ``config_override`` row, already decoded."""

    scope: Layer
    scope_id: str | None
    component_id: str | None
    data: Mapping[str, Any]


@dataclass(frozen=True)
class Resolved:
    values: dict[str, Any]
    sources: dict[str, Layer]  # dotted field path → layer, e.g. "fallback.to" → "item"


def _flatten(data: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in data.items():
        path = f"{prefix}{key}"
        if isinstance(value, Mapping):
            out.update(_flatten(value, f"{path}."))
        else:
            out[path] = value
    return out


def _set_path(target: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    node = target
    for part in parts[:-1]:
        child = node.get(part)
        if not isinstance(child, dict):
            child = {}
            node[part] = child
        node = child
    node[parts[-1]] = value


def resolve(
    component_id: str,
    overrides: Iterable[Override],
    *,
    item: str | None = None,
    config: StudioConfig | None = None,
) -> Resolved:
    """Merge factory defaults with the overrides that apply to ``component_id`` / ``item``."""
    cfg = config or get_config()
    comp = cfg.components.component(component_id)
    values = copy.deepcopy(factory_settings(comp, cfg.components.fallback_defaults))
    sources: dict[str, Layer] = dict.fromkeys(_flatten(values), "factory")

    def applies(ov: Override) -> bool:
        if ov.component_id not in (None, component_id):
            return False
        if ov.scope == "item":
            return item is not None and ov.scope_id == item
        return ov.scope in ("project", "component")

    ordered = sorted((ov for ov in overrides if applies(ov)), key=lambda ov: LAYERS.index(ov.scope))
    for ov in ordered:
        for path, value in _flatten(ov.data).items():
            _set_path(values, path, value)
            sources[path] = ov.scope
    return Resolved(values=values, sources=sources)
