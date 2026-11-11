"""视频生成 (M5 step 5), in Mock mode: every shot's video product, takes as versions, the first
frame, sound by audio mode, the 生成 badge and 生成确认.

The demo: 9 shots, 1-01–1-03 confirmed; 1-04 native with a locked voice, 1-06 dub-first (one of
its lines not dubbed), 1-08 continues 1-06 and 1-09 continues 1-08.
"""

from __future__ import annotations

import io
import json
import time
import wave
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import col, select

from drama_series_agent.api.app import create_app
from drama_series_agent.api.state import StudioState
from drama_series_agent.core.models_db import (
    Job,
    ModelCall,
    Product,
    ProductVersion,
    ScriptLine,
)
from drama_series_agent.media.video import probe
from drama_series_agent.modelhub.adapters.base import ModelRequest
from drama_series_agent.pipeline import vlook
from drama_series_agent.prompts import h3_format

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
        assert roles == ["video", "poster", "last_frame", "raw", "sheet", "prompt"]
        assert (take["model_key"], take["where"], take["stage"]) == ("comfy/h3", "local", "draft")
        video = take["files"][0]
        # The shot's length less the 0.3 s cut off the head.
        assert video["duration_s"] == pytest.approx(shot["duration_s"] - 0.3, abs=0.1)
        assert take["payload"]["audio_mode"] == "native"
        # Where the edit takes it from (step 15i): a Mock clip never moves, the shot outlasts
        # it, so all of it.
        assert take["payload"]["window"] == {"in_s": 0.0, "out_s": video["duration_s"]}
        assert take["payload"]["cuts"] == []  # one continuous shot (step 15j)
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
    assert text.startswith("subject_definitions:\n<Picture 1> is the first frame of [Shot 1]")
    # The locked pictures are <Subject N>, never a standalone <Picture N> line (M5 step 14b).
    assert "<Subject 1> is the character whose look comes from <Picture 2>." in text
    assert "\n<Picture 2>" not in text
    assert "<Audio 1> is the voice-timbre reference for" in text
    assert "using the voice timbre referenced from <Audio 1>: <d>[Chinese]" in text


def _rewrites(client: TestClient) -> list[ModelCall]:
    return _rows(client, ModelCall, ModelCall.component_id == "vprompt")


def test_a_local_h3_take_is_rewritten_into_the_official_layout(client: TestClient) -> None:
    """M5 step 14b: before a local H3 take, the ``vprompt`` route's writing model puts the
    prompt in MiniMax's official layout; the takes of one run share the rewrite."""
    _confirm_storyboard(client)
    shot = _shots(client)["1-01"]
    takes = _run(client, shot["video_product_id"])["versions"]
    calls = _rewrites(client)
    assert len(calls) == 1 and calls[0].model_key == "deepseek/v4.1-flash"
    assert calls[0].shot_id == "demo-shot-1-01" and calls[0].status == "success"
    facts = h3_format.Facts(
        "i2va", shot["duration_s"], "9:16", "", [h3_format.Picture("first_frame")]
    )
    for take in takes:
        assert take["payload"]["prompt_rewrite"] == "deepseek/v4.1-flash"
        assert h3_format.check(_prompt(client, take), facts) == []
    # 「再出一条」 with the same inputs: the rewrite is not asked again.
    _run(client, shot["video_product_id"])
    assert len(_rewrites(client)) == 1
    # An API take is not rewritten here (Context-IR is H3's own rewriter).
    api = _run(client, shot["video_product_id"], model="minimax/h3-api")["versions"][-1]
    assert "prompt_rewrite" not in api["payload"] and len(_rewrites(client)) == 1


