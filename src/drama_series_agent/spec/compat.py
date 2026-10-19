"""Can the models on the current route make this output spec? (SPEC 13.3)

Each row of ``config/spec.yaml`` ``compat_stages`` picks model(s) from one component's resolved
settings and judges them by their ``caps`` in ``providers.yaml``:

- aspect not in ``caps.aspects`` → ``unsupported``: make the nearest supported aspect, then
  outpaint or crop (``outpaint_from_<aspect>``);
- ``caps.max_short_edge`` below the stage's tier → ``convert``: upscale (``upscale_from_<res>``);
- otherwise ``native``, explained by the stage's own ``native`` code.

Only the aspect and size are checked; frame rate is converted in post (SPEC 13.2).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from typing import Any, Literal

from pydantic import BaseModel

from drama_series_agent.core.config import CompatStage, StudioConfig
from drama_series_agent.spec.dims import Aspect, Delivery, dims

Status = Literal["native", "convert", "unsupported"]
_RANK: dict[Status, int] = {"native": 0, "convert": 1, "unsupported": 2}


class How(BaseModel):
    code: str
    params: dict[str, str | int] = {}


class CompatRow(BaseModel):
    stage: str
    model_keys: list[str]
    status: Status
    how: How


class Compat(BaseModel):
    aspect: Aspect
    rows: list[CompatRow]


def model_caps(cfg: StudioConfig, key: str) -> dict[str, Any]:
    for media in cfg.providers.media_models:
        if media.key == key:
            return media.caps
    for local in cfg.providers.local_models:
        if local.key == key:
            return local.caps
    return {}


def _ratio(aspect: str) -> float:
    w, h = (int(x) for x in aspect.split(":"))
    return w / h


def _nearest(aspect: str, choices: list[str]) -> str:
    target = math.log(_ratio(aspect))
    return min(choices, key=lambda a: abs(math.log(_ratio(a)) - target))


def _res_label(px: int) -> str:
    return f"{round(px / 1024)}k" if px >= 1024 else f"{px}p"


def judge(caps: Mapping[str, Any], aspect: Aspect, short_edge: int) -> tuple[Status, How | None]:
    """One model: its status and, unless native, how the gap is bridged."""
    aspects = caps.get("aspects")
    if aspects and aspect not in aspects:
        src = _nearest(aspect, list(aspects))
        return "unsupported", How(code=f"outpaint_from_{src.replace(':', '_')}")
    max_edge = caps.get("max_short_edge")
    if isinstance(max_edge, int) and max_edge < short_edge:
        return "convert", How(code=f"upscale_from_{_res_label(max_edge)}")
    return "native", None


def _picked(stage: CompatStage, values: Mapping[str, Any]) -> list[str]:
    keys: list[str] = []
    for role in stage.pick:
        if role == "fallback":
            key = values.get("fallback", {}).get("to")
        elif role == "alt":
            primary = values.get("api_model")
            key = next((m for m in values.get("alt_order", []) if m != primary), None)
        else:
            key = values.get(role)
        if isinstance(key, str) and key not in keys:
            keys.append(key)
    return keys


def compat_table(
    aspect: Aspect,
    delivery: Delivery,
    settings: Callable[[str], Mapping[str, Any]],
    cfg: StudioConfig,
) -> Compat:
    """``settings(component_id)`` gives that component's resolved values (preset + overrides)."""
    rows: list[CompatRow] = []
    for stage in cfg.spec.compat_stages:
        values = settings(stage.component)
        if values.get("mode") == "off":
            continue
        keys = _picked(stage, values)
        if not keys:
            continue
        tier = dims(aspect, "draft" if stage.tier == "draft" else delivery)
        short_edge = min(tier.w, tier.h)
        status: Status = "native"
        how = How(code=stage.native)
        for key in keys:
            s, h = judge(model_caps(cfg, key), aspect, short_edge)
            if _RANK[s] > _RANK[status] and h is not None:
                status, how = s, h
        rows.append(CompatRow(stage=stage.stage, model_keys=keys, status=status, how=how))
    return Compat(aspect=aspect, rows=rows)
