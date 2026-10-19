"""An episode's script (SPEC 9.1): ``GET /episodes/{id}/script``, ``PATCH /lines/{id}``,
``PATCH /scenes/{id}`` and 「重写这一段」 ``POST /lines|scenes/{id}/rewrite``. Edits append an
``edit`` version of the episode's 剧本化 and adopt it; a rewrite only proposes a text
(``script/service.py``)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from drama_series_agent.api.state import StudioState, get_state
from drama_series_agent.script.schema import (
    BlockRewriteIn,
    LinePatch,
    RewriteProposalOut,
    ScenePatch,
    ScriptOut,
)

router = APIRouter(tags=["script"])

State = Annotated[StudioState, Depends(get_state)]


@router.get("/episodes/{episode_id}/script")
async def get_script(episode_id: str, state: State) -> ScriptOut:
    """The version on screen; empty before the first run, ``adopted`` false = 「未采纳」."""
    return await state.script.get(episode_id)


@router.patch("/lines/{line_id}")
async def patch_line(line_id: str, body: LinePatch, state: State) -> ScriptOut:
    """改一行 (an unconfirmed script; a confirmed one goes through the impact preview)."""
    return await state.script.patch_line(line_id, body)


@router.patch("/scenes/{scene_id}")
async def patch_scene(scene_id: str, body: ScenePatch, state: State) -> ScriptOut:
    """改场景标题 (without the 场号)."""
    return await state.script.patch_scene(scene_id, body)


@router.post("/lines/{line_id}/rewrite")
async def rewrite_line(line_id: str, body: BlockRewriteIn, state: State) -> RewriteProposalOut:
    """A proposal; 409 ``over_budget`` over the per-call cap or the episode's budget until
    ``confirm_budget``."""
    return await state.script.rewrite(line_id, body, scene=False)


@router.post("/scenes/{scene_id}/rewrite")
async def rewrite_scene(scene_id: str, body: BlockRewriteIn, state: State) -> RewriteProposalOut:
    """A proposed heading, as for a line."""
    return await state.script.rewrite(scene_id, body, scene=True)
