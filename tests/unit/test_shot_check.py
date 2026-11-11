"""分镜检查 by rules (M5.5): run 17's problems read off the plan."""

from __future__ import annotations

from typing import Any

from test_shot_ops import KINDS, _ctx, _demo_answer

from drama_series_agent.shots import check, ops


def _lines() -> dict[str, check.LineInfo]:
    """The demo's episode 1, the words that matter to the rules."""
    texts = {
        "demo-b11": "她拉开门，又关上。停两秒，再拉开。",
        "demo-b10": "三年了。他凭什么。",
    }
    ctx = _ctx()
    return {
        x.line_id: check.LineInfo(x.type, texts.get(x.line_id, x.text), "OS" if x.n == 8 else "")
        for x in ctx.lines
    }


def _found(shots: list[dict[str, Any]]) -> list[tuple[str, str]]:
    labels = check.labels(1, shots)
    lines = _lines()
    contracts = check.contracts_of(shots, lines, KINDS)
    return [(labels[i.shot_id], i.code) for i in check.check(shots, labels, lines, contracts)]


def test_run17s_door_and_replay_are_found_in_the_demo_plan() -> None:
    shots = ops.normalize(_demo_answer(), _ctx())["shots"]
    assert ("1-08", "undone") in _found(shots) and ("1-08", "replay") in _found(shots)


def test_a_picture_the_user_wrote_is_read_without_the_scripts_action_lines() -> None:
    """Kelvin 2026-11-10 (run 19): the video reads the user's picture alone, so does the rule."""
    shots = ops.normalize(_demo_answer(), _ctx())["shots"]
    shots[7] = {**shots[7], "intent": "她握着门把，停了两秒，拉开门。", "picture_edited": True}
    assert ("1-08", "undone") not in _found(shots)
    shots[7] = {**shots[7], "picture_edited": False}  # as planned: the script's line counts
    assert ("1-08", "undone") in _found(shots)


def test_undone_reads_a_change_made_undone_and_made_again() -> None:
    assert check.undone("她拉开门，又关上。停两秒，再拉开。") == ["拉开", "关上", "拉开"]
    assert check.undone("她拿起伞，放下，又拿起来") == ["拿起", "放下", "拿起"]
    assert check.undone("她拉开门，望向门外") is None
    assert check.undone("她关上门，背靠着门") is None
    assert check.undone("拉开门走出去，关上门") is None  # opened and shut once: fine


def test_an_insert_where_something_happens() -> None:
    shots = ops.normalize(_demo_answer(), _ctx())["shots"]
    shots[2] = {**shots[2], "intent": "便利贴特写，雨水把字一点点泡开"}
    assert ("1-03", "insert_event") in _found(shots)


def test_an_inner_voice_that_talks() -> None:
    shots = ops.normalize(_demo_answer(), _ctx())["shots"]
    shots[5] = {**shots[5], "intent": "林晚背靠着门，低声说出心里的话"}
    assert ("1-06", "inner_mouth") in _found(shots)


def test_a_continuous_shot_that_starts_unlike_the_one_it_follows_ends() -> None:
    shots = ops.normalize(_demo_answer(), _ctx())["shots"]
    contract = {**shots[7]["contract"], "start": [{"subject": "家门", "state": "关着"}]}
    shots[7] = {**shots[7], "contract": contract}  # 1-06 ends with the door shut: fine
    assert ("1-08", "state_jump") not in _found(shots)
    contract = {**contract, "start": [{"subject": "家门", "state": "开着"}]}
    shots[7] = {**shots[7], "contract": contract}
    assert ("1-08", "state_jump") in _found(shots)


def test_a_moving_camera_or_another_framing_is_no_replay() -> None:
    shots = ops.normalize(_demo_answer(), _ctx())["shots"]
    shots[7] = {**shots[7], "camera_move": "push"}
    assert ("1-08", "replay") not in _found(shots)
    shots[7] = {**shots[7], "camera_move": "static", "framing": "close"}
    assert ("1-08", "replay") not in _found(shots)


def test_someone_outside_the_shots_place_is_found() -> None:
    """Run 19's 1-06, in 林晚出租屋, started 「站在门外」: the keyframe put the camera in the
    stairwell and the take shut her out. A passage the other way round: 屋里 from the stairwell."""
    shots = ops.normalize(_demo_answer(), _ctx())["shots"]
    door = shots[5]
    door["contract"]["start"] = [{"subject": "林晚", "state": "站在门外，伞靠在墙边"}]
    places = {door["scene_id"]: "林晚出租屋", shots[0]["scene_id"]: "老小区楼道 · 六楼林晚家门口"}
    shots[0]["contract"]["end"] = [{"subject": "林晚", "state": "已经进了屋里"}]
    labels = check.labels(1, shots)
    lines = _lines()
    contracts = check.contracts_of(shots, lines, KINDS)
    found = [
        (labels[i.shot_id], i.params)
        for i in check.check(shots, labels, lines, contracts, places)
        if i.code == "cross_space"
    ]
    assert found == [
        ("1-01", {"words": "屋里", "place": "老小区楼道 · 六楼林晚家门口"}),
        ("1-06", {"words": "门外", "place": "林晚出租屋"}),
    ]
    # Her back to the door, or looking out (1-08: 「望向门外地上」), is not being outside.
    for state in ("背靠着门", "站在门口，望向门外地上"):
        assert check.cross_space("林晚出租屋", [{"subject": "林晚", "state": state}]) is None


def test_a_doorway_and_more_in_one_shot_is_crowded() -> None:
    """Run 19's 1-06 pushed the door, came in, turned, shut it and leant on it in six seconds:
    the door went through her. The demo's 1-06 is the same shot."""
    shots = ops.normalize(_demo_answer(), _ctx())["shots"]
    assert _found(shots) == [("1-06", "crowded"), ("1-08", "undone"), ("1-08", "replay")]
    run19 = ["她推门", "进门", "转身", "关门", "靠门"]
    assert check.crowded("、".join(run19)) == run19
    assert check.crowded("她放下包，脱下外套，坐下，拿起手机") is not None  # four, no door
    # Going through alone, the door opened for it, or a place someone is in: fine.
    fine = ("她推门进来", "她推开门，走进屋", "伞斜靠在墙边", "她拉开门，又关上；停两秒，再拉开")
    for text in fine:
        assert check.crowded(text) is None
    # Start outside, end inside: through the doorway even when the words do not say it.
    crossing = {"start": [{"state": "站在门外"}], "end": [{"state": "在屋里，背靠着门"}]}
    assert check.crowded("她反手关上门", crossing) == ["她反手关上门"]
    assert check.crowded("她反手关上门") is None
