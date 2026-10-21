"""An episode's script as data (``script.ops``) and the pure parts of 剧本化
(``pipeline/components/script.py``): ids across reruns, numbering, edits, reading the answer."""

from __future__ import annotations

import itertools
from typing import Any

import pytest

from drama_series_agent.modelhub.adapters.base import ModelRequest
from drama_series_agent.pipeline.components import script as comp
from drama_series_agent.script import ops


def _ids(prefix: str) -> Any:
    counter = itertools.count(1)
    return lambda: f"{prefix}{next(counter)}"


def _line(text: str, **extra: Any) -> dict[str, Any]:
    return {"type": "action", "text": text, "paras": [], **extra}


BASE = {
    "scenes": [
        {"id": "s1", "heading": "夜　内　楼道", "lines": [
            {"id": "a", "type": "action", "text": "声控灯坏了一半，忽明忽暗。"},
            {"id": "b", "type": "dialogue", "text": "……周屿？"},
        ]},
        {"id": "s2", "heading": "夜　内　出租屋", "lines": [
            {"id": "c", "type": "action", "text": "她拉开门，又关上。"},
            {"id": "d", "type": "action", "text": "门外，她拿起了那把伞。"},
        ]},
    ]
}  # fmt: skip


def test_reconcile_keeps_scene_ids_by_order_and_line_ids_by_text() -> None:
    found = [
        {"heading": "夜　内　六楼楼道", "lines": [_line("她拉开门，又关上。"), _line("……周屿？")]},
        {"heading": "夜　内　出租屋",
         "lines": [_line("门外，她终于拿起了那把伞。"), _line("新的一行")]},
        {"heading": "日　外　楼下", "lines": [_line("雨停了。")]},
    ]  # fmt: skip
    out = ops.reconcile(found, BASE, _ids("S"), _ids("L"))
    assert [s["id"] for s in out] == ["s1", "s2", "S1"]
    # Same text anywhere (c moved to scene 1), then similar in the scene with this number.
    assert [[x["id"] for x in s["lines"]] for s in out] == [["c", "b"], ["d", "L1"], ["L2"]]
    assert ops.reconcile(found[:1], None, _ids("S"), _ids("L"))[0]["id"] == "S1"


def test_view_numbers_scenes_across_the_series_and_lines_in_reading_order() -> None:
    scenes, lines = ops.view(BASE, 3)
    assert [(s["id"], s["idx"], s["edited"]) for s in scenes] == [
        ("s1", 3, False), ("s2", 4, False),
    ]  # fmt: skip
    assert "lines" not in scenes[0]
    assert [(x["id"], x["scene_id"], x["idx"]) for x in lines] == [
        ("a", "s1", 1), ("b", "s1", 2), ("c", "s2", 4), ("d", "s2", 5),
    ]  # fmt: skip


def test_edits_mark_what_they_changed() -> None:
    out = ops.patch_line(BASE, "b", text=" ……是你？ ")
    assert ops.find_line(out, "b") == (out["scenes"][0], out["scenes"][0]["lines"][1])
    assert out["scenes"][0]["lines"][1] == {
        "id": "b", "type": "dialogue", "text": "……是你？", "edited": True,
    }  # fmt: skip
    assert "edited" not in BASE["scenes"][0]["lines"][1]  # a copy
    assert ops.patch_line(BASE, "b", text="……周屿？") == BASE  # unchanged: not edited
    out = ops.patch_scene(BASE, "s2", heading="场 2　夜　内　门内")
    assert (out["scenes"][1]["heading"], out["scenes"][1]["edited"]) == ("夜　内　门内", True)
    for fn, code in (
        (lambda: ops.patch_line(BASE, "nope", text="x"), "line_not_found"),
        (lambda: ops.patch_line(BASE, "a", text="  "), "line_empty"),
        (lambda: ops.patch_scene(BASE, "a", heading="x"), "scene_not_found"),
        (lambda: ops.patch_scene(BASE, "s1", heading="场 3"), "heading_empty"),
    ):
        with pytest.raises(ops.ScriptEditError) as err:
            fn()
        assert err.value.code == code


def test_plain_heading() -> None:
    assert ops.plain_heading("场 12　夜　内　出租屋") == "夜　内　出租屋"
    assert ops.plain_heading("场12：日　外　街口") == "日　外　街口"
    assert ops.plain_heading("夜　内　场院") == "夜　内　场院"


# --------------------------------------------------------------------------- the answer

NAMES: comp.Names = [
    ("character", "c-linwan", {"林晚"}),
    ("character", "c-clerk", {"便利店店员", "店员"}),
    ("location", "l-store", {"楼下便利店", "便利店"}),
    ("location", "l-flat", {"林晚出租屋"}),
]


def test_resolve_names_and_places() -> None:
    assert comp.resolve(NAMES, "character", "林晚") == "c-linwan"
    assert comp.resolve(NAMES, "character", "林晚（OS）") == "c-linwan"
    assert comp.resolve(NAMES, "character", "店员") == "c-clerk"
    assert comp.resolve(NAMES, "location", "夜　外　便利店门口") == "l-store"
    assert comp.resolve(NAMES, "location", "夜　内　林晚出租屋") == "l-flat"
    assert comp.resolve(NAMES, "character", "周屿") is None
    assert comp.resolve(NAMES, "location", "") is None


