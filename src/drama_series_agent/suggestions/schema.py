"""API shapes of enrichment suggestions (front-end contract ``web/src/api/schemas/novel.ts``)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from drama_series_agent.bible.schema import SourceSpanOut
from drama_series_agent.suggestions import ops

SuggestionKind = Literal[
    "appearance", "lighting", "inner_to_action", "cliffhanger", "motive", "timeline",
    "consistency", "gap",
]  # fmt: skip
SuggestionStatus = Literal["pending", "accepted", "rejected", "rewritten"]


class SuggestionOut(BaseModel):
    id: str
    series_id: str
    kind: SuggestionKind
    para_idx: int  # the paragraph the addition follows (across the book, 0-based)
    anchor_span: SourceSpanOut
    reason: str
    text: str  # the rewrite when there is one
    status: SuggestionStatus
    # Set once rewritten on request (「已按要求重写」), kept after accepting.
    rewrite_instruction: str | None
    rewritten_by: str | None


class SuggestionsOut(BaseModel):
    """``GET /series/{id}/suggestions``: the 小说补全 version on screen (the current one)."""

    series_id: str
    product_id: str | None
    version_id: str | None
    # False while the version on screen is not the adopted one (「未采纳」).
    adopted: bool
    source_id: str | None
    suggestions: list[SuggestionOut]


class RewriteIn(BaseModel):
    """``POST /suggestions/{id}/rewrite``; ``confirm_budget`` after a 409 ``over_budget``."""

    model_config = ConfigDict(extra="forbid")

    instruction: str = Field(max_length=500)
    confirm_budget: bool = False


def suggestion_out(
    series_id: str, s: Mapping[str, Any], decision: Mapping[str, Any] | None
) -> SuggestionOut:
    return SuggestionOut(
        id=s["id"],
        series_id=series_id,
        kind=s["kind"],
        para_idx=s["para_idx"],
        anchor_span=SourceSpanOut.model_validate(s["anchor_span"]),
        reason=s.get("reason") or "",
        text=ops.final_text(s, decision),
        status=ops.status_of(decision),
        rewrite_instruction=decision.get("rewrite_instruction") if decision else None,
        rewritten_by=decision.get("rewritten_by") if decision else None,
    )


def suggestions_out(
    series_id: str,
    payload: Mapping[str, Any] | None,
    decisions: ops.Decisions,
    *,
    product_id: str | None = None,
    version_id: str | None = None,
    adopted: bool = True,
) -> SuggestionsOut:
    """One pure view of a version, adopted or not (plan 设计要点「当前和采纳」)."""
    payload = payload or {}
    return SuggestionsOut(
        series_id=series_id,
        product_id=product_id,
        version_id=version_id,
        adopted=adopted,
        source_id=payload.get("source_id"),
        suggestions=[
            suggestion_out(series_id, s, decisions.get(s["id"]))
            for s in payload.get("suggestions") or []
        ],
    )
