"""How long lines, scenes and shots run (M3: audio first; SPEC 7 时长由音频决定).

- A line runs as long as its dubbed audio; before it is dubbed, as long as the script estimated
  (the scriptwriter's ``duration_s``), else by its characters.
- A scene is its lines one after another.
- A shot covers some lines: their audio, plus a breath before and after. Over what one
  video take can hold, it suggests splitting.
- How long a shot runs (M4, Kelvin 2026-10-21): with dialogue, as long as its audio (the user
  may make it longer, never shorter); without, the plan's seconds or the user's. A voice-over
  laid over an action shot does not set its length (no lips to follow), it only must fit.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

PRE_ROLL_S = 0.3  # before the first line of a shot
POST_ROLL_S = 0.2  # after its last
CHARS_PER_SECOND = 4.0  # a line not dubbed nor estimated yet: about four characters a second
SHORTEST_LINE_S = 0.5
DEFAULT_SHOT_S = 3.0  # a shot without dialogue the plan gave no seconds


def line_seconds(text: str, script_s: float | None, audio_s: float | None) -> float:
    """The audio's length once dubbed; the script's estimate before; else by its characters."""
    if audio_s is not None:
        return round(audio_s, 3)
    if script_s is not None:
        return round(script_s, 3)
    spoken = len("".join(text.split()))
    return round(max(SHORTEST_LINE_S, spoken / CHARS_PER_SECOND), 3)


def scene_seconds(lines: Iterable[float]) -> float:
    return round(sum(lines), 3)


@dataclass(frozen=True)
class ShotTiming:
    seconds: float
    split: bool  # longer than one take can be: split the shot


def shot_seconds(audio_s: Sequence[float], longest_s: float | None = None) -> ShotTiming:
    """A shot over these lines' audio: their sum with a breath before and after."""
    seconds = round(PRE_ROLL_S + sum(audio_s) + POST_ROLL_S, 3)
    return ShotTiming(seconds, longest_s is not None and seconds > longest_s)


@dataclass(frozen=True)
class ShotDuration:
    seconds: float
    source: Literal["audio", "manual"]  # the audio set it, or the plan's or the user's seconds
    min_s: float  # the spoken lines' audio with a breath each side; 0 when nobody speaks
    split: bool  # longer than one take can be


def shot_duration(
    dialogue_s: Sequence[float],
    voiceover_s: Sequence[float],
    planned_s: float | None,
    manual_s: float | None,
    longest_s: float | None = None,
) -> ShotDuration:
    """How long a shot runs: ``dialogue_s`` are its on-screen lines' seconds, ``voiceover_s``
    the voice-over laid over it. Every spoken line fits; with dialogue, the audio sets the
    length unless the user made it longer; without, the user's seconds, else the plan's."""
    spoken = [*dialogue_s, *voiceover_s]
    floor = shot_seconds(spoken).seconds if spoken else 0.0
    if manual_s is not None:
        base = manual_s
    elif dialogue_s:
        base = floor
    else:
        base = planned_s if planned_s is not None else DEFAULT_SHOT_S
    source: Literal["audio", "manual"] = "manual"
    if (dialogue_s and manual_s is None) or floor > base:
        source = "audio"
    seconds = round(max(base, floor), 3)
    return ShotDuration(seconds, source, floor, longest_s is not None and seconds > longest_s)


def longest_take_s(
    route: Mapping[str, Any], caps_of: Callable[[str], Mapping[str, Any]]
) -> float | None:
    """The longest take the video route can make (the shorter of its models' ``duration_s``
    upper bounds: H3 is 15 s); None when no model on it says."""
    mode = route.get("mode")
    keys = [
        key
        for role, skip in (("api_model", "local"), ("local_model", "api"))
        if mode != skip and isinstance(key := route.get(role), str)
    ]
    bounds = []
    for key in keys:
        span = caps_of(key).get("duration_s")
        if isinstance(span, Sequence) and len(span) == 2 and isinstance(span[1], int | float):
            bounds.append(float(span[1]))
    return min(bounds) if bounds else None
