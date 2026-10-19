"""What the model pickers list (SPEC 7, 9.1 ``GET /config/components``).

Every model in ``providers.yaml`` with its list price, and per component the models it can use
and the run locations this machine cannot offer. Shapes follow ``web/src/api/schemas/config.ts``
and ``models.ts``.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from drama_series_agent.core.capabilities import CUDA, Capabilities, local_model
from drama_series_agent.core.config import ComponentDefault, MediaModel, StudioConfig

Where = Literal["local", "api"]


class ModelOption(BaseModel):
    key: str
    display: str
    where: Where
    price: dict[str, Any] | None


class Message(BaseModel):
    code: str
    params: dict[str, str | int | float] = {}


class ComponentDef(BaseModel):
    id: str
    stage: str
    kind: str
    api_models: list[str]
    local_models: list[str]
    unavailable: dict[str, Message]


class Catalog(BaseModel):
    components: list[ComponentDef]
    models: list[ModelOption]
    local_runtime_ok: bool


def _currency(value: Any) -> str:
    return "CNY" if value == "CNY" else "USD"


def _media_price(m: MediaModel) -> dict[str, Any] | None:
    """A media model's list price in the UI's units; None when there is no per-use price."""
    extra: dict[str, Any] = m.model_extra or {}
    currency = _currency(m.currency)
    price = extra.get("price")
    unit = m.unit
    if unit == "char":
        per_million = extra.get("price_per_million")
        return (
            {"unit": "mchar", "amount": float(per_million), "currency": currency}
            if per_million is not None
            else None
        )
    if unit == "second":
        if price is None and isinstance(extra.get("price_by_res"), dict):
            price = min(extra["price_by_res"].values())  # the draft tier, "from …"
        if price is None and isinstance(extra.get("price_range"), list):
            price = extra["price_range"][0]
    if unit == "minute" and isinstance(price, int | float):
        unit, price = "second", price / 60
    if unit == "world":
        unit = "call"
    if unit not in ("image", "second", "call") or not isinstance(price, int | float):
        return None  # subscriptions, token-priced helpers, unknown prices
    return {"unit": unit, "amount": float(price), "currency": currency}


def model_options(cfg: StudioConfig) -> list[ModelOption]:
    out: list[ModelOption] = []
    for provider in cfg.providers.llm_providers:
        for m in provider.models:
            price = None
            if m.price is not None and provider.where == "api":
                price = {
                    "unit": "mtok",
                    "in": m.price.in_,
                    "out": m.price.out,
                    "currency": _currency(m.price.currency),
                }
            out.append(ModelOption(key=m.key, display=m.display, where=provider.where, price=price))
    for media in cfg.providers.media_models:
        out.append(
            ModelOption(
                key=media.key, display=media.display, where="api", price=_media_price(media)
            )
        )
    for loc in cfg.providers.local_models:
        out.append(ModelOption(key=loc.key, display=loc.display, where="local", price=None))
    return out


def _machine_reason(lacks: list[list[str]]) -> Message:
    """Why none of a component's local models runs here: no CUDA, or items still missing."""
    if all(CUDA in one for one in lacks):
        return Message(code="machine_cuda")
    fewest = min((one for one in lacks if CUDA not in one), key=len)
    return Message(code="machine_missing", params={"count": len(fewest)})


def component_def(
    comp: ComponentDefault, cfg: StudioConfig, known: set[str], caps: Capabilities | None
) -> ComponentDef:
    api = [k for k in comp.api if k in known]
    local = [k for k in comp.local if k in known]
    unavailable: dict[str, Message] = {}
    if caps is not None and local:
        lacks = []
        for key in local:
            model = local_model(cfg.providers, key)
            lacks.append(caps.missing(model) if model is not None else [])
        if all(lacks):
            reason = _machine_reason(lacks)
            unavailable = {"local": reason, "hybrid": reason}
    return ComponentDef(
        id=comp.id,
        stage=comp.stage,
        kind=comp.kind,
        api_models=api,
        local_models=local,
        unavailable=unavailable,
    )


def catalog(cfg: StudioConfig, caps: Capabilities | None) -> Catalog:
    models = model_options(cfg)
    known = {m.key for m in models}
    return Catalog(
        components=[component_def(c, cfg, known, caps) for c in cfg.components.components],
        models=models,
        # Before a scan we cannot tell; afterwards: did it find ComfyUI.
        local_runtime_ok=caps is None or "comfy" in caps.found,
    )
