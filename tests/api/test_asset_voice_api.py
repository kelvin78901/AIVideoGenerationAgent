"""音色 (SPEC 5 ``voice``; M3 step 6), in Mock mode: free local auditions, the MiniMax final
(design + five emotions, the 9.90 元 design fee + characters), the local final, levelling and
locking.

The demo seeds 林晚's voice: three auditions reading her two lines, then the MiniMax final from
A, locked whole. 周屿 (vzhouyu) has no lines in episode 1, so his auditions read the sample.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlmodel import select

from drama_series_agent.api.app import create_app
from drama_series_agent.api.state import StudioState
from drama_series_agent.core.config import get_config
from drama_series_agent.core.models_db import GateDecision, ModelCall, Product
from drama_series_agent.media.audio import measure
from drama_series_agent.modelhub.adapters.mock import sine_wav
from drama_series_agent.pipeline.component import RunContext
from drama_series_agent.pipeline.components.voice import VoiceComponent
from drama_series_agent.pipeline.hashing import hash_json

LOCAL = "http://127.0.0.1"
V1 = "/api/v1"
EMOTIONS = ["calm", "angry", "crying", "whisper", "shout"]
CNY = 7.1  # providers.yaml currency_rates
PER_CHAR = 350 / 1e6 / CNY  # MiniMax Speech HD (China), per character
DESIGN = 9.90 / CNY  # the voice design fee, on the first synthesis
CLONE = 9.90 / CNY  # a clone's (国内站 快速复刻), also on the first synthesis


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(), base_url=LOCAL, headers={"X-Drama-Studio": "1"}) as c:
        yield c


def _state(client: TestClient) -> StudioState:
    state: StudioState = client.app.state.studio  # type: ignore[attr-defined]
    return state


def _rows(client: TestClient, model: Any) -> list[Any]:
    async def read() -> list[Any]:
        async with _state(client).db.session() as s:
            return list((await s.exec(select(model))).all())

    return list(client.portal.call(read))  # type: ignore[union-attr]


def _product(client: TestClient, asset_id: str) -> dict[str, Any]:
    product: dict[str, Any] = client.get(f"{V1}/products/demo-p-asset-{asset_id}").json()
    return product


def _latest(client: TestClient, asset_id: str) -> dict[str, Any]:
    version: dict[str, Any] = _product(client, asset_id)["versions"][-1]
    return version


def _wait(client: TestClient, job_id: str, *states: str) -> dict[str, Any]:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        job: dict[str, Any] = client.get(f"{V1}/jobs/{job_id}").json()
        if job["state"] in (states or ("succeeded", "failed", "canceled")):
            return job
        time.sleep(0.02)
    raise AssertionError("job did not get there")


def _run(client: TestClient, asset_id: str, **body: Any) -> dict[str, Any]:
    resp = client.post(f"{V1}/products/demo-p-asset-{asset_id}/run", json={"mode": "run", **body})
    assert resp.status_code == 200, resp.text
    return resp.json()  # type: ignore[no-any-return]


def _done(client: TestClient, asset_id: str, **body: Any) -> dict[str, Any]:
    job = _wait(client, _run(client, asset_id, **body)["id"])
    assert job["state"] == "succeeded", job
    return job


def _final(client: TestClient, asset_id: str, draft: dict[str, Any], idx: int) -> dict[str, Any]:
    """「用 MiniMax 出终版」 from candidate ``idx``: about $1.40, under the $3 cap, so it runs
    without asking."""
    params = {"source_version_id": draft["id"], "source_idx": idx}
    job = _wait(client, _run(client, asset_id, where="api", params=params)["id"])
    assert "confirm" not in (job["params"] or {})
    assert job["state"] == "succeeded", job
    return job


def _by_role(version: dict[str, Any], role: str) -> list[dict[str, Any]]:
    return [f for f in version["files"] if f["role"] == role]


def test_the_demo_voice_is_a_locked_final(client: TestClient) -> None:
    voice = _product(client, "vlinwan")
    draft, final = voice["versions"]
    assert (draft["stage"], draft["model_key"], draft["cost_usd"]) == (
        "draft", "local/qwen3-tts", 0
    )  # fmt: skip
    labels = [c["label"] for c in draft["payload"]["candidates"]]
    assert labels == ["偏低沉", "更清亮", "带一点沙哑"]
    cands = _by_role(draft, "candidate")
    assert [(f["idx"], f["line"]) for f in cands] == [(i, j) for i in range(3) for j in range(2)]
    assert all(len(f["waveform"]) == 64 and f["duration_s"] for f in cands)
    assert (final["stage"], final["parent_version_id"]) == ("final", draft["id"])
    assert final["payload"]["emotions"] == EMOTIONS
    assert [f["emotion"] for f in _by_role(final, "variant")] == EMOTIONS
    assert len(_by_role(final, "anchor")) == 1
    assert voice["adopted_version_id"] == final["id"] and voice["locked_hash"]
    resp = client.get(f"{V1}/files/{cands[0]['sha256']}")
    assert resp.status_code == 200 and resp.headers["content-type"] == "audio/wav"


def test_auditions_read_the_characters_lines(client: TestClient) -> None:
    """林晚's first two lines in script order; a voice without lines reads the sample."""
    state = _state(client)
    comp = state.components.get("voice")
    assert isinstance(comp, VoiceComponent)

    async def lines(asset_id: str) -> list[dict[str, Any]]:
        async with state.db.session() as s:
            product = await s.get(Product, f"demo-p-asset-{asset_id}")
            assert product is not None
            got: list[dict[str, Any]] = (await comp.inputs(s, product)).context["lines"]
            return got

    linwan = client.portal.call(lines, "vlinwan")  # type: ignore[union-attr]
    assert [(x["text"], x["tone"]) for x in linwan] == [
        ("……周屿？", "低声，愣住"),
        ("三年了。他凭什么。", "OS"),
    ]
    zhouyu = client.portal.call(lines, "vzhouyu")  # type: ignore[union-attr]
    assert [x["text"] for x in zhouyu] == [get_config().voice.sample_text]


