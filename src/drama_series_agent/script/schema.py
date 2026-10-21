"""API shapes of an episode's script (front-end contract ``web/src/api/schemas/script.ts``)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from drama_series_agent.bible.schema import SourceSpanOut

LineType = Literal["action", "dialogue", "vo", "sfx"]


class SceneOut(BaseModel):
    id: str
    episode_id: str
    idx: int  # 场号, 1-based across the series
    heading: str  # without the number: 「夜　内　林晚出租屋」
    location_id: str | None
    time_of_day: str | None
    paras: list[int]  # paragraph numbers across the book, 0-based
    source_spans: list[SourceSpanOut]
    edited: bool  # 「已修改」


class ScriptLineOut(BaseModel):
    id: str
    scene_id: str
    idx: int  # reading order within the episode, scene headings counted (the first is 0)
    type: LineType
    character_id: str | None
    character_name: str | None
    tone: str | None  # delivery in brackets: 「低声，愣住」, 「OS」
    text: str
    mood: str | None
    duration_s: float | None
    overlay_shot: str | None
    paras: list[int]
    # Paragraph spans; ``sug:<id>`` for a line from an accepted addition.
    source_spans: list[SourceSpanOut]
    ai_added: bool  # 「AI 新增」: not in the novel
    cliffhanger: bool  # 「本集卡点」
    edited: bool


class ScriptOut(BaseModel):
    """``GET /episodes/{id}/script``: the version on screen (the product's current one)."""

    episode_id: str
    product_id: str | None
    version_id: str | None
    # False while the version on screen is not the adopted one (「未采纳」).
    adopted: bool
    source_id: str | None
    scenes: list[SceneOut]
    lines: list[ScriptLineOut]


class LinePatch(BaseModel):
    """``PATCH /lines/{id}``."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(max_length=2000)


class ScenePatch(BaseModel):
    """``PATCH /scenes/{id}``: the heading without the 场号."""

    model_config = ConfigDict(extra="forbid")

    heading: str = Field(max_length=200)


class BlockRewriteIn(BaseModel):
    """``POST /lines/{id}/rewrite``, ``POST /scenes/{id}/rewrite``: 「重写这一段」 on the route's
    model, 「换模型重写」 on ``model``; ``confirm_budget`` after a 409 ``over_budget``."""

    model_config = ConfigDict(extra="forbid")

    model: str | None = None
    instruction: str | None = Field(default=None, max_length=500)
    confirm_budget: bool = False


class RewriteProposalOut(BaseModel):
    """A proposal: nothing is saved until the user keeps it (``PATCH`` or the impact preview)."""

    text: str
    model_key: str
