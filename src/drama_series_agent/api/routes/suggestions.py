"""Enrichment suggestions (SPEC 9.1): ``GET /series/{id}/suggestions``, decisions on one
(``accept`` / ``reject`` / ``reset`` / ``rewrite``) and ``accept-all``. Deciding never makes a
version (``suggestions/service.py``)."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends

from drama_series_agent.api.state import StudioState, get_state
from drama_series_agent.suggestions.schema import RewriteIn, SuggestionOut, SuggestionsOut

router = APIRouter(tags=["suggestions"])

State = Annotated[StudioState, Depends(get_state)]


@router.get("/series/{series_id}/suggestions")
async def list_suggestions(series_id: str, state: State) -> SuggestionsOut:
    """The version on screen with the user's decisions; ``adopted`` false = 「未采纳」."""
    return await state.suggestions.get(series_id)


@router.post("/series/{series_id}/suggestions/accept-all")
async def accept_all(series_id: str, state: State) -> SuggestionsOut:
    """「全部采纳」: every suggestion that was not ignored."""
    return await state.suggestions.accept_all(series_id)


# Before the generic route below, which would take 「rewrite」 as an action.
@router.post("/suggestions/{suggestion_id}/rewrite")
async def rewrite(suggestion_id: str, body: RewriteIn, state: State) -> SuggestionOut:
    """「按要求重写这一条」: 409 ``over_budget`` over the per-call cap until ``confirm_budget``."""
    return await state.suggestions.rewrite(suggestion_id, body)


@router.post("/suggestions/{suggestion_id}/{action}")
async def decide(
    suggestion_id: str, action: Literal["accept", "reject", "reset"], state: State
) -> SuggestionOut:
    """采纳 / 忽略 / 撤销 (back to undecided, or to 「已重写」 after a rewrite)."""
    return await state.suggestions.decide(suggestion_id, action)