def test_auditions_then_the_minimax_final_then_lock(client: TestClient) -> None:
    job = _done(client, "vzhouyu")
    assert job["queue"] == "gpu" and job["est_cost_usd"] == 0
    draft = _latest(client, "vzhouyu")
    assert (draft["stage"], draft["model_key"], draft["cost_usd"]) == (
        "draft", "local/qwen3-tts", 0
    )  # fmt: skip
    assert len(_by_role(draft, "candidate")) == 3  # the sample, read three ways
    # An audition is not a voice yet.
    resp = client.post(f"{V1}/assets/vzhouyu/lock")
    assert resp.status_code == 409 and resp.json()["detail"]["code"] == "voice_needs_final"

    job = _final(client, "vzhouyu", draft, 1)
    final = _latest(client, "vzhouyu")
    assert (final["stage"], final["parent_version_id"]) == ("final", draft["id"])
    assert final["model_key"] == "minimax/speech-2.8-hd"
    payload = final["payload"]
    assert payload["provider"] == "minimax" and payload["voice_id"].startswith("mock-voice-")
    assert (payload["emotions"], payload["label"]) == (EMOTIONS, "更清亮")
    variants = _by_role(final, "variant")
    assert [(f["emotion"], f["idx"]) for f in variants] == [(e, i) for i, e in enumerate(EMOTIONS)]
    assert len(_by_role(final, "anchor")) == 1  # the design's trial clip

    calls = [c for c in _rows(client, ModelCall) if c.job_id == job["id"]]
    assert len(calls) == 6 and all(c.status == "success" for c in calls)
    # Whisper on 2.6 HD (2.8 has none); the design fee on the first synthesis with the voice.
    assert [c.model_key for c in calls].count("minimax/speech-2.6-hd") == 1
    sample = len(get_config().voice.sample_text)
    assert sorted(round(c.cost_usd, 6) for c in calls) == sorted(
        [round(sample * PER_CHAR, 6)] * 5 + [round(DESIGN + sample * PER_CHAR, 6)]
    )
    assert final["cost_usd"] == pytest.approx(DESIGN + 6 * sample * PER_CHAR)
    assert job["est_cost_usd"] == pytest.approx(final["cost_usd"])

    resp = client.post(f"{V1}/assets/vzhouyu/lock")
    assert resp.status_code == 200, resp.text
    voice = _product(client, "vzhouyu")
    assert voice["adopted_version_id"] == final["id"]  # locked whole, no pick version
    shas = sorted(f["sha256"] for f in final["files"] if f["role"] != "prompt")
    expected = hash_json({"payload": payload, "files": shas})
    assert voice["locked_hash"] == expected
    (gate,) = [g for g in _rows(client, GateDecision) if g.scope_id == "vzhouyu"]
    assert gate.product_hashes_json == {voice["id"]: expected}


