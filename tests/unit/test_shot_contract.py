"""镜头契约 (M5.5): the plan's answer turned into a contract, the rules filling what the model
left out, the user's edits checked, a continuous shot starting where the one it follows ends."""

from __future__ import annotations

import pytest
from test_shot_ops import KINDS, _ctx, _demo_answer

from drama_series_agent.shots import contract, ops

NAMES = {"umbrella": "红色长柄伞", "note": "黄色便利贴"}


def _spoken(*pairs: tuple[str, str, str]) -> list[contract.SpokenLine]:
    return [contract.SpokenLine(i, n, t, tone) for n, (i, t, tone) in enumerate(pairs, 1)]


def test_the_demo_plan_carries_its_contracts() -> None:
    shots = ops.normalize(_demo_answer(), _ctx())["shots"]
    kinds = [s["contract"]["kind"] for s in shots]
    assert kinds == [
        "performance",
        "insert",
        "insert",
        "dialogue",
        "performance",
        "performance",
        "insert",
        "performance",
        "performance",
    ]
    assert shots[1]["contract"]["beats"] == 0
    assert shots[1]["contract"]["props"][0] == {
        "asset_id": "umbrella",
        "state": "斜靠在门边墙上，伞面湿",
    }
    assert shots[3]["contract"]["delivery"] == {"demo-b5": "dialogue"}
    assert shots[5]["contract"]["delivery"] == {"demo-b10": "inner"}
    assert shots[7]["contract"]["start"] == []  # 1-08 starts where 1-06 ends


def test_rules_fill_what_the_model_left_out() -> None:
    lines = _spoken(("a", "dialogue", ""), ("b", "vo", "OS"), ("c", "vo", "电话里"))
    c = contract.build({}, lines, ["linwan"], KINDS)
    assert c["kind"] == "dialogue" and c["beats"] == 2
    assert c["delivery"] == {"a": "dialogue", "b": "inner", "c": "offscreen"}
    assert contract.build({}, [], ["note"], KINDS)["kind"] == "insert"
    assert contract.build({}, [], ["linwan"], KINDS)["kind"] == "performance"


def test_an_insert_with_someone_in_it_is_not_an_insert() -> None:
    assert contract.build({"kind": "insert"}, [], ["linwan"], KINDS)["kind"] == "performance"
    talking = _spoken(("a", "dialogue", ""))
    assert contract.build({"kind": "insert"}, talking, [], KINDS)["kind"] == "dialogue"


def test_beats_are_kept_within_the_kinds_budget() -> None:
    assert contract.build({"kind": "insert", "beats": 3}, [], ["note"], KINDS)["beats"] == 0
    assert contract.build({"kind": "performance", "beats": 5}, [], ["linwan"], KINDS)["beats"] == 2
    assert contract.build({"kind": "action", "beats": 0}, [], ["linwan"], KINDS)["beats"] == 1
    assert contract.build({"kind": "action"}, [], ["linwan"], KINDS)["beats"] == 4


def test_states_and_props_are_cleaned() -> None:
    raw = {
        "start": {"家门": "关着", "": "x"},
        "end": [{"subject": "家门", "state": "开着"}, {"subject": "林晚"}, "junk"],
        "props": [
            {"asset_id": "红色长柄伞", "state": "靠在墙边"},  # by name
            {"asset_id": "note", "state": ""},  # no state
            {"asset_id": "linwan", "state": "站着"},  # not a prop
            {"asset_id": "band", "state": "在手腕上"},  # not one of the shot's references
        ],
    }
    c = contract.build(raw, [], ["linwan", "umbrella", "note"], KINDS, NAMES)
    assert c["start"] == [{"subject": "家门", "state": "关着"}]
    assert c["end"] == [{"subject": "家门", "state": "开着"}]
    assert c["props"] == [{"asset_id": "umbrella", "state": "靠在墙边"}]


def test_the_model_names_lines_by_their_number() -> None:
    lines = [contract.SpokenLine("demo-b10", 8, "vo", "")]
    c = contract.build({"delivery": {"L8": "inner", "L9": "dialogue"}}, lines, [], KINDS)
    assert c["delivery"] == {"demo-b10": "inner"}


def test_patch_checks_values() -> None:
    old = contract.build({"kind": "action", "beats": 3}, _spoken(("a", "vo", "")), ["note"], KINDS)
    new = contract.patch(old, {"kind": "performance"}, ["a"], ["note"], KINDS)
    assert new["kind"] == "performance" and new["beats"] == 2
    assert contract.patch(old, {"kind": "insert"}, ["a"], ["note"], KINDS)["beats"] == 0
    new = contract.patch(old, {"delivery": {"a": "inner"}}, ["a"], ["note"], KINDS)
    assert new["delivery"] == {"a": "inner"}
    for bad in (
        {"kind": "dance"},
        {"beats": 9},
        {"delivery": {"zz": "inner"}},
        {"delivery": {"a": "sing"}},
        {"props": [{"asset_id": "linwan", "state": "x"}]},
        {"start": [{"subject": "门", "state": ""}]},
        {"mood": "x"},
    ):
        with pytest.raises(contract.ContractError):
            contract.patch(old, bad, ["a"], ["note"], KINDS)


def test_a_continuous_shot_starts_where_the_one_it_follows_ends() -> None:
    shots = ops.normalize(_demo_answer(), _ctx())["shots"]
    by_id = {s["id"]: s for s in shots}
    c = contract.effective(shots[7], [], KINDS, by_id)
    assert c["start_inherited"] is True
    assert c["start"] == shots[5]["contract"]["end"]
    assert contract.effective(shots[5], [], KINDS, by_id)["start_inherited"] is False


def test_an_old_plan_gets_the_default_contract() -> None:
    shot = {"asset_ids": ["linwan"], "shot_type": "same_scene_cut"}
    lines = _spoken(("a", "vo", "OS"))
    c = contract.effective(shot, lines, KINDS)
    assert c["kind"] == "performance" and c["delivery"] == {"a": "inner"}


def test_patching_references_drops_props_no_longer_referenced() -> None:
    payload = ops.normalize(_demo_answer(), _ctx())
    shot = payload["shots"][1]  # 1-02: hall, umbrella, note
    out = ops.patch(payload, shot["id"], {"asset_ids": ["hall", "note"]})
    props = ops.find_shot(out, shot["id"])["contract"]["props"]  # type: ignore[index]
    assert [p["asset_id"] for p in props] == ["note"]