def test_the_rewrite_is_told_what_the_first_frame_shows(client: TestClient) -> None:
    """M5 step 15g: before a local H3 take is rewritten, the vlook route describes the first
    frame (the locked keyframe; a continuous shot's, the last frame of the take it follows),
    once per picture; a look that fails leaves the plan's words."""
    _confirm_storyboard(client)
    mock = _state(client).registry.mock_settings
    told: list[dict[str, Any]] = []
    looked: list[ModelRequest] = []
    rewrite, look = mock.responders[("vid", "h3_prompt")], mock.responders[("vid", vlook.TASK)]

    def spy_rewrite(req: ModelRequest) -> Any:
        told.append(json.loads(str((req.messages or [])[1]["content"])))
        return rewrite(req)

    def spy_look(req: ModelRequest) -> Any:
        looked.append(req)
        return look(req)

    mock.responders[("vid", "h3_prompt")] = spy_rewrite
    mock.responders[("vid", vlook.TASK)] = spy_look
    shots = _shots(client)
    _run(client, shots["1-01"]["video_product_id"])  # two takes, one look
    _run(client, shots["1-01"]["video_product_id"])  # 「再出一条」: the cache
    (asked,) = looked
    text, picture = (asked.messages or [])[0]["content"]
    assert "first frame of a video shot" in text["text"]
    assert picture["image_url"]["url"].startswith("data:image/png;base64,")
    assert told and told[0]["pictures"][0]["description"] == vlook.MOCK_TEXT
    # Step 15j: paced over what H3 renders (a 4 s shot is 124 frames), not the shot's seconds.
    assert shots["1-01"]["duration_s"] == 4 and told[0]["duration_s"] == 5.17
    (call,) = _rows(client, ModelCall, ModelCall.component_id == vlook.VLOOK)
    assert (call.model_key, call.shot_id, call.status) == (
        "google/gemini-3.1-flash-lite",
        "demo-shot-1-01",
        "success",
    )
    assert call.cost_usd > 0

    # A look that fails: the plan's words, and the take is made.
    mock.fail_keys.add("google/gemini-3.1-flash-lite")
    told.clear()
    keyframe = client.get(f"{V1}/products/{shots['1-02']['keyframe_product_id']}").json()
    take = _run(client, shots["1-02"]["video_product_id"], count=1)["versions"][-1]
    assert take["where"] == "local"
    assert told[0]["pictures"][0]["description"] == keyframe["prompt"]["intent"]  # the plan's


def test_a_rewrite_that_never_fits_the_layout_makes_no_take(client: TestClient) -> None:
    """Asked again once with what is wrong; still wrong, the run fails and nothing is made."""
    _confirm_storyboard(client)
    asked: list[ModelRequest] = []

    def wrong(req: ModelRequest) -> str:
        asked.append(req)
        return "integrated_multimodal_description: [Shot 1] 林晚走上楼梯。"

    _state(client).registry.add_mock_responder("vid", "h3_prompt", wrong)
    product_id = _shots(client)["1-01"]["video_product_id"]
    resp = client.post(f"{V1}/products/{product_id}/run", json={"mode": "run"})
    deadline = time.monotonic() + 60
    while (job := client.get(f"{V1}/jobs/{resp.json()['id']}").json())["state"] not in (
        "succeeded",
        "failed",
    ):
        assert time.monotonic() < deadline
        time.sleep(0.02)
    assert job["state"] == "failed" and job["error"]["code"] == "prompt_not_conformant"
    assert "first line must be exactly" in job["error"]["params"]["errors"]
    assert len(asked) == 2 and len(_rewrites(client)) == 2
    fix = (asked[1].messages or [])[-1]["content"]
    assert fix.startswith("This does not follow the official H3 layout yet.")
    assert "Write every section in English" in fix
    assert client.get(f"{V1}/products/{product_id}").json()["versions"] == []


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
    # Mock bills the tier the real adapter would (step 13: it used to cost 0 at "1080p").
    videos = _rows(client, ModelCall, ModelCall.model_key == "minimax/h3-api")
    assert len(videos) == 2 and all(c.cost_usd > ir[0].cost_usd for c in videos)

    take = _run(client, shots["1-04"]["video_product_id"], model="minimax/h3-api")["versions"][0]
    assert take["model_key"] == "minimax/h3-api" and take["payload"]["voices"]
    text = _prompt(client, take)
    assert text.startswith("[Context-IR] subject_definitions:\n<Picture 1> is the first frame")
    assert "<Audio 1> is the voice-timbre reference for" in text

    # 先配音: the dubbed lines are <Audio 1>, copied as the whole sound track.
    _on_screen(client, shots["1-06"])
    _dub_shot(client, shots["1-06"])
    take = _run(client, shots["1-06"]["video_product_id"], model="minimax/h3-api")["versions"][0]
    text = _prompt(client, take)
    assert "<Audio 1>: fully_copy - <Audio 1> is reused 1:1" in text
    assert "overall_soundscape: <Audio 1> as it is, with no other sound." in text


