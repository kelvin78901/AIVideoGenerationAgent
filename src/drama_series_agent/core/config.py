"""Configuration: factory defaults from ``config/*.yaml`` plus user overrides from the database.

Resolution order for a component setting (SPEC 7.1), later layers win:

``preset`` (components.yaml under the active preset, SPEC 7.2) → ``project`` → ``component`` →
``item`` (a single shot / asset).

Every resolved field carries the layer it came from so the UI can show "来自哪一级".
"""

from __future__ import annotations

import copy
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from drama_series_agent.core.capabilities import Capabilities, restrict
from drama_series_agent.core.paths import config_dir

Layer = Literal["preset", "project", "component", "item"]
LAYERS: tuple[Layer, ...] = ("preset", "project", "component", "item")
PresetId = Literal["quality", "balanced", "cheap", "local"]
PRESETS: tuple[PresetId, ...] = ("quality", "balanced", "cheap", "local")
# The top-level fields of a component's settings; the UI shows one source per field.
CONFIG_FIELDS = ("mode", "api_model", "local_model", "fallback", "alt_order", "per_call_cap_usd")


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
    # Context window in tokens; None = unknown (long inputs are chunked as if it were 32k).
    max_context: int | None = None
    # Extra request-body fields sent with every call (e.g. DeepSeek's ``thinking``); they never
    # replace what the adapter sets itself (model, messages, max_tokens, ...).
    request: dict[str, Any] = Field(default_factory=dict)
    # Local models only (core/capabilities.py): setup-manifest item ids it needs, and CUDA.
    needs: list[str] = Field(default_factory=list)
    requires_cuda: bool = False


class LlmProvider(_Loose):
    id: str
    name: str
    base_url: str | None = None
    key_name: str | None = None
    where: Literal["local", "api"] = "api"
    docs: str | None = None
    verify: bool = False
    # Ask the server for a context of ``max_context`` (``options.num_ctx``, Ollama): its
    # default can be as small as 2–4k and silently cuts long prompts.
    send_num_ctx: bool = False
    models: list[LlmModel] = Field(default_factory=list)


class MediaModel(_Loose):
    key: str
    kind: str
    display: str
    # The ``llm_providers`` account whose key it uses (one MiniMax / Google / OpenAI key for
    # writing, pictures and voices); its base URL too unless ``base_url`` says otherwise.
    account: str | None = None
    # Which real adapter runs it (``modelhub/media_adapters.py``); none yet → unavailable.
    adapter: str | None = None
    model_id: str | None = None
    base_url: str | None = None
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
    # ``runtime: python``: the worker script (``workers/<worker>.py``), the environment it runs in
    # (``~/.drama-studio/envs/<env>``), what it loads (``args``, ``{models}`` / ``{envs}``
    # expanded) and whether it needs the GPU (the VRAM lease; RapidOCR does not).
    worker: str | None = None
    env: str | None = None
    args: dict[str, Any] = Field(default_factory=dict)
    gpu: bool = True
    caps: dict[str, Any] = Field(default_factory=dict)
    verify: bool = False
    # What this machine must have to run it (core/capabilities.py): setup-manifest item ids.
    needs: list[str] = Field(default_factory=list)
    requires_cuda: bool = False


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
    per_call_cap_usd: float | None = None  # 单次花费上限; default: ComponentsConfig's
    candidates: int | None = None
    gate: str | None = None
    follows_output_spec: bool = False
    # Asset kind → the aspect its reference pictures are drawn at, whatever the output spec
    # (img: scenes 16:9, Kelvin 2026-10-26); a kind not listed follows the spec.
    aspects: dict[str, str] = Field(default_factory=dict)


class FallbackDefaults(_Loose):
    on: list[str] = Field(default_factory=lambda: ["error", "timeout"])
    qa_fail_n: int = 2
    local_timeout_s: int = 600
    notify: str = "after"


class DialogueAudio(_Loose):
    """How voice samples and dubbed lines are levelled (``media/audio.py``)."""

    lufs: float = -18.0
    peak_dbtp: float = -1.5
    trim_db: float = -45.0
    sample_rate: int = 48000
    tail_s: float = 0.3


class AudioDefaults(_Loose):
    dialogue: DialogueAudio = Field(default_factory=DialogueAudio)