def test_a_retried_final_neither_designs_nor_pays_again(client: TestClient) -> None:
    _done(client, "vzhouyu")
    draft = _latest(client, "vzhouyu")
    job = _final(client, "vzhouyu", draft, 0)
    final = _latest(client, "vzhouyu")
    before = len(_rows(client, ModelCall))
    state = _state(client)
    comp = state.components.get("voice")
    assert isinstance(comp, VoiceComponent)

    async def again() -> Any:
        async with state.db.session() as s:
            product = await s.get(Product, "demo-p-asset-vzhouyu")
            assert product is not None
            inputs = await comp.inputs(s, product)
        inputs.params = {"source_version_id": draft["id"], "source_idx": 0}
        ctx = RunContext(
            product=product,
            mode="run",
            model_key="minimax/speech-2.8-hd",
            seed=int(job["params"]["seed"]),
            intent=final["intent"],
            compiled=final["compiled"],
            compiled_overridden=False,
        )
        return await comp.run(ctx, inputs)

    redo = client.portal.call(again)  # type: ignore[union-attr]
    assert len(_rows(client, ModelCall)) == before  # every call came from the cache
    assert redo.cost_usd == 0
    assert redo.payload["voice_id"] == final["payload"]["voice_id"]


def test_a_failing_final_is_made_locally_as_a_whole(client: TestClient) -> None:
    _done(client, "vzhouyu")
    draft = _latest(client, "vzhouyu")
    _state(client).registry.mock_settings.fail_keys.add("minimax/speech-2.6-hd")  # whisper
    _final(client, "vzhouyu", draft, 2)
    final = _latest(client, "vzhouyu")
    assert (final["origin"], final["fallback_reason"]) == ("fallback", "error")
    assert final["model_key"] == "local/indextts2" and final["cost_usd"] == 0
    assert final["payload"]["provider"] == "local" and final["payload"]["voice_id"] is None
    # The anchor is the picked audition itself; every emotion is IndexTTS's.
    anchors = _by_role(final, "anchor")
    picked = [f for f in _by_role(draft, "candidate") if f["idx"] == 2]
    assert [f["sha256"] for f in anchors] == [f["sha256"] for f in picked]
    assert len(_by_role(final, "variant")) == 5


def test_a_local_voice_is_free(client: TestClient) -> None:
    resp = client.patch(f"{V1}/assets/vzhouyu", json={"voice": {"method": "local"}})
    assert resp.json()["voice"]["method"] == "local"
    _done(client, "vzhouyu")
    draft = _latest(client, "vzhouyu")
    params = {"source_version_id": draft["id"], "source_idx": 0}
    job = _done(client, "vzhouyu", where="local", params=params)
    assert job["est_cost_usd"] == 0
    final = _latest(client, "vzhouyu")
    assert (final["stage"], final["model_key"], final["cost_usd"]) == (
        "final", "local/indextts2", 0
    )  # fmt: skip
    assert final["payload"]["provider"] == "local"
    calls = [c for c in _rows(client, ModelCall) if c.job_id == job["id"]]
    assert {c.model_key for c in calls} == {"local/indextts2"} and len(calls) == 5
    assert client.post(f"{V1}/assets/vzhouyu/lock").status_code == 200


def _sample(
    client: TestClient, seconds: float = 12.0, name: str = "me.wav", rate: int = 48000
) -> Any:
    files = {"file": (name, sine_wav(seconds, rate=rate), "audio/wav")}
    return client.post(f"{V1}/assets/vzhouyu/voice/sample", files=files)


