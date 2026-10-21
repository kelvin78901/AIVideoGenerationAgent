"""Asset analysis without the database (``assets/ops.py``): rules, the model's extras, ids."""

from __future__ import annotations

from drama_series_agent.assets import ops

BIBLE = {
    "entities": [
        {"id": "c-a", "kind": "character", "name": "阿青", "data": {"age": "20 岁"}},
        {"id": "c-b", "kind": "character", "name": "老周"},
        {"id": "l-1", "kind": "location", "name": "码头"},
        {"id": "l-2", "kind": "location", "name": "茶馆"},
        {"id": "p-1", "kind": "prop", "name": "铜铃", "aliases": ["铃"]},
        {"id": "p-2", "kind": "prop", "name": "旧船票"},
    ]
}
SCRIPT = {
    "scenes": [
        {
            "id": "s1",
            "location_id": "l-1",
            "time_of_day": "dawn",
            "lines": [
                {"id": "x1", "type": "action", "character_id": "c-a",
                 "text": "阿青摇了摇铜铃，又掏出旧船票。"},
                {"id": "x2", "type": "dialogue", "character_id": "c-a", "text": "船来了吗？"},
                {"id": "x3", "type": "action", "text": "招牌上写着“平安渡”。"},
            ],
        },
        {
            "id": "s2",
            "location_id": "l-1",
            "time_of_day": "dawn",
            "lines": [{"id": "x4", "type": "vo", "character_id": "c-b", "text": "铃声响了。"}],
        },
    ]
}  # fmt: skip


def test_rules_find_cast_voices_scenes_and_props_with_where() -> None:
    found = {f.key: f for f in ops.collect(SCRIPT, BIBLE)}
    assert list(found) == [
        "scene:l-1:dawn", "character:c-a", "prop:p-1", "prop:p-2", "voice:c-a",
        "character:c-b", "voice:c-b",
    ]  # fmt: skip
    assert found["scene:l-1:dawn"].name == "码头 · 清晨"
    assert found["scene:l-1:dawn"].uses == {"s1": [], "s2": []}  # one asset, two scenes
    assert found["character:c-a"].description == "20 岁"
    assert found["voice:c-a"].uses == {"s1": ["x2"]}  # only where they speak
    assert found["prop:p-1"].uses == {"s1": ["x1"], "s2": ["x4"]}  # by alias too
    assert "voice:c-b" in found  # voice-over counts as speaking


def test_the_answer_adds_descriptions_and_extras() -> None:
    lines = ops.numbered_lines(SCRIPT)
    answer = {
        "assets": [
            {"key": "character:c-a", "name": "阿青（少女）", "description": "瘦，短发。"},
            {"kind": "text", "name": "渡口招牌", "text": {"exact": "平安渡", "style": "printed",
             "method": "model"}, "lines": [3, 99]},
            {"kind": "text", "name": "没字的"},  # no exact text: dropped
            {"kind": "prop", "name": "铜铃"},  # already listed: joins it
            {"kind": "voice", "name": "老周", "description": "沙哑。"},
            {"kind": "scene", "name": "茶馆 · 夜", "note": "第 2 集"},
        ]
    }  # fmt: skip
    merged = {f.key: f for f in ops.merge(ops.collect(SCRIPT, BIBLE), answer, lines, BIBLE)}
    assert merged["character:c-a"].description == "瘦，短发。"
    assert merged["character:c-a"].name == "阿青（少女）"
    sign = merged["text:name:渡口招牌"]
    assert sign.text == {"exact": "平安渡", "style": "printed", "method": "model"}
    assert sign.uses == {"s1": ["x3"]}  # an unknown line number is ignored
    assert not any(f.kind == "text" and f.name == "没字的" for f in merged.values())
    assert merged["voice:c-b"].description == "沙哑。"  # a voice is its character's
    assert merged["scene:l-2:night"].note == "第 2 集" and merged["scene:l-2:night"].uses == {}
    assert sum(1 for f in merged.values() if f.kind == "prop") == 2


def test_ids_carry_over_by_key_or_name() -> None:
    found = ops.collect(SCRIPT, BIBLE)
    known = [
        {"id": "a-qing", "key": "character:c-a", "kind": "character", "name": "x"},
        {"id": "a-bell", "key": "prop:old", "kind": "prop", "name": "铜铃"},
    ]
    assets = {a["key"]: a for a in ops.reconcile(found, known)}
    assert assets["character:c-a"]["id"] == "a-qing"
    assert assets["prop:p-1"]["id"] == "a-bell"
    fresh = [a["id"] for k, a in assets.items() if k not in ("character:c-a", "prop:p-1")]
    assert all(i.startswith("a-") for i in fresh) and len(set(fresh)) == len(fresh)
    assert assets["scene:l-1:dawn"]["uses"] == [
        {"scene_id": "s1", "line_ids": []}, {"scene_id": "s2", "line_ids": []}
    ]  # fmt: skip