class _Book:
    class source:
        id = "src"

    def span(self, idx: int) -> dict[str, Any] | None:
        return {"source_id": "src", "start": idx * 10, "end": idx * 10 + 9}


def test_collect_reads_paragraphs_additions_and_the_cliffhanger() -> None:
    context = {
        "book": _Book(),
        "paras": [3, 4],
        "additions": {1: {"id": "s9", "para_idx": 4, "text": "手机亮了一下。"}},
        "names": NAMES,
    }
    answer = comp.ScriptAnswer.model_validate(
        {
            "scenes": [
                {"heading": "场 1 夜　内　林晚出租屋", "time": "夜", "paras": ["P4", 9], "lines": [
                    {"type": "动作", "character": "林晚", "text": "她靠着门。", "seconds": "5秒",
                     "paras": [4, 7], "cliffhanger": True},
                    {"type": "OS", "who": "林晚", "tone": "OS", "text": "三年了。",
                     "added": "true"},
                    {"type": "action", "text": "  "},
                    {"type": "sfx", "text": "嗡——", "paras": [5], "adds": [1, 1, 2],
                     "cliffhanger": True},
                ]},
                {"heading": "", "time": "dusk", "location": "便利店", "lines": []},
                {"time": "dawn", "location": "便利店", "lines": [{"text": "天亮了。"}]},
            ]
        }
    )  # fmt: skip
    scenes = comp.collect(answer, context)
    s1, s2 = scenes
    assert (s1["heading"], s1["time_of_day"], s1["location_id"], s1["paras"]) == (
        "夜　内　林晚出租屋", "night", "l-flat", [3],
    )  # fmt: skip
    a, b, c = s1["lines"]
    assert (a["type"], a["character_id"], a["duration_s"], a["paras"]) == (
        "action",
        "c-linwan",
        5,
        [3],
    )
    assert (b["type"], b["character_name"], b["ai_added"], b["paras"]) == ("vo", "林晚", True, [])
    # An addition: its paragraph and a ``sug:`` span (unknown numbers dropped, repeats once).
    assert c["paras"] == [4]
    assert c["source_spans"] == [
        {"source_id": "src", "start": 40, "end": 49},
        {"source_id": "sug:s9", "start": 0, "end": 7},
    ]
    # Only the last line the model marked is the 卡点.
    assert [a["cliffhanger"], c["cliffhanger"]] == [False, True]
    # No heading: time and place; no paragraphs: none.
    assert (s2["heading"], s2["location_id"], s2["paras"]) == ("晨　便利店", "l-store", [])
    assert s2["lines"][0]["cliffhanger"] is False
    # Nothing marked: the last line.
    plain = comp.ScriptAnswer.model_validate(
        {"scenes": [{"lines": [{"text": "x"}, {"text": "y"}]}]}
    )
    assert [x["cliffhanger"] for x in comp.collect(plain, context)[0]["lines"]] == [False, True]


def _request(text: str) -> ModelRequest:
    return ModelRequest(kind="llm", messages=[{"role": "user", "content": text}])


def test_mock_rules_for_any_other_episode() -> None:
    text = "\n".join(
        [
            "[本集]", "第 2 集《转折》", "预计时长：60 秒；预计场数：2", "",
            "[节拍]", "1. 老陈进门（P8）", "2. 两人争执（P9、P10）", "3. 摔门而去（P11）", "",
            "[设定]", "人物「老陈」", "地点「茶馆」", "",
            "[原文]", "[第 2 章] 转折",
            "[P8] 老陈推开茶馆的门。",
            "[P9] “你来晚了。”老板说。【补写1】茶已经凉了。",
            "[P10] 老陈没说话。",
            "[P11] 老陈摔门走了。",
        ]
    )  # fmt: skip
    answer = comp.mock_script(_request(text))
    scenes = answer["scenes"]
    assert [(s["heading"], s["paras"]) for s in scenes] == [
        ("日　内　茶馆", [8, 9, 10]), ("日　内　场景", [11]),
    ]  # fmt: skip
    lines = scenes[0]["lines"]
    assert lines[2] == {"type": "dialogue", "character": "", "text": "你来晚了。", "seconds": 3,
                        "paras": [9]}  # fmt: skip
    assert lines[3]["adds"] == [1] and lines[3]["text"] == "茶已经凉了。"
    assert scenes[-1]["lines"][-1]["cliffhanger"] is True
    # The rewrites: a line's content, a heading.
    line = comp.mock_rewrite_line(
        _request("[本场]\n日　内　茶馆\n\n[这一行]\n类型：动作\n内容：老陈推门。")
    )
    assert line == {"text": "老陈推门——换个说法。"}
    assert comp.mock_rewrite_scene(_request("[场景标题]\n日　内　茶馆")) == {
        "text": "日　内　茶馆 · 另一角"
    }
