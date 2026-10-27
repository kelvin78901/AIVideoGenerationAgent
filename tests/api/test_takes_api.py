"""视频生成 (M5 step 5), in Mock mode: every shot's video product, takes as versions, the first
frame, sound by audio mode, the 生成 badge and 生成确认.

The demo: 9 shots, 1-01–1-03 confirmed; 1-04 native with a locked voice, 1-06 dub-first (one of
its lines not dubbed), 1-08 continues 1-06 and 1-09 continues 1-08.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import col, select

from drama_series_agent.api.app import create_app
from drama_series_agent.api.state import StudioState
from drama_series_agent.core.models_db import Job, ModelCall, Product

LOCAL = "http://127.0.0.1"
V1 = "/api/v1"
EP1 = "demo-e1"


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


def _badge(client: TestClient) -> dict[str, Any]:
    steps: dict[str, Any] = client.get(f"{V1}/episodes/{EP1}/progress").json()["steps"]
    return dict(steps["generate"])


def _wait(client: TestClient, job_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 60
    while True:
        job: dict[str, Any] = client.get(f"{V1}/jobs/{job_id}").json()
        if job["state"] in ("succeeded", "failed", "canceled"):
            assert job["state"] == "succeeded", job
            return job
        assert time.monotonic() < deadline, "the job did not finish"
        time.sleep(0.02)


def _run(client: TestClient, product_id: str, **body: Any) -> dict[str, Any]:
    resp = client.post(f"{V1}/products/{product_id}/run", json={"mode": "run", **body})
    assert resp.status_code == 200, resp.text
    _wait(client, resp.json()["id"])
    product: dict[str, Any] = client.get(f"{V1}/products/{product_id}").json()
    return product


def _refused(client: TestClient, product_id: str) -> tuple[int, str, dict[str, Any]]:
    resp = client.post(f"{V1}/products/{product_id}/run", json={"mode": "run"})
    detail = resp.json()["detail"]
    return resp.status_code, detail["code"], detail.get("params") or {}


def _confirm_storyboard(client: TestClient) -> None:
    for label, shot in _shots(client).items():
        if not shot["confirmed"]:
            resp = client.patch(f"{V1}/shots/{shot['id']}", json={"confirmed": True})
            assert resp.status_code == 200, (label, resp.text)
    resp = client.post(f"{V1}/gates/storyboard/confirm", json={"scope_id": EP1})
    assert resp.status_code == 200, resp.text


def _prompt(client: TestClient, version: dict[str, Any]) -> str:
    f = next(f for f in version["files"] if f["role"] == "prompt")
    return client.get(f"{V1}/files/{f['sha256']}").text


def _adopt(client: TestClient, version: dict[str, Any]) -> None:
    client.post(f"{V1}/versions/{version['id']}/adopt").raise_for_status()


def test_every_shot_has_a_video_product_that_waits_for_the_storyboard(
    client: TestClient,
) -> None:
    shots = _shots(client)
    assert all(s["video_product_id"] for s in shots.values())
    vid = client.get(f"{V1}/products/{shots['1-01']['video_product_id']}").json()
    assert (vid["component_id"], vid["slot"], vid["owner_id"]) == ("vid", "video", "demo-shot-1-01")
    assert _badge(client) == {"state": "not_started", "done": None, "total": None, "stale": 0}
    assert _refused(client, vid["id"])[:2] == (409, "storyboard_not_confirmed")


def test_a_first_run_makes_two_takes_from_the_keyframe(client: TestClient) -> None:
    _confirm_storyboard(client)
    assert _badge(client) == {"state": "in_progress", "done": 0, "total": 9, "stale": 0}
    shot = _shots(client)["1-01"]
    product = _run(client, shot["video_product_id"])
    takes = product["versions"]
    assert len(takes) == 2 and product["adopted_version_id"] is None  # candidates: 2
    for take in takes:
        # A local draft keeps its untrimmed clip (``raw``) for Regenerate-2K.
        roles = [f["role"] for f in take["files"]]
        assert roles == ["video", "poster", "last_frame", "raw", "prompt"]
        assert (take["model_key"], take["where"], take["stage"]) == ("comfy/h3", "local", "draft")
        video = take["files"][0]
        # The shot's length less the 0.3 s cut off the head.
        assert video["duration_s"] == pytest.approx(shot["duration_s"] - 0.3, abs=0.1)
        assert take["payload"]["audio_mode"] == "native"
    assert takes[1]["seed"] == takes[0]["seed"] + 1
    text = _prompt(client, takes[0])
    assert text.startswith(
        "For the target video, at 0.00 seconds into the target video, <Picture 1>"
    )
    assert "non_diegetic_music: N/A" in text
    calls = _rows(client, ModelCall, ModelCall.component_id == "vid")
    assert len(calls) == 2 and {c.shot_id for c in calls} == {"demo-shot-1-01"}
    # 「再出一条」: one more.
    assert len(_run(client, shot["video_product_id"])["versions"]) == 3
    _adopt(client, takes[0])
    assert _badge(client)["done"] == 1


def test_a_native_shot_sends_its_voices_to_the_reference_workflow(client: TestClient) -> None:
    _confirm_storyboard(client)
    take = _run(client, _shots(client)["1-04"]["video_product_id"])["versions"][0]
    assert take["model_key"] == "comfy/h3-r2v" and take["payload"]["voices"]
    text = _prompt(client, take)
    assert text.startswith("subject_definitions:\n<Picture 1> is the first frame of [Shot 1].")
    assert "<Audio 1> is the voice-timbre reference for" in text
    assert "using the voice timbre referenced from <Audio 1>: <d>[Chinese]" in text


def test_an_h3_api_take_goes_through_context_ir(client: TestClient) -> None:
    """M5 step 6: the H3 API gets the official rewriter's prompt (one Context-IR call for the
    takes of a run); a native shot with voices is reference-to-video there too."""
    _confirm_storyboard(client)
    shots = _shots(client)
    product = _run(client, shots["1-01"]["video_product_id"], model="minimax/h3-api")
    take = product["versions"][0]
    assert (take["model_key"], take["where"], take["stage"]) == ("minimax/h3-api", "api", None)
    assert take["payload"]["prompt_ir"] is True and take["payload"]["refs"] == []
    assert _prompt(client, take).startswith("[Context-IR] For the target video, at 0.00 seconds")
    ir = _rows(client, ModelCall, ModelCall.model_key == "minimax/context-ir")
    assert len(ir) == 1 and ir[0].component_id == "vid" and ir[0].cost_usd > 0

    take = _run(client, shots["1-04"]["video_product_id"], model="minimax/h3-api")["versions"][0]
    assert take["model_key"] == "minimax/h3-api" and take["payload"]["voices"]
    text = _prompt(client, take)
    assert text.startswith("[Context-IR] subject_definitions:\n<Picture 1> is the first frame")
    assert "<Audio 1> is the voice-timbre reference for" in text

    # 先配音: the dubbed lines are <Audio 1>, copied as the whole sound track.
    _dub_shot(client, shots["1-06"])
    take = _run(client, shots["1-06"]["video_product_id"], model="minimax/h3-api")["versions"][0]
    text = _prompt(client, take)
    assert "<Audio 1>: fully_copy - <Audio 1> is reused 1:1" in text
    assert "overall_soundscape: <Audio 1> as it is, with no other sound." in text


def _final(client: TestClient, product_id: str, version_id: str) -> dict[str, Any]:
    body = {"mode": "run", "where": "api", "params": {"source_version_id": version_id}}
    resp = client.post(f"{V1}/products/{product_id}/run", json=body)
    assert resp.status_code == 200, resp.text
    job: dict[str, Any] = resp.json()
    deadline = time.monotonic() + 60
    while job["state"] not in ("succeeded", "failed", "canceled"):
        assert time.monotonic() < deadline, "the job did not finish"
        time.sleep(0.02)
        job = client.get(f"{V1}/jobs/{job['id']}").json()
    return job


def test_an_api_final_regenerates_the_local_draft_at_2k(client: TestClient) -> None:
    """M5 step 7: 「用 API 出终版」 is H3 Regenerate-2K from the draft's untrimmed clip, its own
    inputs and prompt; one version, its parent the draft."""
    _confirm_storyboard(client)
    pid = _shots(client)["1-01"]["video_product_id"]
    draft = _run(client, pid)["versions"][0]
    raw = next(f for f in draft["files"] if f["role"] == "raw")
    video = draft["files"][0]
    assert raw["duration_s"] == pytest.approx(video["duration_s"] + 0.3, abs=0.1)
    _adopt(client, draft)
    # The impact rows price it on Regenerate-2K (Mock: the shot's seconds at 0.30 元; the real
    # adapter adds the input video, test_video_api_adapters).
    cost = _state(client).runs.final_cost
    product_row = _rows(client, Product, Product.id == pid)[0]
    estimate = client.portal.call(cost, product_row)  # type: ignore[union-attr]
    seconds = _shots(client)["1-01"]["duration_s"]
    assert estimate == pytest.approx(seconds * 0.30 / 7.1, abs=0.001)

    job = _final(client, pid, draft["id"])
    assert job["state"] == "succeeded", job
    product = client.get(f"{V1}/products/{pid}").json()
    assert len(product["versions"]) == 3  # two takes and one final, not two
    final = next(v for v in product["versions"] if v["stage"] == "final")
    assert final["model_key"] == "minimax/h3-regenerate-2k" and final["where"] == "api"
    assert final["parent_version_id"] == draft["id"]
    assert final["payload"]["resolution"] == "2k"
    assert [f["role"] for f in final["files"]] == ["video", "poster", "last_frame", "prompt"]
    assert (final["files"][0]["w"], final["files"][0]["h"]) == (1440, 2560)
    assert _prompt(client, final) == _prompt(client, draft)  # resent as it was
    (call,) = _rows(client, ModelCall, ModelCall.model_key == "minimax/h3-regenerate-2k")
    assert call.cost_usd > 0

    # An API take has no 768P draft to regenerate.
    api_take = _run(client, pid, model="minimax/h3-api")["versions"][-1]
    job = _final(client, pid, api_take["id"])
    assert job["state"] == "failed" and job["error"]["code"] == "draft_not_regenerable"


def test_a_failed_local_take_is_made_again_on_the_api(client: TestClient) -> None:
    """The fallback rebuilds the request for the H3 API (its layout, Context-IR)."""
    _confirm_storyboard(client)
    _state(client).registry.mock_settings.fail_keys.add("comfy/h3")
    product = _run(client, _shots(client)["1-01"]["video_product_id"])
    take = product["versions"][0]
    assert (take["model_key"], take["origin"], take["fallback_reason"]) == (
        "minimax/h3-api",
        "fallback",
        "error",
    )
    assert take["stage"] is None and take["payload"]["prompt_ir"] is True
    assert _prompt(client, take).startswith("[Context-IR] For the target video")
    assert not [f for f in take["files"] if f["role"] == "raw"]
    failed = _rows(client, ModelCall, ModelCall.model_key == "comfy/h3")
    assert failed and all(c.status == "error" for c in failed)


def test_a_local_take_that_times_out_falls_back(client: TestClient) -> None:
    body = {"scope": "component", "scope_id": None, "component_id": "vid"}
    fallback = client.get(f"{V1}/config/resolve", params={"component": "vid"}).json()["values"]
    data = {"fallback": {**fallback["fallback"], "timeout_s": 1}}
    client.put(f"{V1}/config/override", json={**body, "data": data}).raise_for_status()
    _confirm_storyboard(client)
    _state(client).registry.mock_settings.hang_keys.add("comfy/h3")
    take = _run(client, _shots(client)["1-01"]["video_product_id"])["versions"][0]
    assert (take["model_key"], take["fallback_reason"]) == ("minimax/h3-api", "timeout")
    (timed_out, *_) = _rows(client, ModelCall, ModelCall.model_key == "comfy/h3")
    assert timed_out.status == "timeout"


def test_the_gpu_keeps_the_loaded_workflow_busy(client: TestClient) -> None:
    """Local takes share the GPU queue, grouped by model: with H3 running, a later H3 take goes
    before an earlier H3 reference-to-video one (hard rule 8)."""
    _confirm_storyboard(client)
    _state(client).registry.mock_settings.delay_s = 0.4
    shots = _shots(client)
    ids = []
    for label in ("1-01", "1-04", "1-02"):  # comfy/h3, comfy/h3-r2v, comfy/h3
        resp = client.post(
            f"{V1}/products/{shots[label]['video_product_id']}/run", json={"mode": "run"}
        )
        assert resp.status_code == 200, resp.text
        ids.append(resp.json()["id"])
    jobs = {job_id: _wait(client, job_id) for job_id in ids}
    rows = {r.id: r for r in _rows(client, Job, col(Job.id).in_(ids))}
    assert {rows[i].queue for i in ids} == {"gpu"}
    assert [rows[i].params_json["model_key"] for i in ids] == [
        "comfy/h3",
        "comfy/h3-r2v",
        "comfy/h3",
    ]
    started = sorted(ids, key=lambda i: str(jobs[i]["started_at"]))
    assert started == [ids[0], ids[2], ids[1]]


def test_continuing_shots_wait_for_the_take_they_continue(client: TestClient) -> None:
    _confirm_storyboard(client)
    shots = _shots(client)
    assert _refused(client, shots["1-08"]["video_product_id"]) == (
        409,
        "upstream_not_adopted",
        {"id": "1-06"},
    )
    code, error, params = _refused(client, shots["1-06"]["video_product_id"])
    assert (code, error) == (409, "line_audio_missing") and params["count"] >= 1


def _dub_shot(client: TestClient, shot: dict[str, Any]) -> None:
    """Dub the shot's spoken lines (「配音」 on the episode's dubbing list)."""
    spoken = {x["line_id"] for x in client.get(f"{V1}/episodes/{EP1}/dub").json()["lines"]}
    ids = [x for x in shot["line_ids"] if x in spoken]
    resp = client.post(f"{V1}/episodes/{EP1}/dub", json={"line_ids": ids})
    assert resp.status_code == 200, resp.text
    for job_id in resp.json()["jobs"]:
        _wait(client, job_id)


def test_the_takes_gate_locks_one_adopted_take_per_shot(client: TestClient) -> None:
    _confirm_storyboard(client)
    shots = _shots(client)
    _dub_shot(client, shots["1-06"])
    for label in ("1-01", "1-02", "1-03", "1-04", "1-05", "1-06", "1-07", "1-08", "1-09"):
        product = _run(client, shots[label]["video_product_id"], count=1)
        _adopt(client, product["versions"][-1])
        if label == "1-06":  # dub-first: the dubbed lines go with it, said in the prompt
            text = _prompt(client, product["versions"][-1])
            assert text.startswith("For the target video") and "(S1) says" in text
            assert "<d>[Chinese] " in text and "\n\noverall_soundscape: " in text
        if label == "1-02":
            resp = client.post(f"{V1}/gates/takes/confirm", json={"scope_id": EP1})
            assert resp.status_code == 409, resp.text
            detail = resp.json()["detail"]
            assert detail["code"] == "takes_not_adopted" and detail["params"]["count"] == 7
            assert detail["params"]["labels"].startswith("1-03、1-04")
    assert _badge(client) == {"state": "in_progress", "done": 9, "total": 9, "stale": 0}
    resp = client.post(f"{V1}/gates/takes/confirm", json={"scope_id": EP1})
    assert resp.status_code == 200, resp.text
    assert _badge(client)["state"] == "confirmed"
    first = client.get(f"{V1}/products/{shots['1-01']['video_product_id']}").json()
    assert first["locked_hash"]
    client.post(f"{V1}/gates/takes/reopen", json={"scope_id": EP1}).raise_for_status()
    first = client.get(f"{V1}/products/{shots['1-01']['video_product_id']}").json()
    assert not first["locked_hash"] and _badge(client)["state"] == "in_progress"


def test_a_changed_shot_or_aspect_lists_its_takes(client: TestClient) -> None:
    _confirm_storyboard(client)
    shot = _shots(client)["1-01"]
    _adopt(client, _run(client, shot["video_product_id"])["versions"][0])
    resp = client.post(
        f"{V1}/impact/preview",
        json={"kind": "shot_edit", "target_id": shot["id"], "patch": {"framing": "close"}},
    )
    assert resp.status_code == 200, resp.text
    codes = {x["code"]: x for x in resp.json()["lines"]}
    assert codes["stale_video"]["params"]["shots"] == "1-01"
    resp = client.post(
        f"{V1}/impact/preview",
        json={"kind": "spec_aspect", "target_id": "demo", "patch": {"aspect": "16:9"}},
    )
    assert resp.status_code == 200, resp.text
    codes = {x["code"]: x for x in resp.json()["lines"]}
    assert codes["videos_redo"]["params"] == {"count": 2, "adopted": 1}
