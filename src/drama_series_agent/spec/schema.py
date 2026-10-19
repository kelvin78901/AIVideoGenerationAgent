"""API shapes of the output spec (front end: ``web/src/api/schemas/spec.ts``)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from drama_series_agent.core.config import SpecConfig
from drama_series_agent.core.models_db import OutputSpecRow
from drama_series_agent.spec.dims import ASPECTS, Aspect, Delivery, Dims, all_tiers, dims

Platform = Literal["cn", "intl", "wide", "custom"]
Fps = Literal[24, 25, 30]
EpisodeLen = Literal["short", "mid", "long", "xl"]
Subtitles = Literal["burn", "srt", "both"]


class Audio(BaseModel):
    sample_rate: int
    lufs: float
    peak_dbtp: float


class SpecDims(BaseModel):
    delivery: Dims
    draft: Dims


class OutputSpec(BaseModel):
    series_id: str
    platform: Platform
    aspect: Aspect
    delivery: Delivery
    fps: Fps
    episode_len: EpisodeLen
    subtitles: Subtitles
    audio: Audio
    codec: str
    ai_mark: bool
    derive: Aspect | None
    locked_at: datetime | None
    dims: SpecDims


class SpecPatch(BaseModel):
    """``PUT /series/{id}/spec``: any subset of the editable fields."""

    model_config = ConfigDict(extra="forbid")

    platform: Platform | None = None
    aspect: Aspect | None = None
    delivery: Delivery | None = None
    fps: Fps | None = None
    episode_len: EpisodeLen | None = None
    subtitles: Subtitles | None = None
    derive: Aspect | None = None


def to_public(row: OutputSpecRow) -> OutputSpec:
    aspect: Aspect = row.aspect  # type: ignore[assignment]
    delivery: Delivery = row.delivery  # type: ignore[assignment]
    return OutputSpec.model_validate(
        {
            **row.model_dump(exclude={"audio_json"}),
            "audio": row.audio_json,
            "dims": SpecDims(delivery=dims(aspect, delivery), draft=dims(aspect, "draft")),
        }
    )


def apply_patch(row: OutputSpecRow, patch: SpecPatch) -> None:
    # `derive` may be set back to null on purpose; the other fields only when present.
    for field, value in patch.model_dump(exclude_unset=True).items():
        if value is not None or field == "derive":
            setattr(row, field, value)


def default_row(series_id: str, cfg: SpecConfig) -> OutputSpecRow:
    """A new series' spec from ``config/spec.yaml`` ``defaults``."""
    values: dict[str, Any] = dict(cfg.defaults)
    audio = values.pop("audio", {})
    return OutputSpecRow(series_id=series_id, audio_json=dict(audio), **values)


def presets(cfg: SpecConfig) -> dict[str, Any]:
    """``GET /spec/presets``: platform presets, sizes per aspect and the platform safe areas."""
    return {
        "platforms": [p.model_dump(include={"id", "aspect", "delivery"}) for p in cfg.platforms],
        "dims": {
            aspect: {tier: d.model_dump() for tier, d in all_tiers(aspect).items()}
            for aspect in ASPECTS
        },
        "safe_areas": {k: v.model_dump() for k, v in cfg.safe_areas.items()},
    }
