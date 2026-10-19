"""The story bible as data (``bible/merge.py``): grouping, ids across reruns, edits."""

from __future__ import annotations

from typing import Any

import pytest

from drama_series_agent.bible import merge as ops
from drama_series_agent.bible.merge import Found

TEXT = {0: "林晚回家。", 1: "阿晚撑着红伞。", 2: "周屿和阿晚。", 3: "红色长柄伞。"}


def span_of(idx: int) -> dict[str, Any] | None:
    return {"source_id": "s", "start": idx * 10, "end": idx * 10 + 5} if idx in TEXT else None


def ids_from(*names: str) -> Any:
    it = iter(names)
    return lambda kind: next(it)


def test_normalize_ignores_spacing_punctuation_and_width() -> None:
    assert (
        ops.normalize(" 老小区楼道（六楼） ")
        == ops.normalize("老小区楼道(六楼)")
        == "老小区楼道六楼"
    )
    assert ops.normalize("Lin·Wan") == "linwan"


def test_group_merges_shared_names_of_one_kind_in_order() -> None:
    found = [
        Found("character", "林晚", summary="插画师", paras=[0]),
        Found("prop", "红伞", paras=[1]),
        Found("character", "阿晚", ["林晚"], details={"age": "26"}, paras=[1, 2]),
        Found("location", "林晚", paras=[0]),  # another kind: not merged
        Found("prop", "红色长柄伞", ["红伞"], summary="缠着铁丝", paras=[3]),
    ]
    groups = ops.group(found)
    assert [(g.kind, g.name) for g in groups] == [
        ("character", "林晚"), ("prop", "红伞"), ("location", "林晚"),
    ]  # fmt: skip
    linwan, umbrella = groups[0], groups[1]
    assert linwan.aliases == ["阿晚"] and linwan.paras == [0, 1, 2]
    assert (linwan.summary, linwan.details) == ("插画师", {"age": "26"})
    assert umbrella.aliases == ["红色长柄伞"] and umbrella.summary == "缠着铁丝"


def test_reconcile_keeps_ids_frozen_entries_and_user_merges() -> None:
    base = {
        "entities": [
            {"id": "c-1", "kind": "character", "name": "林晚", "aliases": ["阿晚"]},
            {
                "id": "c-2", "kind": "character", "name": "周屿", "aliases": [],
                "data": {"summary": "改过"}, "paras": [2], "source_spans": [], "frozen": True,
            },
            {"id": "p-9", "kind": "prop", "name": "旧物", "aliases": []},
        ],
        "distinct": [["c-1", "c-2"], ["c-1", "p-9"]],
    }  # fmt: skip
    groups = [
        Found("character", "阿晚", paras=[1]),  # matches c-1 by its alias
        Found("character", "周屿", summary="新的", paras=[2]),  # frozen: dropped
        Found("character", "林晚", paras=[0]),  # also c-1 (the user merged them): one entry
        Found("prop", "红伞", paras=[1]),
    ]
    entities, distinct = ops.reconcile(groups, base, span_of, ids_from("p-new"))
    by_id = {e["id"]: e for e in entities}
    assert list(by_id) == ["c-1", "c-2", "p-new"]  # kind, then first paragraph
    # The adopted name stays the name even though the alias came first this time.
    assert by_id["c-1"]["name"] == "林晚" and by_id["c-1"]["aliases"] == ["阿晚"]
    assert by_id["c-1"]["paras"] == [0, 1] and len(by_id["c-1"]["source_spans"]) == 2
    assert by_id["c-2"] == base["entities"][1]  # exactly as it was
    assert distinct == [["c-1", "c-2"]]  # p-9 is gone


