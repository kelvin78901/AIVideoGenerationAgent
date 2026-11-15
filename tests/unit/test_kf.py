"""关键帧 (M4 step 3): which references a keyframe sends, and the top view in words."""

from __future__ import annotations

from drama_series_agent.modelhub.workflows import load_workflow
from drama_series_agent.pipeline.component import Inputs
from drama_series_agent.pipeline.components.kf import (
    blocking_text,
    facing,
    part_of,
    pick_refs,
    ref_limit,
    size_words,
)


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


def test_which_workflows_need_a_reference_picture() -> None:
    """Qwen-Image-Edit 2511 only edits (reference 1 is required); Qwen-Image draws from words."""
    assert load_workflow("qwen-image-edit").needs_refs()
    assert load_workflow("qwen-image-edit-hq").needs_refs()
    assert not load_workflow("qwen-image").needs_refs()
    assert load_workflow("flux3-klein").needs_refs()
    assert len(load_workflow("flux3-klein").bindings("ref_image")) == 4
    assert not load_workflow("flux3-klein-t2i").needs_refs()


def test_the_top_view_in_words() -> None:
    marks = [
        {"id": "door", "kind": "landmark", "label": "家门", "x": 0.78, "y": 0.14},
        {"id": "linwan", "kind": "character", "label": "林晚", "x": 0.5, "y": 0.8},
        {"id": "camera", "kind": "camera", "label": "", "x": 0.5, "y": 0.92},
    ]
    assert blocking_text(marks) == "家门在画面右侧，远处；林晚在画面中间，近处；机位在正前方"


def test_the_top_view_leaves_out_who_is_not_in_the_shot() -> None:
    """The top view is the scene's: 1-02 (the umbrella at the door) has no 林晚 in it."""
    marks = [
        {"id": "door", "kind": "landmark", "label": "家门", "x": 0.78, "y": 0.14},
        {"id": "umbrella", "kind": "prop", "label": "红伞", "x": 0.9, "y": 0.5},
        {"id": "linwan", "kind": "character", "label": "林晚", "x": 0.5, "y": 0.4},
        {"id": "camera", "kind": "camera", "label": "", "x": 0.5, "y": 0.92},
    ]
    assert blocking_text(marks, {"hall", "umbrella"}) == (
        "家门在画面右侧，远处；红伞在画面右侧；机位在正前方"
    )
    assert "林晚" in blocking_text(marks, {"林晚"})  # a model's own ids: matched by name


def test_a_props_size_against_a_person() -> None:
    """M5.5 step 9e-1: the size in words a picture model can see, from the first length named."""
    assert size_words("全长约 90 cm，伞面直径约 100 cm") == "立着到人的胯部"
    assert size_words("7.6 cm 见方") == "手掌大小，比脸小"
    assert size_words("长 15 厘米") == "和脸差不多大"
    assert size_words("1.8 m") == "比人的肩还高"
    assert size_words("一张便签纸") is None


def test_whose_part_a_close_up_films() -> None:
    """M5.5 step 9e-2: a close-up of 「林晚的手」, or of only things while she is in the shot, is a
    part of her (filmed over her shoulder, her own picture left out); her face is not."""
    hand = {"framing": "closeup", "intent": "特写林晚的手"}
    c = {"start": [{"subject": "林晚的手", "state": "停在便利贴上方"}], "end": []}
    assert part_of(hand, c, ["林晚"]) == "林晚"
    phone = {"start": [{"subject": "手机", "state": "屏幕亮着"}], "end": []}
    assert part_of({"framing": "closeup"}, phone, ["林晚"]) == "林晚"
    face = {"start": [{"subject": "林晚", "state": "看着便利贴，愣住"}], "end": []}
    assert part_of({"framing": "closeup"}, face, ["林晚"]) is None
    assert part_of({"framing": "close"}, c, ["林晚"]) is None
    assert part_of(hand, c, []) is None


def test_who_looks_at_the_words() -> None:
    """What has words or a screen faces whoever looks at it (run 19 1-07's phone faced the lens)."""
    looking = {"framing": "close", "intent": "林晚看着便利贴，愣住"}
    assert facing(looking, None, ["林晚"], ["黄色便利贴"]) == {
        "who": "林晚",
        "things": ["黄色便利贴"],
    }
    walking = {"framing": "wide", "intent": "林晚走上六楼"}
    assert facing(walking, None, ["林晚"], ["黄色便利贴"]) is None
    assert facing(looking, None, [], ["黄色便利贴"]) is None
    assert facing(looking, None, ["林晚"], []) is None
