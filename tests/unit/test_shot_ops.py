"""The shot plan's rules (M4): every line filmed, voice-over laid over action, continuous shots
following the right shot, ids across reruns, split and merge."""

from __future__ import annotations

import json
from typing import Any

import pytest

from drama_series_agent.core.paths import REPO_ROOT
from drama_series_agent.shots import ops

# The demo's episode 1: scene b1 (L1–L5), scene b7 (L6–L10); L4 dialogue, L8 voice-over.
TYPES = {4: "dialogue", 8: "vo"}
SCENES = {n: "demo-b1" if n <= 5 else "demo-b7" for n in range(1, 11)}
LINE_ID = {n: f"demo-b{n + 1 if n <= 5 else n + 2}" for n in range(1, 11)}
KINDS = {
    "linwan": "character",
    "hall": "scene",
    "room": "scene",
    "umbrella": "prop",
    "note": "prop",
    "band": "prop",
    "phone": "prop",
    "txt1": "text",
    "txt2": "text",
    "vlinwan": "voice",
}


def _ctx() -> ops.PlanContext:
    lines = [
        ops.PlanLine(n, SCENES[n], LINE_ID[n], TYPES.get(n, "action"), f"line {n}")
        for n in range(1, 11)
    ]
    return ops.PlanContext(
        episode_id="demo-e1",
        scene_ids=["demo-b1", "demo-b7"],
        lines=lines,
        asset_kinds=KINDS,
        asset_names={"linwan": "林晚", "umbrella": "红色长柄伞"},
        line_assets={"demo-b2": ["linwan"], "demo-b5": ["linwan", "vlinwan"]},
        scene_assets={"demo-b1": ["hall"], "demo-b7": ["room"]},
    )


def _demo_answer() -> dict[str, Any]:
    path = REPO_ROOT / "tests" / "fixtures" / "demo" / "plan.json"
    answer: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))["answer"]
    return answer


def _lines(payload: dict[str, Any]) -> list[list[str]]:
    return [s["line_ids"] for s in payload["shots"]]


def test_the_demo_answer_makes_the_prototypes_nine_shots() -> None:
    shots = ops.normalize(_demo_answer(), _ctx())["shots"]
    assert len(shots) == 9
    assert shots[5]["line_ids"] == ["demo-b8", "demo-b10"]  # 1-06: the voice-over over the door
    assert [s["shot_type"] for s in shots][:2] == ["scene_change", "same_scene_cut"]
    assert shots[5]["shot_type"] == "scene_change"
    # 1-08 continues 1-06 over the insert 1-07; 1-09 continues 1-08.
    assert shots[7]["tail_from"] == shots[5]["id"]
    assert shots[8]["tail_from"] == shots[7]["id"]
    assert shots[7]["tail_note"] and shots[0]["tail_note"] is None
    assert shots[5]["audio_mode"] == "tts" and shots[0]["duration_s"] == 4
    assert {b["kind"] for b in shots[0]["blocking"]} == {"landmark", "prop", "character", "camera"}


def test_lines_the_model_left_out_are_filmed_anyway() -> None:
    """L8 (voice-over) lies over the shot before it; L3 (action) gets its own shot."""
    answer = {
        "shots": [
            {"lines": [1, 2], "type": "scene_change"},
            {"lines": [4, 5]},
            {"lines": [6, 7], "type": "scene_change"},
            {"lines": [9, 10]},
        ]
    }
    shots = ops.normalize(answer, _ctx())["shots"]
    assert _lines({"shots": shots}) == [
        ["demo-b2", "demo-b3"],
        ["demo-b4"],
        ["demo-b5", "demo-b6"],
        ["demo-b8", "demo-b9", "demo-b10"],
        ["demo-b11", "demo-b12"],
    ]
    assert shots[1]["intent"] == "line 3"  # a rule-made shot shows its action line


def test_a_spoken_line_is_in_one_shot_only() -> None:
    answer = {"shots": [{"lines": [1, 2, 3, 4]}, {"lines": [4, 5]}, {"lines": list(range(6, 11))}]}
    shots = ops.normalize(answer, _ctx())["shots"]
    assert shots[0]["line_ids"][-1] == "demo-b5"
    assert shots[1]["line_ids"] == ["demo-b6"]


def test_a_scene_never_opens_on_a_continuous_shot() -> None:
    answer = {
        "shots": [
            {"lines": [1, 2, 3, 4, 5], "type": "continuous"},
            {"lines": [6, 7, 8], "type": "continuous", "continues": 1},
            {"lines": [9, 10], "type": "continuous", "continues": 1},
        ]
    }
    shots = ops.normalize(answer, _ctx())["shots"]
    assert [s["shot_type"] for s in shots] == ["scene_change", "scene_change", "continuous"]
    # Asked to continue a shot of another scene: the last one of its own scene instead.
    assert shots[2]["tail_from"] == shots[1]["id"]


