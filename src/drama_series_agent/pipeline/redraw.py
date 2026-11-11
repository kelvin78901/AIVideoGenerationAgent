"""检查没过自动重画 (M5.5 step 9e-5, Kelvin 2026-11-11): a keyframe run whose every candidate
failed its check (``kfcheck``), or a take that failed its own (``takecheck``), is made again
with what failed, up to the component's ``redraw`` (``config/components.yaml``) more times, on
this machine only (an API picture or take costs: there a failed check stays a warning). The
first try that passes is kept, else the one with the most checks passed; still only a warning.

A check here is what both checks write: ``{"items": [{"check", "ok", "note"}], "ok", "model"}``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from drama_series_agent.core.config import get_config

FIX_TITLE = "上一次没过的检查（这次要改掉）"


def tries(component_id: str) -> int:
    """How many more tries ``component_id`` may take (its ``redraw``; 0 when not set)."""
    try:
        return max(0, get_config().components.component(component_id).redraw)
    except KeyError:
        return 0


def checked(check: Mapping[str, Any] | None) -> bool:
    """Whether there is anything to go by (a check that ran and asked something)."""
    return bool((check or {}).get("items"))


def failed(check: Mapping[str, Any] | None) -> bool:
    """A check that ran and did not pass."""
    return checked(check) and not (check or {}).get("ok")


def score(check: Mapping[str, Any] | None) -> int:
    """How many of its items passed."""
    return sum(1 for x in (check or {}).get("items") or [] if x.get("ok"))


def failed_text(check: Mapping[str, Any] | None, labels: Mapping[str, str]) -> str:
    """What failed, one line each (「- 机位在场景里：机位在楼道里」), for the next try's prompt."""
    rows = []
    for x in (check or {}).get("items") or []:
        if x.get("ok"):
            continue
        label = labels.get(str(x.get("check")), str(x.get("check")))
        note = str(x.get("note") or "")
        if x.get("check") == "ocr" and note:
            note = f"读到「{note}」"
        rows.append(f"- {label}：{note}" if note else f"- {label}")
    return "\n".join(rows)
