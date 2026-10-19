"""The only place that derives frame sizes from the output spec (SPEC 13.1, hard rule 10).

Input (aspect, tier) → width × height, both even. Delivery tiers are 1080p and 2K (short side
1080 / 1440); drafts always use the 768p tier (short side 768).
"""

from __future__ import annotations

import math
from typing import Literal, get_args

from pydantic import BaseModel

Aspect = Literal["9:16", "16:9", "3:4", "1:1", "21:9"]
Delivery = Literal["1080p", "2k"]
Tier = Literal["1080p", "2k", "draft"]

ASPECTS: tuple[Aspect, ...] = get_args(Aspect)

_RATIO: dict[Aspect, tuple[int, int]] = {
    "9:16": (9, 16),
    "16:9": (16, 9),
    "3:4": (3, 4),
    "1:1": (1, 1),
    "21:9": (21, 9),
}
SHORT_SIDE: dict[Tier, int] = {"1080p": 1080, "2k": 1440, "draft": 768}
# H3, the local draft-video model, tops out at about 2976×1248 for 21:9.
_CAPS: dict[tuple[Aspect, Tier], tuple[int, int]] = {("21:9", "2k"): (2976, 1248)}


class Dims(BaseModel):
    w: int
    h: int


def _even(n: float) -> int:
    # Round half up like the front end's Math.round, not Python's banker's rounding.
    return math.floor(n / 2 + 0.5) * 2


def is_vertical(aspect: Aspect) -> bool:
    w, h = _RATIO[aspect]
    return h > w


def dims(aspect: Aspect, tier: Tier) -> Dims:
    if (aspect, tier) in _CAPS:
        w, h = _CAPS[(aspect, tier)]
        return Dims(w=w, h=h)
    short = SHORT_SIDE[tier]
    rw, rh = _RATIO[aspect]
    if rw <= rh:
        return Dims(w=short, h=_even(short * rh / rw))
    return Dims(w=_even(short * rw / rh), h=short)


def all_tiers(aspect: Aspect) -> dict[Tier, Dims]:
    return {tier: dims(aspect, tier) for tier in get_args(Tier)}