def _clone_ready(client: TestClient) -> dict[str, Any]:
    """周屿's source is 声音克隆, with a 12 s sample and the 本人授权 box ticked."""
    client.patch(f"{V1}/assets/vzhouyu", json={"voice": {"method": "clone"}}).raise_for_status()
    assert _sample(client).status_code == 200
    resp = client.patch(f"{V1}/assets/vzhouyu", json={"voice": {"consent": True}})
    voice: dict[str, Any] = resp.json()["voice"]
    assert (voice["method"], voice["consent"]) == ("clone", True)
    return voice


def test_a_clone_needs_a_sample_and_the_speakers_consent(client: TestClient) -> None:
    client.patch(f"{V1}/assets/vzhouyu", json={"voice": {"method": "clone"}})
    run = f"{V1}/products/demo-p-asset-vzhouyu/run"
    resp = client.post(run, json={"mode": "run"})
    assert resp.status_code == 409 and resp.json()["detail"]["code"] == "voice_sample_missing"

    resp = _sample(client)
    assert resp.status_code == 200, resp.text
    voice = resp.json()["voice"]
    sample = voice["sample"]
    assert (voice["method"], voice["consent"]) == ("clone", False)
    assert (sample["name"], sample["duration_s"]) == ("me.wav", 12.0)
    assert sample["clip_s"] == pytest.approx(12.0, abs=0.05)  # the levelled clip
    assert len(sample["waveform"]) == 64
    assert client.get(f"{V1}/files/{sample['sha256']}").status_code == 200
    resp = client.post(run, json={"mode": "run"})
    assert resp.status_code == 409 and resp.json()["detail"]["code"] == "voice_clone_consent"
    # Still priced before the box is ticked: the page shows what a clone costs.
    estimate = _product(client, "vzhouyu")["estimate"]
    sample_chars = len(get_config().voice.sample_text)
    assert (estimate["model_key"], estimate["cost_usd"]) == ("local/indextts2", 0)
    assert estimate["final_usd"] == pytest.approx(CLONE + 5 * sample_chars * PER_CHAR, abs=1e-4)

    resp = client.patch(f"{V1}/assets/vzhouyu", json={"voice": {"consent": True}})
    assert resp.json()["voice"]["consent"] is True
    assert resp.json()["voice"]["method"] == "clone"  # the method stays
    # A new sample may be someone else: the box is unticked again.
    other = _sample(client, 20.0, "other.wav").json()["voice"]
    assert other["consent"] is False
    assert other["sample"]["duration_s"] == 20.0 and other["sample"]["clip_s"] == 15.0


def test_a_sample_is_checked_like_minimax_checks_it(client: TestClient) -> None:
    resp = _sample(client, 6.0)
    assert resp.status_code == 422 and resp.json()["detail"]["code"] == "voice_sample_too_short"
    resp = _sample(client, 301.0, rate=8000)
    assert resp.status_code == 422 and resp.json()["detail"]["code"] == "voice_sample_too_long"
    files = {"file": ("notes.txt", b"hello there, not a sound", "text/plain")}
    resp = client.post(f"{V1}/assets/vzhouyu/voice/sample", files=files)
    assert resp.status_code == 422 and resp.json()["detail"]["code"] == "not_audio"
    # Only a voice takes one; a locked voice refuses.
    files = {"file": ("me.wav", sine_wav(12.0), "audio/wav")}
    resp = client.post(f"{V1}/assets/linwan/voice/sample", files=files)
    assert resp.status_code == 422 and resp.json()["detail"]["code"] == "upload_not_supported"
    resp = client.post(f"{V1}/assets/vlinwan/voice/sample", files=files)
    assert resp.status_code == 409 and resp.json()["detail"]["code"] == "product_locked"


def test_a_local_clone_reads_with_the_sample_for_free(client: TestClient) -> None:
    """No auditions: the run is a final, IndexTTS with the sample as its reference."""
    voice = _clone_ready(client)
    job = _done(client, "vzhouyu")
    assert job["est_cost_usd"] == 0
    final = _latest(client, "vzhouyu")
    assert (final["stage"], final["model_key"], final["cost_usd"]) == (
        "final", "local/indextts2", 0
    )  # fmt: skip
    assert final["payload"]["provider"] == "local" and final["payload"]["cloned"] is True
    (anchor,) = _by_role(final, "anchor")
    assert anchor["sha256"] == voice["sample"]["sha256"]
    assert len(_by_role(final, "variant")) == 5
    calls = [c for c in _rows(client, ModelCall) if c.job_id == job["id"]]
    assert {c.model_key for c in calls} == {"local/indextts2"} and len(calls) == 5
    assert client.post(f"{V1}/assets/vzhouyu/lock").status_code == 200