def test_a_continuous_shot_skips_an_insert() -> None:
    answer = {
        "shots": [
            {"lines": [6, 8], "framing": "medium", "refs": ["linwan", "room"]},
            {"lines": [7], "framing": "closeup", "refs": ["phone", "txt2"]},
            {"lines": [9, 10], "type": "continuous"},
        ]
    }
    ctx = _ctx()
    ctx.lines = [x for x in ctx.lines if x.n >= 6]
    ctx.scene_ids = ["demo-b7"]
    shots = ops.normalize(answer, ctx)["shots"]
    assert shots[2]["tail_from"] == shots[0]["id"]
    assert ops.is_insert(shots[1], ctx.characters)


def test_references_come_from_the_episode_or_the_rules() -> None:
    answer = {"shots": [{"lines": [1], "refs": ["linwan", "nobody"]}, {"lines": [2, 3, 4, 5]}]}
    ctx = _ctx()
    ctx.lines = [x for x in ctx.lines if x.n <= 5]
    ctx.scene_ids = ["demo-b1"]
    shots = ops.normalize(answer, ctx)["shots"]
    assert shots[0]["asset_ids"] == ["linwan"]
    # No references: the scene's place and what the analysis found on its lines.
    assert shots[1]["asset_ids"] == ["hall", "linwan", "vlinwan"]
    people = [b for b in shots[1]["blocking"] if b["kind"] == "character"]
    assert [(b["id"], b["label"]) for b in people] == [("linwan", "林晚")]


def test_a_rerun_keeps_the_ids_of_the_same_shots() -> None:
    ctx = _ctx()
    first = ops.normalize(_demo_answer(), ctx)
    again = ops.normalize(_demo_answer(), ctx, base=first)
    assert [s["id"] for s in again["shots"]] == [s["id"] for s in first["shots"]]
    assert again["shots"][7]["tail_from"] == first["shots"][5]["id"]
    # One shot fewer in scene 2: the others keep theirs.
    answer = _demo_answer()
    answer["shots"] = [s for s in answer["shots"] if s["lines"] != [7]]
    answer["shots"][-1]["continues"] = 7  # 1-09 still follows 1-08, now the model's 7th
    fewer = ops.normalize(answer, ctx, base=first)["shots"]
    # L7 left out: the rules give it a shot again, which keeps 1-07's id, so nothing moves.
    assert [s["id"] for s in fewer] == [s["id"] for s in first["shots"]]
    assert fewer[8]["tail_from"] == first["shots"][7]["id"]


def test_split_and_merge() -> None:
    payload = ops.normalize(_demo_answer(), _ctx())
    shots = payload["shots"]
    types = {LINE_ID[n]: TYPES.get(n, "action") for n in range(1, 11)}
    # 1-06 has two lines: one each.
    split, new_id = ops.split(payload, shots[5]["id"], types)
    after = split["shots"]
    assert len(after) == 10 and after[6]["id"] == new_id
    assert (after[5]["line_ids"], after[6]["line_ids"]) == (["demo-b8"], ["demo-b10"])
    # What continued 1-06 now continues its second half.
    assert after[8]["tail_from"] == new_id
    # A one-line dialogue shot: the line stays, the second half is a reaction shot.
    split, new_id = ops.split(payload, shots[3]["id"], types)
    assert split["shots"][4]["line_ids"] == [] and split["shots"][4]["duration_s"] == 2.0
    # A one-line action shot: both film it, half the seconds each.
    split, _ = ops.split(payload, shots[1]["id"], types)
    assert split["shots"][1]["line_ids"] == split["shots"][2]["line_ids"] == ["demo-b3"]
    assert split["shots"][1]["duration_s"] == 1.5
    with pytest.raises(ops.ShotEditError, match="split_point_invalid"):
        ops.split(payload, shots[5]["id"], types, after_line_id="demo-b10")
    order = {LINE_ID[n]: n for n in range(1, 11)}
    merged, gone = ops.merge(payload, shots[5]["id"], order)
    assert gone == shots[6]["id"] and len(merged["shots"]) == 8
    assert merged["shots"][5]["line_ids"] == ["demo-b8", "demo-b9", "demo-b10"]
    assert merged["shots"][5]["duration_s"] == 7
    with pytest.raises(ops.ShotEditError, match="no_next_shot"):
        ops.merge(payload, shots[4]["id"], order)  # the last shot of scene 1


def test_patch() -> None:
    payload = ops.normalize(_demo_answer(), _ctx())
    shots = payload["shots"]
    out = ops.patch(payload, shots[2]["id"], {"framing": "wide", "manual_s": 5.0})
    assert out["shots"][2]["framing"] == "wide" and out["shots"][2]["manual_s"] == 5.0
    with pytest.raises(ops.ShotEditError, match="invalid_value"):
        ops.patch(payload, shots[2]["id"], {"framing": "huge"})
    with pytest.raises(ops.ShotEditError, match="no_shot_to_continue"):
        ops.patch(payload, shots[0]["id"], {"shot_type": "continuous"})
    # Continuous again: it follows the last shot before it that is not an insert (1-02 → 1-01).
    out = ops.patch(payload, shots[1]["id"], {"shot_type": "continuous"}, {"linwan"})
    assert out["shots"][1]["tail_from"] == shots[0]["id"]
