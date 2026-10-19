from __future__ import annotations

import json
from typing import Any

import pytest

from drama_series_agent.core.config import Override, get_config, resolve
from drama_series_agent.core.paths import REPO_ROOT
from drama_series_agent.spec.compat import compat_table, judge
from drama_series_agent.spec.dims import ASPECTS, Aspect, Delivery


def _table(
    aspect: Aspect, delivery: Delivery = "1080p", overrides: list[Override] | None = None
) -> list[tuple[str, list[str], str, str]]:
    cfg = get_config()
    compat = compat_table(
        aspect, delivery, lambda c: resolve(c, overrides or [], config=cfg).values, cfg
    )
    assert compat.aspect == aspect
    return [(r.stage, r.model_keys, r.status, r.how.code) for r in compat.rows]


def _msw_rows(aspect: Aspect) -> list[tuple[str, list[str], str, str]]:
    """``web/src/mocks/handlers/spec.ts:compatRows``, the prototype's table."""
    is21 = aspect == "21:9"
    return [
        (
            "keyframe",
            ["google/nano-banana-pro"],
            "unsupported" if is21 else "native",
            "outpaint_from_16_9" if is21 else "native_4k",
        ),
        ("text_keyframe", ["openai/gpt-image-2"], "convert", "upscale_from_1k"),
        ("sketch", ["volc/seedream-5.0"], "native", "cheap_sketch"),
        ("video_draft", ["comfy/h3"], "native", "h3_aspects"),
        ("video_final", ["minimax/h3-regenerate-2k"], "native", "follow_draft"),
        ("video_alt", ["volc/seedance-2.5"], "convert", "upscale_from_720p"),
        ("upscale", ["comfy/seedvr2", "comfy/flashvsr"], "native", "any_aspect"),
    ]


@pytest.mark.parametrize("aspect", ASPECTS)
def test_matches_prototype_table(aspect: Aspect) -> None:
    assert _table(aspect) == _msw_rows(aspect)


def test_every_code_has_copy() -> None:
    how: dict[str, Any] = {}
    stages: dict[str, Any] = {}
    for lang in ("zh-CN", "en"):
        path = REPO_ROOT / "web" / "src" / "locales" / lang / "spec.json"
        data = json.loads(path.read_text(encoding="utf-8"))["compat"]
        how[lang], stages[lang] = data["how"], data["stage"]
    for aspect in ASPECTS:
        for delivery in ("1080p", "2k"):
            for stage, _, _, code in _table(aspect, delivery):  # type: ignore[arg-type]
                for lang in ("zh-CN", "en"):
                    assert code in how[lang], (lang, code)
                    assert stage in stages[lang], (lang, stage)
    for stage in get_config().spec.compat_stages:
        assert stage.native in how["zh-CN"] and stage.native in how["en"]


def test_follows_route_overrides() -> None:
    # Keyframes switched to GPT Image 2: needs an upscale; 3D world stays off and has no row.
    ov = Override("component", None, "kf", {"api_model": "openai/gpt-image-2"})
    rows = {r[0]: r for r in _table("9:16", overrides=[ov])}
    assert rows["keyframe"][1:] == (["openai/gpt-image-2"], "convert", "upscale_from_1k")
    # Fallback cleared: no sketch row.
    ov = Override("component", None, "kf", {"fallback": {"to": None}})
    assert "sketch" not in {r[0] for r in _table("9:16", overrides=[ov])}
    # Component turned off: its rows disappear.
    ov = Override("component", None, "vid", {"mode": "off"})
    stages = [r[0] for r in _table("9:16", overrides=[ov])]
    assert "video_draft" not in stages and "video_alt" not in stages


def test_judge() -> None:
    caps = {"aspects": ["9:16", "16:9"], "max_short_edge": 1440}
    assert judge(caps, "9:16", 1080) == ("native", None)
    status, how = judge(caps, "1:1", 1080)
    assert status == "unsupported" and how is not None and how.code == "outpaint_from_9_16"
    status, how = judge(caps, "16:9", 1536)
    assert status == "convert" and how is not None and how.code == "upscale_from_1k"
    status, how = judge({"max_short_edge": 720}, "21:9", 768)
    assert status == "convert" and how is not None and how.code == "upscale_from_720p"
    assert judge({}, "21:9", 1440) == ("native", None)  # no caps known: assume native