def test_a_minimax_clone_pays_its_fee_on_the_first_synthesis(client: TestClient) -> None:
    voice = _clone_ready(client)
    job = _done(client, "vzhouyu", where="api")
    final = _latest(client, "vzhouyu")
    assert (final["stage"], final["model_key"]) == ("final", "minimax/speech-2.8-hd")
    payload = final["payload"]
    assert payload["provider"] == "minimax" and payload["cloned"] is True
    assert payload["voice_id"].startswith("ds") and len(payload["voice_id"]) == 24
    assert [f["sha256"] for f in _by_role(final, "anchor")] == [voice["sample"]["sha256"]]
    assert [f["emotion"] for f in _by_role(final, "variant")] == EMOTIONS

    calls = [c for c in _rows(client, ModelCall) if c.job_id == job["id"]]
    assert len(calls) == 6 and all(c.status == "success" for c in calls)
    sample = len(get_config().voice.sample_text)
    assert sorted(round(c.cost_usd, 6) for c in calls) == sorted(
        [0.0] + [round(sample * PER_CHAR, 6)] * 4 + [round(CLONE + sample * PER_CHAR, 6)]
    )
    assert final["cost_usd"] == pytest.approx(CLONE + 5 * sample * PER_CHAR)
    assert job["est_cost_usd"] == pytest.approx(final["cost_usd"])


def test_a_failing_clone_is_made_locally_as_a_whole(client: TestClient) -> None:
    voice = _clone_ready(client)
    _state(client).registry.mock_settings.fail_keys.add("minimax/speech-2.6-hd")  # whisper
    _done(client, "vzhouyu", where="api")
    final = _latest(client, "vzhouyu")
    assert (final["origin"], final["fallback_reason"]) == ("fallback", "error")
    assert final["model_key"] == "local/indextts2" and final["cost_usd"] == 0
    assert final["payload"]["voice_id"] is None
    assert [f["sha256"] for f in _by_role(final, "anchor")] == [voice["sample"]["sha256"]]


