"""不达标自动重跑和兜底 (M6 step 4): what ``qa_policy.decide`` does about a shot's newest
batch of takes."""

from __future__ import annotations

from typing import Any

from drama_series_agent.core.models_db import ProductVersion
from drama_series_agent.pipeline.qa_policy import decide, fix_lines

FALLBACK = "minimax/h3-api"


def _take(
    n: int,
    job: str,
    *,
    origin: str = "run",
    passed: bool | None = False,
    fails: tuple[str, ...] = ("face",),
    checked: bool = True,
    score: float = 0.5,
    **extra: Any,
) -> ProductVersion:
    checks = [{"metric": m, "ok": False, "off": False, "detail": {}} for m in fails]
    return ProductVersion(
        product_id="p",
        n=n,
        origin=origin,
        job_id=job,
        model_key="comfy/h3",
        content_hash=f"h{n}",
        qa_json={"checks": checks, "score": score} if checked else None,
        qa_pass=passed if checked else None,
        **extra,
    )


def _decide(*versions: ProductVersion, retry_max: int = 2) -> str:
    return decide(list(versions), retry_max=retry_max, fallback=FALLBACK).action


def test_nothing_while_a_take_of_the_batch_passes_or_is_not_checked_yet() -> None:
    assert _decide(_take(1, "j1"), _take(2, "j1", passed=True)) == "none"
    assert _decide(_take(1, "j1"), _take(2, "j1", checked=False)) == "wait"
    assert _decide(_take(1, "j1", passed=None)) == "none"  # could not be checked
    assert _decide() == "none"


def test_reruns_then_the_fallback_then_stop() -> None:
    first = _take(1, "j1")
    one = _take(2, "j2", origin="auto_qa_rerun")
    two = _take(3, "j3", origin="auto_qa_rerun")
    assert _decide(first) == "rerun"
    assert _decide(first, one) == "rerun"
    d = decide([first, one, two], retry_max=2, fallback=FALLBACK)
    assert (d.action, d.model, d.source) == ("fallback", FALLBACK, two)
    fell = _take(4, "j4", origin="fallback", fallback_reason="qa_fail")
    assert _decide(first, one, two, fell) == "stop"
    # No fallback configured: stop once the reruns are used up.
    assert decide([first, one, two], retry_max=2, fallback=None).action == "stop"
    assert _decide(first, retry_max=0) == "fallback"


def test_a_rerun_that_fell_back_on_an_error_still_counts() -> None:
    first = _take(1, "j1")
    errored = _take(2, "j2", origin="fallback", fallback_reason="error", params_json={})
    errored.params_json = {"auto": "auto_qa_rerun"}
    assert _decide(first, errored, retry_max=1) == "fallback"


def test_a_persons_own_run_starts_the_count_again() -> None:
    old = [_take(1, "j1"), _take(2, "j2", origin="auto_qa_rerun")]
    assert _decide(*old, retry_max=1) == "fallback"
    mine = _take(3, "j3", origin="rerun")
    assert _decide(*old, mine, retry_max=1) == "rerun"
    switched = _take(3, "j3", origin="switch")
    assert _decide(*old, switched, retry_max=1) == "rerun"


def test_only_lip_sync_failing_goes_to_lip_sync_repair() -> None:
    take = _take(1, "j1", fails=("lipsync",))
    d = decide([take], retry_max=2, fallback=FALLBACK)
    assert (d.action, d.source) == ("lip", take)
    assert _decide(_take(1, "j1", fails=("lipsync", "face"))) == "rerun"


def _repair(n: int, of: ProductVersion, **kw: Any) -> ProductVersion:
    finish = {"kind": "lipsync", "version_id": of.id}
    return _take(n, f"lip{n}", origin="lipsync", params_json={"finish": finish}, **kw)


def test_a_take_is_repaired_once_then_judged_with_its_repair() -> None:
    take = _take(1, "j1", fails=("lipsync",))
    # The repair is no take of a batch; until it is checked, wait for it.
    assert _decide(take, _repair(2, take, checked=False)) == "wait"
    # It passed: nothing more (the person adopts it or not).
    assert _decide(take, _repair(2, take, passed=True)) == "none"
    # It failed too: never repaired again, the takes are made again; noted on the repair.
    failed = _repair(2, take, fails=("lipsync",))
    d = decide([take, failed], retry_max=2, fallback=FALLBACK)
    assert (d.action, d.source, d.noted) == ("rerun", take, failed)
    # Another shot's or an older batch's repair does not count.
    new = _take(3, "j3", origin="rerun", fails=("lipsync",))
    assert _decide(take, failed, new) == "lip"
    # A repair that fell back (origin ``fallback``) is still a repair, not a take.
    fell = _repair(2, take, passed=True)
    fell.origin, fell.fallback_reason = "fallback", "error"
    assert _decide(take, fell) == "none"


def test_the_best_take_of_the_batch_says_what_to_fix() -> None:
    worse = _take(1, "j1", fails=("face", "asr"), score=0.2)
    better = _take(2, "j1", fails=("ocr",), score=0.7)
    better.qa_json["checks"][0]["detail"] = {"expected": ["23:52"]}  # type: ignore[index]
    d = decide([worse, better], retry_max=2, fallback=FALLBACK)
    assert d.source is better and d.fixes == ["- 画面上的字要一字不差：「23:52」"]


def test_fix_lines_cover_each_check() -> None:
    v = _take(1, "j1", fails=())
    v.qa_json = {
        "checks": [
            {"metric": "face", "ok": False, "off": False},
            {"metric": "asr", "ok": False, "off": False, "detail": {"expected": "你回来啦"}},
            {"metric": "speaker", "ok": False, "off": True},  # off: not told
            {
                "metric": "vlm",
                "ok": False,
                "off": False,
                "items": [{"check": "repeat", "ok": False, "note": "门关上又开"}],
            },
        ]
    }
    assert fix_lines(v) == [
        "- 人物的脸要和参考图一样",
        "- 台词要一字不差：「你回来啦」",
        "- 动作重复（做了又撤销再做）：门关上又开",
    ]
