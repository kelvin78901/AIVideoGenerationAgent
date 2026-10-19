"""``suggestions.ops``: how a rerun carries decisions over, and what downstream reads."""

from __future__ import annotations

from itertools import count
from typing import Any

from drama_series_agent.suggestions import ops


def _span(idx: int, source: str = "src") -> dict[str, Any]:
    return {"source_id": source, "start": idx * 10, "end": idx * 10 + 5}


def _s(sid: str, para: int, kind: str, text: str, reason: str = "") -> dict[str, Any]:
    return {"id": sid, "kind": kind, "para_idx": para, "anchor_span": _span(para),
            "reason": reason, "text": text}  # fmt: skip


def _found(para: int, kind: str, text: str) -> dict[str, Any]:
    return {k: v for k, v in _s("", para, kind, text, "新理由").items() if k != "id"}


def _ids() -> Any:
    n = count(1)
    return lambda: f"new{next(n)}"


def test_additions_are_the_accepted_ones_with_their_final_text() -> None:
    payload = {"suggestions": [_s("a", 0, "lighting", "灯"), _s("b", 1, "gap", "缺"),
                               _s("c", 1, "motive", "因为")]}  # fmt: skip
    decisions = {
        "a": {"status": "accepted", "text": None},
        "b": {"status": "rejected", "text": None},
        "c": {"status": "accepted", "text": "改写后"},
    }
    assert ops.additions(payload, decisions) == [
        {"id": "a", "para_idx": 0, "anchor_span": _span(0), "text": "灯"},
        {"id": "c", "para_idx": 1, "anchor_span": _span(1), "text": "改写后"},
    ]
    assert ops.by_paragraph(ops.additions(payload, decisions)) == {0: ["灯"], 1: ["改写后"]}
    assert ops.additions(payload, {}) == []


def test_reconcile_keeps_accepted_and_reuses_ids_for_the_same_text() -> None:
    base = [_s("a", 0, "appearance", "米色风衣"), _s("b", 0, "lighting", "声控灯"),
            _s("c", 2, "gap", "旧的")]  # fmt: skip
    decisions = {"a": {"status": "accepted"}, "b": {"status": "rejected"}}
    found = [
        _found(0, "appearance", "工装外套"),  # same slot as an accepted one: a repeat
        _found(0, "lighting", "声 控 灯"),  # same text (spaces aside): keeps id b (ignored)
        _found(1, "cliffhanger", "23:52"),  # new
        _found(1, "cliffhanger", "23:52"),  # a duplicate in the same answer
    ]
    out = ops.reconcile(found, base, decisions, _ids())
    assert [(s["id"], s["para_idx"], s["text"]) for s in out] == [
        ("a", 0, "米色风衣"), ("b", 0, "声 控 灯"), ("new1", 1, "23:52"),
    ]  # fmt: skip
    assert out[1]["reason"] == "新理由"  # the rerun's reason for a kept id


def test_reanchor_follows_paragraph_text() -> None:
    base = [_s("a", 1, "lighting", "灯"), _s("b", 3, "gap", "缺")]
    old = {0: "第一段", 1: "第二段", 2: "第三段", 3: "第四段"}
    # A paragraph inserted at the top; the fourth one rewritten.
    new = {0: "新开头", 1: "第一段", 2: "第二段", 3: "第三段", 4: "第四段改了"}
    out = ops.reanchor(base, old.__getitem__, new, lambda i: _span(i, "src2"))
    assert [(s["id"], s["para_idx"], s["anchor_span"]["source_id"]) for s in out] == [
        ("a", 2, "src2"),
    ]
    assert ops.reanchor(base, None, new, _span) == []


def test_reanchor_picks_the_nearest_repeat() -> None:
    base = [_s("a", 4, "lighting", "灯")]
    old = {4: "“嗯。”"}
    new = {0: "“嗯。”", 3: "别的", 5: "“嗯。”"}
    [moved] = ops.reanchor(base, old.__getitem__, new, _span)
    assert moved["para_idx"] == 5
