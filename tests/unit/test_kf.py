"""关键帧 (M4 step 3): which references a keyframe sends, and the top view in words."""

from __future__ import annotations

from drama_series_agent.pipeline.component import Inputs
from drama_series_agent.pipeline.components.kf import blocking_text, pick_refs, ref_limit


def _ref(name: str, kind: str) -> dict[str, str]:
    return {"name": name, "kind": kind, "product_id": f"p-{name}", "sha256": name, "hash": "h"}


def _inputs() -> Inputs:
    refs = [_ref("林晚", "character"), _ref("楼道", "scene"), _ref("红伞", "prop")]
    return Inputs(blocks=[], context={"refs": refs, "unlocked": ["旧黑发圈"]})


def test_the_locked_references_up_to_the_limit() -> None:
    refs, deps, blocks = pick_refs(_inputs(), None, 3)
    assert [r["name"] for r in refs] == ["林晚", "楼道", "红伞"]
    assert [d.upstream_product_id for d in deps] == ["p-林晚", "p-楼道", "p-红伞"]
    named = next(b.text for b in blocks if b.title == "参考图")
    assert named.startswith(
        "参考图 1：林晚（角色）；参考图 2：楼道（场景）；参考图 3：红伞（道具）。"
    )
    missing = next(b.text for b in blocks if b.title == "没传的参考")
    assert missing.startswith("旧黑发圈（")


def test_a_final_sends_its_draft_first_and_drops_what_does_not_fit() -> None:
    refs, deps, blocks = pick_refs(_inputs(), "draft-sha", 3)
    assert [r["sha256"] for r in refs] == ["draft-sha", "林晚", "楼道"]
    assert [d.upstream_product_id for d in deps] == ["p-林晚", "p-楼道"]  # not the dropped one
    assert any(b.title == "草稿" for b in blocks)
    missing = next(b.text for b in blocks if b.title == "没传的参考")
    assert missing.startswith("旧黑发圈、红伞（")


def test_no_limit_known_sends_them_all() -> None:
    refs, _, _ = pick_refs(_inputs(), None, None)
    assert len(refs) == 3


def test_how_many_references_a_model_takes() -> None:
    assert ref_limit(14, "api", None) == 14
    assert ref_limit(None, "api", None) is None
    assert ref_limit(None, "local", "qwen-image-edit") == 3  # its three ref_image slots
    assert ref_limit(None, "local", None) == 3


def test_the_top_view_in_words() -> None:
    marks = [
        {"id": "door", "kind": "landmark", "label": "家门", "x": 0.78, "y": 0.14},
        {"id": "linwan", "kind": "character", "label": "林晚", "x": 0.5, "y": 0.8},
        {"id": "camera", "kind": "camera", "label": "", "x": 0.5, "y": 0.92},
    ]
    assert blocking_text(marks) == "家门在画面右侧，远处；林晚在画面中间，近处；机位在正前方"