def _seconds(client: TestClient, sha: str) -> float:
    data = _state(client).store.path_for(sha).read_bytes()
    with wave.open(io.BytesIO(data)) as w:
        return w.getnframes() / w.getframerate()


def test_the_h3_api_gets_a_voice_sample_long_enough(client: TestClient) -> None:
    """M5 step 15b (Kelvin 2026-11-08): the H3 API wants 2–15 s of voice; a shorter anchor is
    joined with the voice's other clips (never repeated or padded), and when even all of them
    are too short the take stops before anything is paid for."""
    _confirm_storyboard(client)
    pid = _shots(client)["1-04"]["video_product_id"]
    spec = _state(client).registry.spec("minimax/h3-api")
    extra = spec.caps.model_extra
    assert extra is not None and extra["audio_s"] == [2, 15]
    try:
        extra["audio_s"] = [6, 15]  # above any one Mock clip: the anchor gets joined
        take = _run(client, pid, model="minimax/h3-api")["versions"][0]
        (sample,) = take["params"]["request"]["ref_audio"]
        local = _run(client, pid, model="comfy/h3-r2v")["versions"][-1]
        (anchor,) = local["params"]["request"]["ref_audio"]  # locally: the anchor as it is
        assert sample != anchor and 6 <= _seconds(client, sample) <= 15
        assert _seconds(client, anchor) < 6

        extra["audio_s"] = [600, 900]  # longer than the voice has
        before = len(_rows(client, ModelCall, ModelCall.model_key == "minimax/h3-api"))
        body = {"mode": "run", "model": "minimax/h3-api"}
        job = client.post(f"{V1}/products/{pid}/run", json=body).json()
        deadline = time.monotonic() + 60
        while job["state"] not in ("succeeded", "failed", "canceled"):
            assert time.monotonic() < deadline, "the job did not finish"
            time.sleep(0.02)
            job = client.get(f"{V1}/jobs/{job['id']}").json()
        assert job["state"] == "failed" and job["error"]["code"] == "voice_sample_short"
        after = len(_rows(client, ModelCall, ModelCall.model_key == "minimax/h3-api"))
        assert after == before
    finally:
        extra["audio_s"] = [2, 15]


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
    # The take cards price the button the same way (the product's estimate).
    shown = client.get(f"{V1}/products/{pid}").json()["estimate"]["final_usd"]
    assert shown == pytest.approx(estimate, abs=0.001)

    job = _final(client, pid, draft["id"])
    assert job["state"] == "succeeded", job
    product = client.get(f"{V1}/products/{pid}").json()
    assert len(product["versions"]) == 3  # two takes and one final, not two
    final = next(v for v in product["versions"] if v["stage"] == "final")
    assert final["model_key"] == "minimax/h3-regenerate-2k" and final["where"] == "api"
    assert final["parent_version_id"] == draft["id"]
    assert final["payload"]["resolution"] == "2k"
    assert [f["role"] for f in final["files"]] == [
        "video",
        "poster",
        "last_frame",
        "sheet",
        "prompt",
    ]
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
    _on_screen(client, shots["1-06"])  # an inner voice needs no dub before the take (15p)
    code, error, params = _refused(client, shots["1-06"]["video_product_id"])
    assert (code, error) == (409, "line_audio_missing") and params["count"] >= 1