def test_samples_are_levelled(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """With the loudness pass on (tests skip it by default): −18 LUFS ± 0.5."""
    monkeypatch.delenv("DRAMA_FAST_AUDIO")
    _done(client, "vzhouyu")
    clip = _by_role(_latest(client, "vzhouyu"), "candidate")[0]
    path = Path(_state(client).store.path_for(clip["sha256"]))
    lufs = measure(path).lufs
    assert lufs is not None and abs(lufs - get_config().components.audio.dialogue.lufs) <= 0.5


MINIMAX = "https://api.minimax.cn/v1"


@respx.mock(assert_all_called=False)
def test_the_minimax_final_through_the_real_adapter(
    client: TestClient, respx_mock: respx.MockRouter
) -> None:
    """The same final against a fake MiniMax: one design, five syntheses (whisper on 2.6), the
    design fee on the synthesis MiniMax bills it on, characters as MiniMax counts them."""
    respx_mock.route(host="127.0.0.1").pass_through()
    _done(client, "vzhouyu")  # Mock auditions
    draft = _latest(client, "vzhouyu")
    client.post(f"{V1}/providers/minimax_llm/key", json={"api_key": "mm-test"}).raise_for_status()
    registry = _state(client).registry
    registry.mock = False
    registry._adapters.clear()

    wav = sine_wav(0.6).hex()
    design = respx_mock.post(f"{MINIMAX}/voice_design").mock(
        return_value=httpx.Response(
            200,
            json={"voice_id": "ttv-zhouyu", "trial_audio": wav, "base_resp": {"status_code": 0}},
        )
    )
    billed = 2 * len(get_config().voice.sample_text)  # all CJK: counted twice
    first = {"usage_characters": billed, "audio_length": 600, "usage_voice_count": 1}
    rest = {"usage_characters": billed, "audio_length": 600}
    t2a = respx_mock.post(f"{MINIMAX}/t2a_v2").mock(
        side_effect=[
            httpx.Response(
                200,
                json={"data": {"audio": wav}, "extra_info": info, "base_resp": {"status_code": 0}},
            )
            for info in (first, rest, rest, rest, rest)
        ]
    )
    job = _final(client, "vzhouyu", draft, 0)

    assert design.call_count == 1 and t2a.call_count == 5
    bodies = [json.loads(c.request.content) for c in t2a.calls]
    assert {b["voice_setting"]["voice_id"] for b in bodies} == {"ttv-zhouyu"}
    assert [(b["model"], b["voice_setting"].get("emotion")) for b in bodies] == [
        ("speech-2.8-hd", "calm"),
        ("speech-2.8-hd", "angry"),
        ("speech-2.8-hd", "sad"),
        ("speech-2.6-hd", "whisper"),
        ("speech-2.8-hd", "angry"),
    ]
    assert bodies[4]["voice_setting"]["vol"] == 2.0  # shout
    final = _latest(client, "vzhouyu")
    assert final["payload"]["voice_id"] == "ttv-zhouyu"
    calls = [c for c in _rows(client, ModelCall) if c.job_id == job["id"]]
    assert len(calls) == 6 and all(c.status == "success" for c in calls)
    # the trial clip (2.00 元 / 万字符), the design fee, five lines
    expected = billed * 0.0002 / CNY + DESIGN + 5 * billed * PER_CHAR
    assert final["cost_usd"] == pytest.approx(expected)
    assert job["est_cost_usd"] == pytest.approx(expected)


@respx.mock(assert_all_called=False)
def test_a_clone_through_the_real_adapter(client: TestClient, respx_mock: respx.MockRouter) -> None:
    """Against a fake MiniMax: the sample uploaded (``purpose=voice_clone``), cloned under our
    voice_id, five syntheses; the clone's fee on the one MiniMax bills it on."""
    respx_mock.route(host="127.0.0.1").pass_through()
    _clone_ready(client)
    client.post(f"{V1}/providers/minimax_llm/key", json={"api_key": "mm-test"}).raise_for_status()
    registry = _state(client).registry
    registry.mock = False
    registry._adapters.clear()

    ok = {"base_resp": {"status_code": 0}}
    upload = respx_mock.post(f"{MINIMAX}/files/upload").mock(
        return_value=httpx.Response(200, json={"file": {"file_id": 4242}, **ok})
    )
    clone = respx_mock.post(f"{MINIMAX}/voice_clone").mock(
        return_value=httpx.Response(200, json={"input_sensitive": {"type": 0}, **ok})
    )
    wav = sine_wav(0.6).hex()
    billed = 2 * len(get_config().voice.sample_text)
    first = {"usage_characters": billed, "audio_length": 600, "usage_voice_count": 1}
    rest = {"usage_characters": billed, "audio_length": 600}
    t2a = respx_mock.post(f"{MINIMAX}/t2a_v2").mock(
        side_effect=[
            httpx.Response(200, json={"data": {"audio": wav}, "extra_info": info, **ok})
            for info in (first, rest, rest, rest, rest)
        ]
    )
    job = _done(client, "vzhouyu", where="api")

    assert upload.call_count == 1 and clone.call_count == 1 and t2a.call_count == 5
    sent = upload.calls[0].request
    assert b'name="purpose"' in sent.content and b"voice_clone" in sent.content
    assert sent.headers["content-type"].startswith("multipart/form-data")
    body = json.loads(clone.calls[0].request.content)
    final = _latest(client, "vzhouyu")
    assert body == {"file_id": 4242, "voice_id": final["payload"]["voice_id"]}
    voices = {json.loads(c.request.content)["voice_setting"]["voice_id"] for c in t2a.calls}
    assert voices == {body["voice_id"]}
    calls = [c for c in _rows(client, ModelCall) if c.job_id == job["id"]]
    assert len(calls) == 6 and all(c.status == "success" for c in calls)
    expected = CLONE + 5 * billed * PER_CHAR
    assert final["cost_usd"] == pytest.approx(expected)
    assert job["est_cost_usd"] == pytest.approx(expected)
