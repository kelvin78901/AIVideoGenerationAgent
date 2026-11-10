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
    assert _found(shots) == [("1-08", "undone"), ("1-08", "replay")]


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
