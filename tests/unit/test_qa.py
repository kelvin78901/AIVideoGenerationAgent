"""自动质检 (M6 step 3): judging what the tools measured (``pipeline/qa.py``)."""

from __future__ import annotations

from typing import Any

import pytest

from drama_series_agent.pipeline.generate import GenerateRules, QaSwitches, QaThresholds
from drama_series_agent.pipeline.qa import cer, judge, result, scores


def _rules(**on: bool) -> GenerateRules:
    return GenerateRules(
        takes_per_shot=2,
        qa_retry_max=2,
        shot_cap_usd=2,
        thresholds=QaThresholds(face_sim=0.18, syncnet_conf=1.0, cer_max=0.2, speaker_sim=0.65),
        qa_on=QaSwitches(**on),
    )


def _raw(**values: Any) -> list[dict[str, Any]]:
    out = []
    for metric, value in values.items():
        c: dict[str, Any] = {"metric": metric, "value": None, "text": None, "model": None}
        if value == "na":
            c["na"] = True
        elif metric in ("ocr", "vlm"):
            c["match"] = value
            c["items"] = [{"check": "repeat", "ok": value}] if metric == "vlm" else None
        else:
            c["value"] = value
        out.append(c)
    return out


def test_character_error_rate_ignores_punctuation_width_and_spaces() -> None:
    assert cer("你 回来啦！", "你回来啦。") == 0.0
    assert cer("你回来了", "你回来啦") == 0.25
    assert cer("", "你好") == 1.0
    assert cer("ＡＢ", "AB") == 0.0
    assert cer("", "") == 0.0


def test_each_metric_is_held_to_its_threshold() -> None:
    checks, score, passed = judge(
        _raw(face=0.8, lipsync=3.0, asr=0.05, speaker=0.7, ocr=True, vlm=True), _rules()
    )
    assert passed is True and all(c["ok"] for c in checks)
    assert {c["metric"]: c["threshold"] for c in checks} == {
        "face": 0.18,
        "lipsync": 1.0,
        "asr": 0.2,
        "speaker": 0.65,
        "ocr": None,
        "vlm": None,
    }
    # face 0.8, lipsync 3 / 4, asr 0.95, speaker 0.7, ocr 1, vlm 1
    assert score == pytest.approx((0.8 + 0.75 + 0.95 + 0.7 + 1 + 1) / 6, abs=1e-3)

    checks, _, passed = judge(_raw(face=0.1, asr=0.3, ocr=False), _rules())
    assert passed is False
    by = {c["metric"]: c for c in checks}
    assert (by["face"]["ok"], by["face"]["issue"]) == (False, "face_mismatch")
    assert (by["asr"]["ok"], by["asr"]["issue"]) == (False, None)
    assert (by["ocr"]["ok"], by["ocr"]["issue"]) == (False, "text_mismatch")


def test_a_check_that_does_not_apply_or_could_not_run_counts_for_nothing() -> None:
    raw = _raw(face=0.9, lipsync="na")
    raw.append({"metric": "speaker", "value": None, "text": None, "error": "unavailable"})
    checks, score, passed = judge(raw, _rules())
    assert [c["ok"] for c in checks] == [True, None, None]
    assert (score, passed) == (0.9, True)
    # Nothing counted: not checked, neither passed nor failed.
    assert judge(_raw(face="na"), _rules())[1:] == (0.0, None)


def test_a_check_turned_off_is_shown_but_fails_nothing() -> None:
    checks, score, passed = judge(_raw(face=0.1, vlm=True), _rules(face=False))
    face = checks[0]
    assert (face["ok"], face["off"]) == (False, True)
    assert (score, passed) == (1.0, True)


def test_the_result_keeps_the_rules_and_what_model_call_keeps() -> None:
    qa, passed = result(_raw(face=0.8, ocr=False), _rules(), ran_at="t")
    assert passed is False
    assert qa["thresholds"]["face_sim"] == 0.18 and qa["qa_on"]["ocr"] is True
    assert qa["ran_at"] == "t"
    assert scores(qa) == {
        "checks": {
            "face": {"value": 0.8, "ok": True, "off": False},
            "ocr": {"value": None, "ok": False, "off": False},
        },
        "score": 0.4,
    }
