"""How long a shot runs (M4, Kelvin 2026-10-21): dialogue by its audio, the rest by the plan."""

from __future__ import annotations

from typing import Any

import pytest

from drama_series_agent.pipeline.timing import longest_take_s, shot_duration


def test_dialogue_runs_as_long_as_its_audio() -> None:
    d = shot_duration([1.2, 0.8], [], planned_s=4.0, manual_s=None)
    assert d.seconds == pytest.approx(0.3 + 2.0 + 0.2)
    assert d.source == "audio" and d.min_s == d.seconds and not d.split


def test_the_user_may_make_a_dialogue_shot_longer_never_shorter() -> None:
    longer = shot_duration([1.2], [], planned_s=None, manual_s=3.0)
    assert (longer.seconds, longer.source) == (3.0, "manual")
    assert longer.min_s == pytest.approx(1.7)
    # Redubbed longer than what the user typed: the audio wins again.
    shorter = shot_duration([1.2], [], planned_s=None, manual_s=1.0)
    assert (shorter.seconds, shorter.source) == (pytest.approx(1.7), "audio")


def test_a_voice_over_only_has_to_fit_the_action() -> None:
    """1-06: she closes the door (5 s by the plan) while the voice-over runs 2.25 s."""
    action = shot_duration([], [2.25], planned_s=5.0, manual_s=None)
    assert (action.seconds, action.source) == (5.0, "manual")
    assert action.min_s == pytest.approx(2.75)
    longer_vo = shot_duration([], [6.0], planned_s=5.0, manual_s=None)
    assert (longer_vo.seconds, longer_vo.source) == (pytest.approx(6.5), "audio")


def test_a_silent_shot_takes_the_plan_or_the_user() -> None:
    assert shot_duration([], [], planned_s=4.0, manual_s=None).seconds == 4.0
    assert shot_duration([], [], planned_s=4.0, manual_s=6.0).seconds == 6.0
    silent = shot_duration([], [], planned_s=None, manual_s=None)
    assert (silent.seconds, silent.source, silent.min_s) == (3.0, "manual", 0.0)


def test_over_one_take_suggests_a_split() -> None:
    assert shot_duration([14.8], [], None, None, longest_s=15.0).split
    assert not shot_duration([], [], 15.0, None, longest_s=15.0).split
    assert not shot_duration([14.8], [], None, None).split


def test_the_longest_take_is_the_routes_shortest_bound() -> None:
    caps: dict[str, dict[str, Any]] = {
        "minimax/h3-api": {"duration_s": [5, 15]},
        "comfy/h3": {"duration_s": [5, 15]},
        "comfy/short": {"duration_s": [2, 8]},
        "volc/seedance-2.5": {"aspects": ["9:16"]},
    }

    def caps_of(key: str) -> dict[str, Any]:
        return caps.get(key, {})

    hybrid = {"mode": "hybrid", "api_model": "minimax/h3-api", "local_model": "comfy/short"}
    assert longest_take_s(hybrid, caps_of) == 8.0
    assert longest_take_s({**hybrid, "mode": "api"}, caps_of) == 15.0
    assert longest_take_s({"mode": "local", "local_model": "comfy/h3"}, caps_of) == 15.0
    assert longest_take_s({"mode": "api", "api_model": "volc/seedance-2.5"}, caps_of) is None
    assert longest_take_s({"mode": "off"}, caps_of) is None
