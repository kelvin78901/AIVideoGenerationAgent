"""自动质检 (M6 step 3), in Mock mode: each new take queues a QA job; what it measured and how
it was judged lands on the take and on the call that made the clip; 「重新质检」; the series'
thresholds and switches judge the takes again without measuring.

The demo: 1-03 a night insert of the note (on-screen words, nobody in it), 1-04 a 原生同步
dialogue shot with a locked voice.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import select

from drama_series_agent.api.app import create_app
from drama_series_agent.api.state import StudioState
from drama_series_agent.core.models_db import Job, ModelCall, ProductVersion

LOCAL = "http://127.0.0.1"
V1 = "/api/v1"
EP1 = "demo-e1"
DONE = ("succeeded", "failed", "canceled")


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(), base_url=LOCAL, headers={"X-Drama-Studio": "1"}) as c:
        yield c


def _state(client: TestClient) -> StudioState:
    state: StudioState = client.app.state.studio  # type: ignore[attr-defined]
    return state


def _rows(client: TestClient, model: Any, *where: Any) -> list[Any]:
    async def read() -> list[Any]:
        async with _state(client).db.session() as s:
            return list((await s.exec(select(model).where(*where))).all())

    return list(client.portal.call(read))  # type: ignore[union-attr]


def _shots(client: TestClient) -> dict[str, dict[str, Any]]:
    return {s["label"]: s for s in client.get(f"{V1}/episodes/{EP1}/shots").json()}


def _wait(client: TestClient, job_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 60
    while True:
        job: dict[str, Any] = client.get(f"{V1}/jobs/{job_id}").json()
        if job["state"] in DONE:
            assert job["state"] == "succeeded", job
            return job
        assert time.monotonic() < deadline, "the job did not finish"
        time.sleep(0.02)


def _qa_settled(client: TestClient) -> list[Job]:
    deadline = time.monotonic() + 60
    while True:
        jobs = _rows(client, Job, Job.kind == "qa.take")
        if jobs and all(j.state in DONE for j in jobs):
            assert all(j.state == "succeeded" for j in jobs), [j.error_json for j in jobs]
            return jobs
        assert time.monotonic() < deadline, "QA did not finish"
        time.sleep(0.02)


def _confirm_storyboard(client: TestClient) -> None:
    for shot in _shots(client).values():
        if not shot["confirmed"]:
            resp = client.patch(f"{V1}/shots/{shot['id']}", json={"confirmed": True})
            assert resp.status_code == 200, resp.text
    resp = client.post(f"{V1}/gates/storyboard/confirm", json={"scope_id": EP1})
    assert resp.status_code == 200, resp.text


def _take(client: TestClient, label: str) -> dict[str, Any]:
    pid = _shots(client)[label]["video_product_id"]
    resp = client.post(f"{V1}/products/{pid}/run", json={"mode": "run", "count": 1})
    assert resp.status_code == 200, resp.text
    _wait(client, resp.json()["id"])
    _qa_settled(client)
    take: dict[str, Any] = client.get(f"{V1}/products/{pid}").json()["versions"][-1]
    return take


def _checks(take: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {c["metric"]: c for c in take["qa"]["checks"]}


def _set_mock_qa(client: TestClient, version_id: str, given: dict[str, Any]) -> None:
    async def write() -> None:
        async with _state(client).db.session() as s:
            v = await s.get(ProductVersion, version_id)
            assert v is not None
            v.params_json = {**v.params_json, "mock_qa": given}
            s.add(v)
            await s.commit()

    client.portal.call(write)  # type: ignore[union-attr]


def _requa(client: TestClient, version_id: str) -> dict[str, Any]:
    resp = client.post(f"{V1}/versions/{version_id}/qa")
    assert resp.status_code == 200, resp.text
    assert (resp.json()["kind"], resp.json()["queue"]) == ("qa.take", "cpu")
    _wait(client, resp.json()["id"])
    v = next(
        v
        for p in client.get(f"{V1}/episodes/{EP1}/shots").json()
        for v in client.get(f"{V1}/products/{p['video_product_id']}").json()["versions"]
        if v["id"] == version_id
    )
    return v


def test_a_new_take_is_measured_and_judged(client: TestClient) -> None:
    _confirm_storyboard(client)
    take = _take(client, "1-04")
    qa, checks = take["qa"], _checks(take)
    assert list(checks) == ["face", "lipsync", "asr", "speaker", "ocr", "vlm"]
    # 1-04: she is in it and says her line on screen, in her own locked voice, the note in view.
    assert checks["face"]["ok"] is True and 0.8 <= checks["face"]["value"] <= 0.92
    assert checks["lipsync"]["ok"] is True and checks["lipsync"]["value"] >= 6
    assert (checks["asr"]["ok"], checks["asr"]["value"]) == (True, 0.0)
    assert checks["speaker"]["ok"] is True
    assert checks["ocr"]["ok"] is True
    assert checks["vlm"]["ok"] is True and checks["vlm"]["model"] == "google/gemini-3.1-flash-lite"
    assert take["qa_pass"] is True and 0 < qa["score"] <= 1
    assert qa["thresholds"] == {
        "face_sim": 0.75,
        "syncnet_conf": 6,
        "cer_max": 0.1,
        "speaker_sim": 0.6,
    }
    # QA is metadata: the content hash is the one the run gave.
    (row,) = _rows(client, ProductVersion, ProductVersion.id == take["id"])
    assert row.content_hash == take["content_hash"]

    # The call that made the clip carries the scores; each tool logged its own call, free.
    clip = _rows(client, ModelCall, ModelCall.id == take["params"]["call_id"])[0]
    assert clip.component_id == "vid" and clip.qa_pass is True
    assert clip.qa_scores_json["checks"]["face"]["ok"] is True
    assert clip.qa_scores_json["score"] == qa["score"]
    tools = _rows(client, ModelCall, ModelCall.component_id == "qa")
    by_model = sorted(c.model_key for c in tools if c.version_id == take["id"])
    assert by_model == [
        "google/gemini-3.1-flash-lite",  # the picture check, the only look at the sheet
        "local/auraface",
        "local/campplus",
        "local/rapidocr",
        "local/syncnet",
        "local/whisper-large-v3",
    ]
    mine = [c for c in tools if c.version_id == take["id"] and c.model_key.startswith("local/")]
    assert all(c.cost_usd == 0 and c.where == "local" for c in mine)
    # The run itself no longer looks (M6 step 4: no run-time take check).
    assert not [c for c in tools if c.version_id is None]


def test_on_screen_words_are_read_back(client: TestClient) -> None:
    _confirm_storyboard(client)
    take = _take(client, "1-03")
    checks = _checks(take)
    assert checks["ocr"]["ok"] is True and checks["ocr"]["detail"]["expected"]
    # Nobody in it, nothing said.
    assert all(checks[m]["ok"] is None for m in ("face", "lipsync", "asr", "speaker"))

    _set_mock_qa(client, take["id"], {"ocr": "错的字"})
    again = _requa(client, take["id"])
    ocr = _checks(again)["ocr"]
    assert (ocr["ok"], ocr["issue"], ocr["text"]) == (False, "text_mismatch", "错的字")
    assert again["qa_pass"] is False


def test_a_bad_face_fails_and_the_series_thresholds_judge_it_again(client: TestClient) -> None:
    _confirm_storyboard(client)
    take = _take(client, "1-04")
    _set_mock_qa(client, take["id"], {"face": 0.41})
    bad = _requa(client, take["id"])
    assert (_checks(bad)["face"]["ok"], bad["qa_pass"]) == (False, False)
    clip = _rows(client, ModelCall, ModelCall.id == take["params"]["call_id"])[0]
    assert clip.qa_pass is False
    calls = len(_rows(client, ModelCall))

    series = "demo"
    resp = client.put(
        f"{V1}/series/{series}/generate-rules", json={"thresholds": {"face_sim": 0.4}}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["thresholds"]["face_sim"] == 0.4
    assert resp.json()["thresholds"]["syncnet_conf"] == 6  # one item at a time
    pid = _shots(client)["1-04"]["video_product_id"]
    now = client.get(f"{V1}/products/{pid}").json()["versions"][-1]
    assert (now["qa_pass"], _checks(now)["face"]["threshold"]) == (True, 0.4)
    assert len(_rows(client, ModelCall)) == calls  # judged again, not measured again

    # Back to 0.75, the face check turned off: shown, failing nothing.
    client.put(f"{V1}/series/{series}/generate-rules", json={"reset_qa": True}).raise_for_status()
    resp = client.put(f"{V1}/series/{series}/generate-rules", json={"qa_on": {"face": False}})
    assert resp.json()["qa_on"]["face"] is False and resp.json()["thresholds"]["face_sim"] == 0.75
    now = client.get(f"{V1}/products/{pid}").json()["versions"][-1]
    face = _checks(now)["face"]
    assert (face["ok"], face["off"], now["qa_pass"]) == (False, True, True)
    rules = client.put(f"{V1}/series/{series}/generate-rules", json={"reset_qa": True}).json()
    assert rules["qa_on"]["face"] is True
    now = client.get(f"{V1}/products/{pid}").json()["versions"][-1]
    assert now["qa_pass"] is False


def test_only_a_take_is_checked(client: TestClient) -> None:
    kf = _shots(client)["1-01"]["keyframe_product_id"]
    versions = client.get(f"{V1}/products/{kf}").json()["versions"]
    assert versions
    resp = client.post(f"{V1}/versions/{versions[-1]['id']}/qa")
    assert (resp.status_code, resp.json()["detail"]["code"]) == (409, "qa_not_a_take")
    resp = client.post(f"{V1}/versions/nope/qa")
    assert resp.status_code == 404


def test_thresholds_are_bounded(client: TestClient) -> None:
    resp = client.put(f"{V1}/series/demo/generate-rules", json={"thresholds": {"face_sim": 2}})
    assert resp.status_code == 422
    resp = client.put(f"{V1}/series/demo/generate-rules", json={"qa_on": {"nose": True}})
    assert resp.status_code == 422


def _failing_faces(client: TestClient) -> None:
    """Mock's face tool finds nobody alike from now on."""
    from drama_series_agent.modelhub.adapters.base import ModelRequest

    def face(req: ModelRequest) -> dict[str, Any]:
        refs = req.params.get("refs") or []
        return {"faces": [{"asset_id": r["asset_id"], "name": r["name"], "sim": 0.3} for r in refs]}

    _state(client).registry.add_mock_responder("qa", "face", face)


