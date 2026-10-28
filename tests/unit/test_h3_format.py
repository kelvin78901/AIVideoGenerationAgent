"""The official H3 layout check (``prompts/h3_format.py``, M5 step 14b): what MiniMax's
h3-prompt-writing guide asks, and the two prompts of the 1-04 local check
(``docs/studio/reports/m5-local-smoke/run4-1-04-cut/``)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from drama_series_agent.prompts.compiler import PromptCompiler
from drama_series_agent.prompts.h3_format import (
    I2VA_INSTRUCTION,
    Audio,
    Facts,
    Line,
    Picture,
    check,
    mock_prompt,
    sections,
)

ROOT = Path(__file__).resolve().parents[2]
LINE = Line("S1", "林晚", "……周屿？", "Chinese", audio=1)


def _ref_facts(**kw: object) -> Facts:
    base: dict[str, object] = {
        "mode": "ref2va",
        "duration_s": 5.17,
        "aspect": "9:16",
        "draft": "",
        "pictures": [
            Picture("first_frame"),
            Picture("reference", "林晚", "character"),
            Picture("reference", "老小区楼道 · 夜", "scene"),
        ],
        "audios": [Audio("voice", "S1", "林晚")],
        "dialogue": [LINE],
    }
    return Facts(**{**base, **kw})  # type: ignore[arg-type]


def _example() -> str:
    """The Ref2VA example in the rewriter's system message: the 1-04 prompt that gave one
    continuous take on both seeds (run4 ``guidefmt``)."""
    system = PromptCompiler().render("vid/h3_rewrite_system.j2")
    return system.split("one line of Chinese dialogue):\n", 1)[1].strip()


def test_the_example_the_rewriter_is_shown_conforms() -> None:
    assert check(_example(), _ref_facts()) == []


def test_the_prompt_the_studio_sent_before_does_not() -> None:
    sent = ROOT / "docs/studio/reports/m5-local-smoke/run4-1-04-cut/prompt-as-sent.txt"
    if not sent.exists():
        pytest.skip("the local check's files are not in this checkout")
    r2v = sent.read_text(encoding="utf-8").splitlines()[1]  # the 1-04 line, JSON-quoted
    prompt = json.loads(r2v.split(": ", 1)[1].rstrip(","))
    problems = check(prompt, _ref_facts())
    assert any(p.startswith("Write every section in English") for p in problems)
    assert any("English words" in p for p in problems)


@pytest.mark.parametrize(
    "facts",
    [
        Facts("i2va", 5, "9:16", "", [Picture("first_frame")]),
        Facts(
            "i2va", 4, "16:9", "", [Picture("first_frame")],
            dialogue=[Line("S1", "a", "好。", "Chinese")],
        ),
        Facts(
            "i2va", 6, "9:16", "", [Picture("first_frame")],
            dialogue=[Line("S1", "a", "我回来了。", "Chinese", voiceover=True)],
        ),
        _ref_facts(),
        _ref_facts(
            audios=[Audio("dialogue_track")],
            dialogue=[Line("S1", "林晚", "……周屿？", "Chinese")],
        ),
    ],
)  # fmt: skip
def test_the_mock_rewrite_conforms(facts: Facts) -> None:
    assert check(mock_prompt(facts), facts) == []
    assert Facts.from_json(facts.as_json()) == facts


def test_a_reference_picture_on_its_own_line_is_refused() -> None:
    """The cut at 1-04's second 2: <Picture 3> as its own line read as a keyframe."""
    bad = _example().replace(
        "<Subject 2> is the old residential stairwell at night whose look comes from <Picture 3>:",
        "<Picture 3> is the reference for the stairwell:",
    )
    problems = check(bad, _ref_facts())
    assert any("do not give it its own line" in p for p in problems)
    assert any("<Picture 3> (老小区楼道 · 夜) must be cited inside" in p for p in problems)


def test_the_first_line_of_an_i2va_prompt_is_the_official_instruction() -> None:
    facts = Facts("i2va", 5, "9:16", "", [Picture("first_frame")])
    good = mock_prompt(facts)
    assert good.startswith(I2VA_INSTRUCTION + "\n\n")
    problems = check(good.replace(I2VA_INSTRUCTION, "<Picture 1> is the first frame."), facts)
    assert any(p.startswith("The first line must be exactly") for p in problems)
    assert [n for n, _ in sections(good)] == [
        "integrated_multimodal_description",
        "overall_soundscape",
        "non_diegetic_music",
    ]


@pytest.mark.parametrize(
    ("change", "expect"),
    [
        (("……周屿？</d>", "周屿？</d>"), "verbatim"),
        (("Lin Wan (S1)", "林晚 (S1)"), "Write every section in English"),
        (("The shot ends on", "[Shot 2] At 00:04.000, the shot cuts to the door. The shot ends on"),
         "one continuous shot"),
        (("non_diegetic_music: N/A", "non_diegetic_music: Soft piano."), "must be `N/A`"),
        (("[keyframe completion + reference generation + audio reference]",
          "[keyframe completion + reference generation]"), "must include"),
        (("<Audio 1>: reference -", "<Audio 1>: kept -"), "Use one of"),
    ],
)  # fmt: skip
def test_what_breaks_the_layout_is_named(change: tuple[str, str], expect: str) -> None:
    old, new = change
    example = _example()
    assert old in example
    problems = check(example.replace(old, new, 1), _ref_facts())
    assert any(expect in p for p in problems), problems


def test_too_short_a_description_is_refused() -> None:
    facts = Facts("i2va", 5, "9:16", "", [Picture("first_frame")])
    short = (
        f"{I2VA_INSTRUCTION}\n\nintegrated_multimodal_description: [Shot 1] Live-action, "
        "cinematic, <Picture 1>, she walks up the stairs.\n\noverall_soundscape: Rain.\n\n"
        "non_diegetic_music: N/A"
    )
    assert any("English words" in p for p in check(short, facts))