class ConfirmMargin(_Loose):
    """How far past a confirmed amount a job may spend: the larger of ``ratio`` of it and
    ``min_usd`` (Kelvin 2026-10-21)."""

    ratio: float = 0.10
    min_usd: float = 0.05

    def allowance(self, confirmed_usd: float) -> float:
        return confirmed_usd + max(confirmed_usd * self.ratio, self.min_usd)


class ComponentsConfig(_Loose):
    fallback_defaults: FallbackDefaults = Field(default_factory=FallbackDefaults)
    audio: AudioDefaults = Field(default_factory=AudioDefaults)
    per_call_cap_usd: float | None = 0.5  # hard rule 6: a run above this waits for a yes
    confirm_margin: ConfirmMargin = Field(default_factory=ConfirmMargin)
    components: list[ComponentDefault] = Field(default_factory=list)

    def component(self, component_id: str) -> ComponentDefault:
        for comp in self.components:
            if comp.id == component_id:
                return comp
        raise KeyError(f"unknown component: {component_id}")


# --------------------------------------------------------------------------- spec.yaml


class PlatformPreset(_Loose):
    id: str
    aspect: str | None = None
    delivery: str | None = None


class SafeArea(_Loose):
    zones: list[dict[str, Any]] = Field(default_factory=list)
    subtitle: dict[str, float] = Field(default_factory=dict)


class CompatStage(_Loose):
    """One row of the compatibility table (SPEC 13.3): which route model(s) make this stage."""

    stage: str
    component: str
    pick: list[Literal["api_model", "local_model", "fallback", "alt"]]
    tier: Literal["draft", "delivery"] = "delivery"
    native: str = "native"  # spec:compat.how.<code> when every picked model is native


class SpecConfig(_Loose):
    """Output-spec presets (SPEC 13.1). Sizes are not here: only ``spec/dims.py`` computes them."""

    platforms: list[PlatformPreset] = Field(default_factory=list)
    defaults: dict[str, Any] = Field(default_factory=dict)
    # episode_len → [shortest, longest] seconds (分集规划 cuts by it)
    episode_lengths: dict[str, list[int]] = Field(default_factory=dict)
    safe_areas: dict[str, SafeArea] = Field(default_factory=dict)
    compat_stages: list[CompatStage] = Field(default_factory=list)


# --------------------------------------------------------------------------- voice.yaml


class VoiceDraft(_Loose):
    """One of the free local auditions: a tendency added to the voice's description."""

    label: str  # the candidate's description (content)
    hint: str


class VoiceEmotion(_Loose):
    """One emotion variant of a finished voice; the UI names it ``enums:emotion.<id>``."""

    id: str
    instruct: str  # the emotion in words, for a local model (IndexTTS)
    minimax: dict[str, Any] = Field(default_factory=dict)  # T2A overrides (emotion, vol, model)


class VoiceConfig(_Loose):
    """How a voice is auditioned and finished (M3 ``voice``): ``config/voice.yaml``."""

    lines: int = 2  # script lines a voice reads to audition
    sample_text: str = "你好。"  # what it reads when its character has no lines yet
    local_final: str = "local/indextts2"  # variants of a local voice; the API flow's fallback
    drafts: list[VoiceDraft] = Field(default_factory=list)
    emotions: list[VoiceEmotion] = Field(default_factory=list)
    # 台词配音: words in a line's tone → its emotion, the first match in this order.
    tones: dict[str, list[str]] = Field(default_factory=dict)

    def emotion_of(self, tone: str | None) -> str:
        """The emotion a line's tone asks for; ``calm`` when none matches."""
        for emotion, words in self.tones.items():
            if tone and any(w in tone for w in words):
                return emotion
        return "calm"


@dataclass(frozen=True)
class StudioConfig:
    providers: ProvidersConfig
    components: ComponentsConfig
    spec: SpecConfig
    voice: VoiceConfig = field(default_factory=VoiceConfig)


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
        spec=SpecConfig.model_validate(_read_yaml(base / "spec.yaml")),
        voice=VoiceConfig.model_validate(
            _read_yaml(base / "voice.yaml") if (base / "voice.yaml").exists() else {}
        ),
    )


