"""分集规划 as data (``episodes.ops``): ids across reruns, edits and drags, scene numbers."""

from __future__ import annotations

from itertools import count
from typing import Any

import pytest

from drama_series_agent.episodes import ops
from drama_series_agent.pipeline.invalidation import slice_hash


def _ids(prefix: str) -> Any:
    n = count(1)
    return lambda: f"{prefix}{next(n)}"


def _found(*episodes: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "title": f"第 {i} 集",
            "hook": None,
            "cliffhanger": None,
            "target_seconds": 60,
            "scene_count": 2,
            "beats": [{"text": t, "emotion": 0.0, "paras": [], "source_spans": []} for t in beats],
        }
        for i, beats in enumerate(episodes, 1)
    ]


def _plan(*episodes: list[str]) -> dict[str, Any]:
    found = _found(*episodes)
    return {"source_id": "src", "episodes": ops.reconcile(found, None, _ids("e"), _ids("b"))}


def _shape(payload: dict[str, Any]) -> list[tuple[str, int, list[tuple[str, int, str]]]]:
    return [
        (e["id"], e["idx"], [(b["id"], b["idx"], b["text"]) for b in e["beats"]])
        for e in payload["episodes"]
    ]


def test_a_first_run_numbers_everything() -> None:
    plan = _plan(["雨夜回家", "门口的红伞"], ["冲下楼"])
    assert _shape(plan) == [
        ("e1", 1, [("b1", 1, "雨夜回家"), ("b2", 2, "门口的红伞")]),
        ("e2", 2, [("b3", 1, "冲下楼")]),
    ]


def test_a_rerun_keeps_episode_numbers_and_beats_it_writes_again() -> None:
    base = _plan(["雨夜回家", "门口的红伞", "她拿起了伞"], ["冲下楼"])
    again = _found(
        ["门口的红伞"],  # moved to episode 1 alone
        ["雨夜回家", "冲下楼了", "全新的节拍"],  # same / similar / new
        ["第三集的节拍"],
    )
    out = ops.reconcile(again, base, _ids("new-e"), _ids("new-b"))
    assert _shape({"episodes": out}) == [
        ("e1", 1, [("b2", 1, "门口的红伞")]),
        ("e2", 2, [("b1", 1, "雨夜回家"), ("b4", 2, "冲下楼了"), ("new-b1", 3, "全新的节拍")]),
        ("new-e1", 3, [("new-b2", 1, "第三集的节拍")]),
    ]


def test_patch_episode() -> None:
    plan = _plan(["雨夜回家"])
    out = ops.patch_episode(plan, "e1", title=" 红伞 ", hook="  ", cliffhanger="她拿起了伞")
    e = out["episodes"][0]
    assert (e["title"], e["hook"], e["cliffhanger"]) == ("红伞", None, "她拿起了伞")
    assert plan["episodes"][0]["title"] == "第 1 集"  # the input is left as it was
    with pytest.raises(ops.EpisodeEditError) as err:
        ops.patch_episode(plan, "e1", title=" ")
    assert err.value.code == "title_required"
    with pytest.raises(ops.EpisodeEditError) as err:
        ops.patch_episode(plan, "nope", title="x")
    assert err.value.code == "episode_not_found"


def test_patch_and_drag_a_beat() -> None:
    plan = _plan(["a", "b", "c"], ["d"])
    out = ops.patch_beat(plan, "b2", text=" 改过 ", emotion=1.5)
    beat = out["episodes"][0]["beats"][1]
    assert (beat["text"], beat["emotion"]) == ("改过", 1.0)
    # Drag b1 to the start of episode 2, then b3 down within episode 1 (to the end).
    out = ops.patch_beat(plan, "b1", episode_id="e2", position=0)
    assert _shape(out) == [
        ("e1", 1, [("b2", 1, "b"), ("b3", 2, "c")]),
        ("e2", 2, [("b1", 1, "a"), ("b4", 2, "d")]),
    ]
    out = ops.patch_beat(plan, "b1", position=9)
    assert [b["id"] for b in out["episodes"][0]["beats"]] == ["b2", "b3", "b1"]
    for kwargs, code in (
        ({"text": "  "}, "beat_empty"),
        ({"episode_id": "nope"}, "episode_not_found"),
    ):
        with pytest.raises(ops.EpisodeEditError) as err:
            ops.patch_beat(plan, "b1", **kwargs)
        assert err.value.code == code
    with pytest.raises(ops.EpisodeEditError) as err:
        ops.patch_beat(plan, "nope", text="x")
    assert err.value.code == "beat_not_found"


def test_a_drag_changes_only_the_two_episodes_slices() -> None:
    plan = _plan(["a", "b"], ["c"], ["d"])
    out = ops.patch_beat(plan, "b2", episode_id="e2")
    before = {e["id"]: slice_hash(ops.episode_slice(plan, e["id"])) for e in plan["episodes"]}
    after = {e["id"]: slice_hash(ops.episode_slice(out, e["id"])) for e in out["episodes"]}
    assert [k for k in before if before[k] != after[k]] == ["e1", "e2"]
    # Renumbering episodes alone (idx is a display field) changes no slice.
    swapped = {**plan, "episodes": [{**e, "idx": 9} for e in plan["episodes"]]}
    assert all(slice_hash(ops.episode_slice(swapped, k)) == before[k] for k in ("e1", "e2", "e3"))
    assert ops.episode_slice(plan, "nope") is None


def test_scene_ranges() -> None:
    episodes = [
        {"id": "e1", "idx": 1, "scene_count": 2},
        {"id": "e2", "idx": 2, "scene_count": None},
        {"id": "e3", "idx": 3, "scene_count": 3},
    ]
    assert ops.scene_ranges(episodes) == {"e1": (1, 2), "e2": None, "e3": (3, 5)}