def test_a_continuing_local_take_is_guided_with_the_tail_of_the_one_before(
    client: TestClient,
) -> None:
    """M5 step 15e (末尾片段续写): 1-08's local H3 take gets 1-06's adopted take's last 22 frames
    with their sound, asks 22 frames more and loses them again (not 0.3 s); its final is cut
    the same way; the API fallback, which takes no clip, starts from the last frame."""
    _confirm_storyboard(client)
    shots = _shots(client)
    _on_screen(client, shots["1-06"])
    _dub_shot(client, shots["1-06"])
    before = _run(client, shots["1-06"]["video_product_id"], count=1)["versions"][-1]
    _adopt(client, before)
    last = next(f for f in before["files"] if f["role"] == "last_frame")

    pid = shots["1-08"]["video_product_id"]
    take = _run(client, pid, count=1)["versions"][-1]
    assert (take["model_key"], take["where"]) == ("comfy/h3", "local")
    sent = take["params"]["request"]
    seconds = shots["1-08"]["duration_s"]
    assert (sent["tail_frames"], sent["first_frame"]) == (22, last["sha256"])
    looks = _rows(client, ModelCall, ModelCall.component_id == vlook.VLOOK)
    assert {c.shot_id for c in looks} == {
        "demo-shot-1-06",
        "demo-shot-1-08",
    }  # 1-08: its last frame
    assert sent["duration_s"] == pytest.approx(seconds + 22 / 24, abs=0.01)
    tail = client.portal.call(probe, client.get(f"{V1}/files/{sent['tail_clip']}").content)  # type: ignore[union-attr]
    assert tail.duration_s == pytest.approx(22 / 24, abs=0.05) and tail.has_audio
    video = take["files"][0]
    raw = next(f for f in take["files"] if f["role"] == "raw")
    assert video["duration_s"] == pytest.approx(seconds, abs=0.1)
    assert raw["duration_s"] == pytest.approx(seconds + 22 / 24, abs=0.1)

    _adopt(client, take)
    job = _final(client, pid, take["id"])
    assert job["state"] == "succeeded", job
    final = next(
        v for v in client.get(f"{V1}/products/{pid}").json()["versions"] if v["stage"] == "final"
    )
    assert final["files"][0]["duration_s"] == pytest.approx(seconds, abs=0.1)

    _state(client).registry.mock_settings.fail_keys.add("comfy/h3")
    api = _run(client, pid)["versions"][-1]
    assert (api["model_key"], api["origin"]) == ("minimax/h3-api", "fallback")
    sent = api["params"]["request"]
    assert "tail_clip" not in sent and sent["first_frame"] == last["sha256"]
    assert api["files"][0]["duration_s"] == pytest.approx(seconds - 0.3, abs=0.1)


def _on_screen(client: TestClient, shot: dict[str, Any]) -> None:
    """Make the shot's spoken lines said on screen: 1-06's only line is 林晚's inner voice,
    which is laid in the edit, not made in the take (M5 step 15p). The script says dialogue and
    the shot's contract (M5.5) says it is delivered on screen, as a new plan would."""

    async def write() -> None:
        async with _state(client).db.session() as s:
            ids = [str(x) for x in shot["line_ids"]]
            for row in (await s.exec(select(ScriptLine).where(col(ScriptLine.id).in_(ids)))).all():
                if row.type == "vo":
                    row.type = "dialogue"
                    s.add(row)
            plan = (
                await s.exec(
                    select(Product).where(
                        Product.owner_id == shot["episode_id"], Product.slot == "shot_plan"
                    )
                )
            ).one()
            version = await s.get(ProductVersion, plan.adopted_version_id)
            assert version is not None
            payload = json.loads(json.dumps(version.payload_json))
            for x in payload["shots"]:
                if x["id"] == shot["id"] and x.get("contract"):
                    x["contract"]["delivery"] = {i: "dialogue" for i in x["contract"]["delivery"]}
                    x["contract"]["kind"] = "dialogue"
            version.payload_json = payload
            s.add(version)
            await s.commit()

    client.portal.call(write)  # type: ignore[union-attr]


