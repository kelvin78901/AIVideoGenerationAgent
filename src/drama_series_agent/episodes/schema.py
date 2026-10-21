"""API shapes of episodes, beats and step progress (front-end contract
``web/src/api/schemas/episodes.ts``)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from drama_series_agent.bible.schema import SourceSpanOut

EpisodeStage = Literal["in_progress", "script_pending", "not_started", "done"]
ScriptStatus = Literal["none", "draft", "confirmed"]
StepId = Literal["novel", "script", "assets", "storyboard", "generate", "post"]
STEP_IDS: tuple[StepId, ...] = ("novel", "script", "assets", "storyboard", "generate", "post")


class BeatOut(BaseModel):
    id: str
    episode_id: str
    idx: int  # 1-based within the episode
    text: str
    emotion: float  # -1 … 1
    paras: list[int]  # paragraph numbers across the book, 0-based
    source_spans: list[SourceSpanOut]


class EpisodeOut(BaseModel):
    """An episode of the adopted plan (分集规划) with what the pages show about it."""

    id: str
    series_id: str
    idx: int  # 1-based; the route uses it (``/s/:series/e/:idx/...``)
    title: str
    hook: str | None
    cliffhanger: str | None
    target_seconds: int | None
    scene_count: int | None  # 预计场数
    budget_usd: float | None
    stage: EpisodeStage
    # Scenes the episode covers, numbered across the series (planned counts before scripts).
    scene_from: int | None
    scene_to: int | None
    shot_count: int | None  # once the storyboard exists (M4)
    script_status: ScriptStatus
    beats: list[BeatOut]


class EpisodePatch(BaseModel):
    """``PATCH /episodes/{id}``: only the fields sent change. The budget is a setting; the
    other fields edit the plan (an ``edit`` version of 分集规划, adopted)."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=200)
    hook: str | None = Field(default=None, max_length=500)
    cliffhanger: str | None = Field(default=None, max_length=500)
    target_seconds: int | None = Field(default=None, ge=1, le=3600)
    budget_usd: float | None = Field(default=None, ge=0)


class BeatPatch(BaseModel):
    """``PATCH /beats/{id}``: 改文字、情绪, or drag it to another episode / place
    (``position`` is 0-based among the target episode's other beats; the end when omitted)."""

    model_config = ConfigDict(extra="forbid")

    text: str | None = Field(default=None, max_length=500)
    emotion: float | None = Field(default=None, ge=-1, le=1)
    episode_id: str | None = None
    position: int | None = Field(default=None, ge=0)


class StepProgressOut(BaseModel):
    """One production step as the nav badge shows it: 已确认 / 7/13 / 未开始 / 待更新 N."""

    state: Literal["confirmed", "in_progress", "not_started"]
    done: int | None = None
    total: int | None = None
    stale: int = 0  # products of the step that are 待更新


class EpisodeProgressOut(BaseModel):
    episode_id: str
    steps: dict[StepId, StepProgressOut]


class SeriesProgressOut(BaseModel):
    """The badges before the series has episodes: 小说 (its gate is the series'), the rest not
    started."""

    series_id: str
    steps: dict[StepId, StepProgressOut]