@lru_cache(maxsize=1)
def get_config() -> StudioConfig:
    """Process-wide factory config (tests changing ``DRAMA_CONFIG_DIR`` call cache_clear)."""
    return load_config()


# --------------------------------------------------------------------------- resolution


@dataclass(frozen=True)
class Defaults:
    """Global defaults on the Models page (``app_setting`` ``config.defaults``)."""

    preset: PresetId = "balanced"
    fallback_notify: Literal["after", "ask"] = "after"


def _first(keys: list[str]) -> str | None:
    return keys[0] if keys else None


def _alt_after(comp: ComponentDefault, primary: str | None, to: str | None) -> list[str]:
    """「不满意换一个」: the fallback target first, then the other models (local first)."""
    rest = [k for k in [*comp.local, *comp.api] if k not in (primary, to)]
    return [to, *rest] if to else rest


def preset_settings(
    comp: ComponentDefault, components: ComponentsConfig, defaults: Defaults | None = None
) -> dict[str, Any]:
    """One component's preset layer (SPEC 7.2; the prototype's ``presetCfg()``).

    质量优先 = the first API model, local only as fallback; 均衡 = components.yaml ``balanced``
    (mode not given: hybrid when there are both); 省钱 = local first, ``cheap_api`` as
    fallback; 全本地 = local only, components without a local model are ``off``.
    """
    defaults = defaults or Defaults()
    fb = components.fallback_defaults
    apis, locals_ = comp.api, comp.local
    cap = comp.per_call_cap_usd
    if cap is None:
        cap = components.per_call_cap_usd
    bal = comp.balanced
    api_model = bal.api or _first(apis)
    local_model = bal.local or _first(locals_)
    to = bal.fallback_to
    if defaults.preset == "balanced":
        mode = bal.mode or (
            "hybrid" if api_model and local_model else "api" if api_model else "local"
        )
        primary = local_model if mode in ("local", "hybrid") else api_model
        alt_order = list(comp.alt_order) if comp.alt_order else _alt_after(comp, primary, to)
        enabled = to is not None
    elif defaults.preset in ("quality", "cheap"):
        both = bool(apis and locals_)
        if defaults.preset == "quality":
            api_model = _first(apis)
            mode = "api" if apis else "local"
        else:
            api_model = comp.cheap_api or (apis[-1] if apis else None)
            mode = "local" if locals_ else "api"
        local_model = _first(locals_)
        to = (local_model if mode == "api" else api_model) if both else None
        alt_order = _alt_after(comp, api_model if mode == "api" else local_model, to)
        enabled = both
    else:  # local
        local_model = _first(locals_)
        mode = "local" if local_model else "off"
        to = None
        alt_order = [k for k in locals_ if k != local_model]
        enabled = False
    return {
        "mode": mode,
        "api_model": api_model,
        "local_model": local_model,
        "fallback": {
            "enabled": enabled,
            # Text has no auto QA, so a writing component never falls back on it by default.
            "on": [t for t in fb.on if not (t == "qa_fail" and comp.kind == "llm")],
            "qa_fail_n": fb.qa_fail_n,
            "timeout_s": fb.local_timeout_s,
            "to": to,
            "notify": defaults.fallback_notify,
        },
        "alt_order": alt_order,
        "per_call_cap_usd": cap if apis else None,
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
    # Local models taken off the route because this machine cannot run them → what each lacks
    # ("cuda" or setup item ids). ``values`` already route around them; ``sources`` are unchanged.
    unavailable: dict[str, list[str]] = field(default_factory=dict)


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
    caps: Capabilities | None = None,
    defaults: Defaults | None = None,
) -> Resolved:
    """Merge the preset layer with the overrides that apply to ``component_id`` / ``item``.

    With ``caps`` (this machine, after a scan), local models it cannot run are routed around
    last, so a hand-picked local model is dropped too (SPEC 7.3).
    """
    cfg = config or get_config()
    comp = cfg.components.component(component_id)
    values = copy.deepcopy(preset_settings(comp, cfg.components, defaults))
    sources: dict[str, Layer] = dict.fromkeys(_flatten(values), "preset")

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
    unavailable = restrict(values, cfg.providers, caps) if caps is not None else {}
    return Resolved(values=values, sources=sources, unavailable=unavailable)