def test_an_inner_voice_is_left_out_of_the_take_and_an_insert_moves_little(
    client: TestClient,
) -> None:
    """M5 steps 15o, 15p: 1-06's only line is 林晚's inner voice (vo): the take gets no dubbed
    track and no line to say, the draft says it is laid in the edit; 1-03 (the note, no one in
    it) is rewritten as an insert, 1-06 as a performance."""
    _confirm_storyboard(client)
    mock = _state(client).registry.mock_settings
    told: list[dict[str, Any]] = []
    rewrite = mock.responders[("vid", "h3_prompt")]

    def spy(req: ModelRequest) -> Any:
        told.append(json.loads(str((req.messages or [])[1]["content"])))
        return rewrite(req)

    mock.responders[("vid", "h3_prompt")] = spy
    shots = _shots(client)
    _dub_shot(client, shots["1-06"])  # dubbed for the edit; the take does not use it
    take = _run(client, shots["1-06"]["video_product_id"], count=1)["versions"][-1]
    sent = take["params"]["request"]
    assert "dialogue_audio" not in sent and take["payload"]["voices"] == []
    assert told[-1]["dialogue"] == [] and told[-1]["shot_kind"] == "performance"
    assert "剪辑时另铺" in told[-1]["draft"] and "三年了。他凭什么。" in told[-1]["draft"]
    assert "<d>" not in _prompt(client, take)
    assert "（内心独白）" in told[-1]["draft"] and told[-1]["end"] == [
        "林晚：背靠着门",
        "家门：关着",
    ]
    _run(client, shots["1-03"]["video_product_id"], count=1)
    assert told[-1]["shot_kind"] == "insert" and told[-1]["beats"] == 0
    assert "插入镜头：只许微动" in told[-1]["draft"]


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
    _on_screen(client, shots["1-06"])
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


def test_each_take_is_checked(client: TestClient) -> None:
    """take 检查 (M5.5 step 7): the take's six frames on a sheet (kept as its ``sheet`` file),
    looked at against the contract; a cut and a still opening measured; only a warning."""
    _confirm_storyboard(client)
    shots = _shots(client)
    take = _run(client, shots["1-03"]["video_product_id"], count=1)["versions"][-1]
    check = take["payload"]["check"]
    found = {x["check"]: x["ok"] for x in check["items"]}
    assert set(found) == {"repeat", "event", "text", "cut", "hold"}  # 1-03: the note's words
    assert found["cut"] is True and check["model"] == "google/gemini-3.1-flash-lite"
    assert len(take["payload"]["sheet_times"]) == 6
    assert "sheet" in {f["role"] for f in take["files"]}
    calls = [c for c in _rows(client, ModelCall) if c.component_id == "takecheck"]
    assert len(calls) == 1


def test_a_picture_the_user_wrote_replaces_the_scripts_action_lines(client: TestClient) -> None:
    """Kelvin 2026-11-10 (run 19): the script's 「拉开门，又关上……再拉开」 is not read beside a
    picture description the user wrote; a shot left as planned still gets its action lines."""
    shots = _shots(client)
    client.patch(f"{V1}/shots/{shots['1-02']['id']}", json={"confirmed": False})
    resp = client.patch(
        f"{V1}/shots/{shots['1-02']['id']}", json={"intent": "门口：伞柄上的便利贴，近一点。"}
    )
    assert resp.status_code == 200, resp.text
    _confirm_storyboard(client)

    async def look(label: str) -> str:
        state = _state(client)
        component = state.components.get("vid")
        assert component is not None
        async with state.db.session() as session:
            product = await session.get(Product, shots[label]["video_product_id"])
            assert product is not None
            inputs = await component.inputs(session, product)
        return next(b.text for b in inputs.blocks if b.title == "镜头")

    edited = client.portal.call(look, "1-02")  # type: ignore[union-attr]
    planned = client.portal.call(look, "1-01")  # type: ignore[union-attr]
    assert "门口靠着一把红色长柄伞" not in edited, edited
    assert "画板" in planned, planned
