"""M6 acceptance (plan step 10), against a real backend process in Mock mode: the demo's three
deliberately bad takes (``studio/demo.py:DEMO_BAD_TAKES``) are checked once the app runs, held
back, and QA does what it does with any take: 1-05 T1 (the note's writing drawn wrong) and 1-06
T1 (someone else's face) are rerun with what was wrong told to the model, 1-04 T4 (only the
mouths off) gets an automatic 口型修复. Each ends with a passing take, none adopted; the run log
says what QA did; the call that made a rerun's clip carries its QA scores, and each QA tool
has a ``model_call`` row.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import pytest
from test_novel_to_script import Api

if TYPE_CHECKING:
    from conftest import Backend  # tests/e2e/conftest.py

pytestmark = pytest.mark.e2e

EP = "demo-e1"
DONE = ("succeeded", "failed", "canceled")


def _settled(api: Api, limit_s: float = 180) -> None:
    """Until the demo's QA and what it started have ended (a QA job starts its rerun or repair
    before it ends, and a new take queues its QA before its run ends)."""
    deadline = time.monotonic() + limit_s
    while True:
        jobs = api.get("/jobs", limit=500)
        if jobs and all(j["state"] in DONE for j in jobs):
            return
        assert time.monotonic() < deadline, [(j["kind"], j["state"]) for j in jobs]
        time.sleep(0.2)


def _versions(api: Api, label: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    shot = next(s for s in api.get(f"/episodes/{EP}/shots") if s["label"] == label)
    product: dict[str, Any] = api.get(f"/products/{shot['video_product_id']}")
    return product, sorted(product["versions"], key=lambda v: v["n"])


def _failing(v: dict[str, Any]) -> list[str]:
    checks = (v["qa"] or {}).get("checks") or []
    return [c["metric"] for c in checks if c["ok"] is False and not c.get("off")]


def test_the_demos_bad_takes_are_held_back_and_fixed(backend: Backend) -> None:
    backend.start(DRAMA_DEMO_QA="1")
    api = Api(backend)
    _settled(api)
    jobs = api.get("/jobs", limit=500)
    assert all(j["state"] == "succeeded" for j in jobs), [
        (j["kind"], j["state"], j["error"]) for j in jobs if j["state"] != "succeeded"
    ]
    calls: list[dict[str, Any]] = api.get("/dev/model-calls", limit=500)

    # 1-05 and 1-06: the bad take fails its one check and is rerun once; the rerun passes.
    for label, metric in (("1-05", "ocr"), ("1-06", "face")):
        product, versions = _versions(api, label)
        assert [v["n"] for v in versions] == [1, 2], label
        bad, rerun = versions
        assert bad["qa_pass"] is False and _failing(bad) == [metric], (label, bad["qa"])
        assert bad["qa"]["policy"]["action"] == "rerun", label
        assert rerun["origin"] == "auto_qa_rerun" and rerun["qa_pass"] is True, label
        assert rerun["params"]["fixes"], label  # what was wrong, told to the model
        assert product["adopted_version_id"] is None, label
        # The call that made the rerun's clip carries its QA; each tool has its own row ($0).
        made = next(c for c in calls if c["id"] == rerun["params"]["call_id"])
        assert made["qa_pass"] is True and made["qa_scores_json"], made
        tools = [c for c in calls if c["component_id"] == "qa" and c["version_id"] == rerun["id"]]
        assert {c["status"] for c in tools} == {"success"}, tools
        assert len({c["model_key"] for c in tools}) >= 2, tools
    _, versions = _versions(api, "1-05")
    ocr = next(c for c in versions[0]["qa"]["checks"] if c["metric"] == "ocr")
    assert ocr["text"] == "楼下便利店，等你到十点。"

    # 1-04: T1–T3 pass; T4 (the Seedance switch) fails only its mouths and is repaired, the
    # repair passing and left to pick (the take it was made from is not adopted).
    product, versions = _versions(api, "1-04")
    assert [v["n"] for v in versions] == [1, 2, 3, 4, 5]
    assert all(v["qa_pass"] is True for v in versions[:3]), [v["qa"] for v in versions[:3]]
    t4, t5 = versions[3], versions[4]
    assert t4["qa_pass"] is False and _failing(t4) == ["lipsync"], t4["qa"]
    assert t4["qa"]["policy"]["action"] == "lip"
    assert (t5["origin"], t5["parent_version_id"]) == ("lipsync", t4["id"])
    assert t5["params"]["auto"] == "auto_lip" and t5["qa_pass"] is True, t5["qa"]
    assert product["adopted_version_id"] is None

    # The run log says what QA did after each bad take.
    log = api.get(f"/episodes/{EP}/generate-log")
    codes = {(e["shot_label"], e["message"]["code"]) for e in log}
    acted = {("1-05", "take_fail_rerun"), ("1-06", "take_fail_rerun"), ("1-04", "take_fail_lip")}
    assert acted <= codes, sorted(codes)
