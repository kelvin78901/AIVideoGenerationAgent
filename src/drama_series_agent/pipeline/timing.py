"""How long lines, scenes and shots run (M3: audio first; SPEC 7 时长由音频决定).

- A line runs as long as its dubbed audio; before it is dubbed, as long as the script estimated
  (the scriptwriter's ``duration_s``), else by its characters.
- A scene is its lines one after another.
- A shot (M4) covers some lines: their audio, plus a breath before and after. Over what one
  video take can hold, it suggests splitting.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

PRE_ROLL_S = 0.3  # before the first line of a shot
POST_ROLL_S = 0.2  # after its last
CHARS_PER_SECOND = 4.0  # a line not dubbed nor estimated yet: about four characters a second
SHORTEST_LINE_S = 0.5


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
