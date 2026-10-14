"""Cost from usage × unit price. Costs are computed at call time and stored with a price
snapshot, so later price changes never rewrite history (SPEC 10)."""

from __future__ import annotations

from typing import Any

from drama_series_agent.core.config import LlmModel, MediaModel
from drama_series_agent.modelhub.adapters.base import Pricing, Usage

DEFAULT_CNY_PER_USD = 7.1


def to_usd(amount: float, currency: str, rates: dict[str, float] | None = None) -> float:
    if currency.upper() == "USD":
        return amount
    if currency.upper() == "CNY":
        return amount / (rates or {}).get("CNY_per_USD", DEFAULT_CNY_PER_USD)
    raise ValueError(f"unsupported currency: {currency}")


def cost_usd(
    pricing: Pricing,
    usage: Usage,
    *,
    resolution: str | None = None,
    offpeak: bool = False,
    rates: dict[str, float] | None = None,
) -> float:
    """Cost of one call. Unknown prices cost 0 (the estimate is flagged as unpriced instead)."""
    unit = pricing.unit
    amount = 0.0
    if unit == "token":
        amount = (usage.tokens_in or 0) * (pricing.price_in or 0) / 1e6
        amount += (usage.tokens_out or 0) * (pricing.price_out or 0) / 1e6
    elif unit == "image":
        amount = (usage.images or 0) * (pricing.price or 0)
    elif unit in ("second", "minute"):
        per = pricing.price or 0
        if pricing.price_by_res and resolution in pricing.price_by_res:
            per = pricing.price_by_res[resolution]
        seconds = usage.output_seconds or 0
        amount = seconds * per if unit == "second" else seconds / 60 * per
        amount += (usage.input_seconds or 0) * (pricing.input_price_per_second or 0)
    elif unit == "char":
        amount = (usage.chars or 0) * (pricing.price or 0)
    elif unit in ("call", "world"):
        amount = pricing.price or 0
    if offpeak and pricing.offpeak and "factor" in pricing.offpeak:
        amount *= float(pricing.offpeak["factor"])
    return round(to_usd(amount, pricing.currency, rates), 10)


def pricing_for_llm(model: LlmModel, as_of: str | None) -> Pricing:
    if model.price is None:
        return Pricing(unit="token", as_of=as_of, offpeak=model.offpeak)
    return Pricing(
        unit="token",
        price_in=model.price.in_,
        price_out=model.price.out,
        currency=model.price.currency,
        as_of=as_of,
        offpeak=model.offpeak,
    )


def pricing_for_media(model: MediaModel, as_of: str | None) -> Pricing:
    extra: dict[str, Any] = model.model_extra or {}
    unit = model.unit or "call"
    price = extra.get("price")
    if unit == "char" and extra.get("price_per_million") is not None:
        price = float(extra["price_per_million"]) / 1e6
    if unit == "token" and isinstance(price, dict):
        return Pricing(
            unit="token",
            price_in=price.get("in"),
            price_out=price.get("out"),
            currency=model.currency,
            as_of=as_of,
        )
    if unit not in ("token", "image", "second", "minute", "char", "call", "world"):
        unit = "call"  # e.g. "subscription": not billed per call
        price = None
    if isinstance(price, dict):
        price = None
    return Pricing(
        unit=unit,
        price=price,
        price_by_res=extra.get("price_by_res"),
        input_price_per_second=extra.get("input_price_per_second"),
        currency=model.currency,
        as_of=as_of,
    )