def test_candidates_and_suggestions() -> None:
    entities = [
        {"id": "p-1", "kind": "prop", "name": "旧发圈", "aliases": []},
        {"id": "p-2", "kind": "prop", "name": "黑色发圈", "aliases": []},
        {"id": "p-3", "kind": "prop", "name": "旧小票", "aliases": []},
        {"id": "r-1", "kind": "relation", "name": "旧发圈 — 黑色发圈", "aliases": []},
    ]
    pairs = ops.candidates(entities, [["p-3", "p-1"]])
    assert [(a["id"], b["id"]) for a, b in pairs] == [("p-1", "p-2")]  # relations are skipped
    out = ops.suggestions(pairs, [(1, True, "同一根"), (2, True, "out of range")])
    assert out == [{"id": ops.suggestion_id(["p-2", "p-1"]), "kind": "prop", "ids": ["p-1", "p-2"],
                    "reason": "同一根"}]  # fmt: skip
    assert ops.suggestions(pairs, [(1, False, "")]) == []


def _payload() -> dict[str, Any]:
    entities, _ = ops.reconcile(
        [
            Found("character", "林晚", ["阿晚"], summary="插画师", paras=[0, 1, 2]),
            Found("prop", "红伞", paras=[1]),
            Found("prop", "红色长柄伞", paras=[3]),
        ],
        None,
        span_of,
        ids_from("c-1", "p-1", "p-2"),
    )
    return {
        "source_id": "s",
        "entities": entities,
        "merge_suggestions": [{"id": "m", "kind": "prop", "ids": ["p-1", "p-2"], "reason": ""}],
        "distinct": [],
    }


def test_patch() -> None:
    payload = _payload()
    out = ops.patch(payload, "c-1", name=" 阿晚 ", data={"age": "26"}, frozen=True)
    e = ops.find(out, "c-1")
    assert e is not None
    # The old name becomes an alias, so the next extraction still finds the entry.
    assert (e["name"], e["aliases"], e["data"], e["frozen"]) == (
        "阿晚",
        ["林晚"],
        {"age": "26", "summary": ""},
        True,
    )
    renamed = ops.find(ops.patch(payload, "c-1", name="林晚晚", aliases=[]), "c-1")
    assert renamed is not None and renamed["aliases"] == []  # aliases sent: taken as they are
    assert ops.find(payload, "c-1")["name"] == "林晚"  # type: ignore[index]  # not changed in place
    with pytest.raises(ops.BibleEditError, match="name_required"):
        ops.patch(payload, "c-1", name=" ")
    with pytest.raises(ops.BibleEditError, match="entity_not_found"):
        ops.patch(payload, "nope", frozen=True)


def test_merge_and_distinct() -> None:
    merged = ops.merge(_payload(), ["p-2", "p-1"])
    assert [e["id"] for e in merged["entities"]] == ["c-1", "p-2"]
    keep = ops.find(merged, "p-2")
    assert keep is not None and keep["aliases"] == ["红伞"] and keep["paras"] == [1, 3]
    assert len(keep["source_spans"]) == 2 and merged["merge_suggestions"] == []
    with pytest.raises(ops.BibleEditError, match="merge_kinds_differ"):
        ops.merge(_payload(), ["c-1", "p-1"])
    with pytest.raises(ops.BibleEditError, match="merge_needs_two"):
        ops.merge(_payload(), ["p-1"])

    apart = ops.distinct(_payload(), ["p-2", "p-1"])
    assert apart["merge_suggestions"] == [] and apart["distinct"] == [["p-2", "p-1"]]
    assert ops.distinct(apart, ["p-1", "p-2"])["distinct"] == [["p-2", "p-1"]]  # once


def test_split_moves_the_paragraphs_that_name_the_alias() -> None:
    out, new = ops.split(_payload(), "c-1", "阿晚", TEXT.__getitem__, span_of, ids_from("c-2"))
    old, fresh = ops.find(out, "c-1"), ops.find(out, "c-2")
    assert old is not None and fresh is not None and new == "c-2"
    assert (old["aliases"], old["paras"]) == ([], [0])
    assert (fresh["name"], fresh["paras"], fresh["kind"]) == ("阿晚", [1, 2], "character")
    assert [e["id"] for e in out["entities"]][:2] == ["c-1", "c-2"]
    assert out["distinct"] == [["c-1", "c-2"]]
    with pytest.raises(ops.BibleEditError, match="alias_not_found"):
        ops.split(_payload(), "c-1", "小晚", TEXT.__getitem__, span_of)
