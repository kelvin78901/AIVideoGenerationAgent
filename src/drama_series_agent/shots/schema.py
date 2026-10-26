"""API shapes of an episode's shots (front-end contract ``web/src/api/schemas/shots.ts``)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ShotType = Literal["continuous", "same_scene_cut", "scene_change"]
Framing = Literal["wide", "medium", "close", "closeup"]
CameraMove = Literal["static", "push", "follow", "pan"]
AudioMode = Literal["native", "tts", "none"]
BlockingKind = Literal["character", "camera", "prop", "landmark"]


class BlockingItem(BaseModel):
    """One mark on the top view (站位俯视图): 0–1 across and down, the action up the page."""

    model_config = ConfigDict(extra="forbid")

    id: str
    kind: BlockingKind
    label: str
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class ShotOut(BaseModel):
    id: str
    episode_id: str
    scene_id: str
    label: str  # 「1-04」: episode number and the shot's place in the episode
    scene_no: int  # series-wide 场号
    scene_place: str  # where the scene is (the heading without day / night, 内 / 外)
    idx: int  # 1-based within the episode
    summary: str
    intent: str  # the keyframe prompt's intent layer (the plan's seed until the user edits it)
    seed_changed: bool  # the plan gave a new picture description since the user edited it
    shot_type: ShotType
    framing: Framing
    camera_move: CameraMove
    duration_s: float  # how long it runs (``timing.shot_duration``)
    duration_source: Literal["audio", "manual"]
    min_s: float  # its spoken lines with a breath each side; 0 when nobody speaks
    planned_s: float | None  # the plan's seconds
    manual_s: float | None  # the user's seconds
    longest_s: float | None  # the longest take the video route makes
    split_hint: bool  # longer than that: split it
    line_ids: list[str]
    dialogue: str | None  # its spoken lines as the script writes them; None = nobody speaks
    sound: str | None
    audio_mode: AudioMode
    asset_ids: list[str]
    tail_from: str | None  # a continuous shot: the label of the shot it starts from
    tail_note: str | None
    blocking: list[BlockingItem]
    keyframe_product_id: str | None
    video_product_id: str | None  # M5
    keyframe_pick: int  # the candidate picked on the keyframe's version on screen
    keyframe_sha256: str | None  # that candidate's picture (``GET /files/{sha256}``)
    confirmed: bool  # its last 「确认这个镜头」 decision (gate ``shot``) is a confirm
    # Confirmed, but its settings (the plan's ``shot:<id>`` slice) or its keyframe changed since.
    confirm_stale: bool


class ShotPatch(BaseModel):
    """``PATCH /shots/{id}``: any of these. ``duration_s`` null = back to automatic."""

    model_config = ConfigDict(extra="forbid")

    shot_type: ShotType | None = None
    framing: Framing | None = None
    camera_move: CameraMove | None = None
    duration_s: float | None = Field(default=None, gt=0, le=60)
    intent: str | None = None
    audio_mode: AudioMode | None = None
    asset_ids: list[str] | None = None
    blocking: list[BlockingItem] | None = None
    keyframe_pick: int | None = Field(default=None, ge=0)
    confirmed: bool | None = None


class ShotSplitIn(BaseModel):
    """``POST /shots/{id}/split``: cut after this line (default: the middle)."""

    model_config = ConfigDict(extra="forbid")

    after_line_id: str | None = None


class ShotEditIn(ShotPatch):
    """The impact preview's ``shot_edit`` patch (a confirmed shot, or a shot of a confirmed
    storyboard): its settings, or a split / a merge with the next shot."""

    split: ShotSplitIn | None = None
    merge: bool = False