def _settled(client: TestClient) -> None:
    """No job of any kind is left to run (QA starts runs, runs start QA)."""
    deadline = time.monotonic() + 120
    while True:
        jobs = client.get(f"{V1}/jobs?limit=500").json()
        if all(j["state"] in (*DONE, "waiting_confirm") for j in jobs):
            return
        assert time.monotonic() < deadline, "the jobs did not settle"
        time.sleep(0.05)


def test_a_failed_take_is_made_again_then_falls_back_then_stops(client: TestClient) -> None:
    _confirm_storyboard(client)
    client.put(f"{V1}/series/demo/generate-rules", json={"qa_retry_max": 1}).raise_for_status()
    _failing_faces(client)
    pid = _shots(client)["1-04"]["video_product_id"]
    resp = client.post(f"{V1}/products/{pid}/run", json={"mode": "run", "count": 1})
    assert resp.status_code == 200, resp.text
    _settled(client)

    versions = client.get(f"{V1}/products/{pid}").json()["versions"]
    assert [(v["origin"], v["qa_pass"]) for v in versions] == [
        ("run", False),
        ("auto_qa_rerun", False),
        ("fallback", False),
    ]
    first, rerun, fallback = versions
    # The rerun is told what failed; the fallback is the route's, for this reason.
    assert rerun["params"]["fixes"] == ["- 人物的脸要和参考图一样"]
    assert (rerun["model_key"], rerun["params"]["auto"]) == (first["model_key"], "auto_qa_rerun")
    assert (fallback["fallback_reason"], fallback["model_key"]) == ("qa_fail", "minimax/h3-api")
    (call,) = _rows(client, ModelCall, ModelCall.id == fallback["params"]["call_id"])
    assert (call.is_fallback, call.fallback_reason) == (True, "qa_fail")

    log = client.get(f"{V1}/episodes/{EP1}/generate-log").json()
    lines = [(e["message"]["code"], e["message"]["params"]) for e in log]
    codes = [c for c, _ in lines]
    assert codes == ["take_fail_rerun", "take_fail_fallback", "take_fail_stop"]
    assert lines[0][1]["issues"] == "face"
    assert lines[1][1]["to"] == "minimax/h3-api"

    # A person's own run starts again: one automatic rerun after it.
    client.post(f"{V1}/products/{pid}/run", json={"mode": "rerun", "count": 1}).raise_for_status()
    _settled(client)
    versions = client.get(f"{V1}/products/{pid}").json()["versions"]
    assert [v["origin"] for v in versions[3:]] == ["rerun", "auto_qa_rerun", "fallback"]


def test_a_fallback_waits_for_a_yes_when_asked_to(client: TestClient) -> None:
    _confirm_storyboard(client)
    client.put(f"{V1}/series/demo/generate-rules", json={"qa_retry_max": 0}).raise_for_status()
    fallback = {
        "enabled": True,
        "on": ["error", "timeout", "qa_fail"],
        "qa_fail_n": 2,
        "timeout_s": 600,
        "to": "minimax/h3-api",
        "notify": "ask",
    }
    body = {"scope": "component", "scope_id": None, "component_id": "vid"}
    resp = client.put(f"{V1}/config/override", json={**body, "data": {"fallback": fallback}})
    assert resp.status_code == 200, resp.text
    _failing_faces(client)
    pid = _shots(client)["1-04"]["video_product_id"]
    client.post(f"{V1}/products/{pid}/run", json={"mode": "run", "count": 1}).raise_for_status()
    _settled(client)
    (job,) = [
        j for j in client.get(f"{V1}/jobs?state=waiting_confirm").json() if j["product_id"] == pid
    ]
    confirm = job["params"]["confirm"]
    assert (confirm["reason"], confirm["error"], job["params"]["fallback_reason"]) == (
        "fallback",
        "qa_fail",
        "qa_fail",
    )
    assert confirm["estimate_usd"] > 0 and job["params"]["model_key"] == "minimax/h3-api"
    log = client.get(f"{V1}/episodes/{EP1}/generate-log").json()
    assert [e["message"]["code"] for e in log] == ["take_fail_fallback", "waiting"]


def test_an_adopted_shot_is_left_alone(client: TestClient) -> None:
    _confirm_storyboard(client)
    take = _take(client, "1-04")
    client.post(f"{V1}/versions/{take['id']}/adopt").raise_for_status()
    _set_mock_qa(client, take["id"], {"face": 0.41})
    _requa(client, take["id"])
    _settled(client)
    pid = _shots(client)["1-04"]["video_product_id"]
    assert len(client.get(f"{V1}/products/{pid}").json()["versions"]) == 1
