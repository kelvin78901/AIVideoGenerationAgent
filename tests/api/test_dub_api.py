"""台词配音 (SPEC 5 ``dub``; M3 step 7), in Mock mode: the episode's spoken lines in their
locked voices, 「全部配音」, the emotion by tone or by hand, and lengths from the audio.

In the demo, 林晚's voice is a locked MiniMax final; 周屿's is not made yet.
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
from drama_series_agent.core.models_db import ModelCall, Product
from drama_series_agent.pipeline.timing import shot_seconds

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


def _rows(client: TestClient, model: Any) -> list[Any]:
    async def read() -> list[Any]:
        async with _state(client).db.session() as s:
            return list((await s.exec(select(model))).all())

    return list(client.portal.call(read))  # type: ignore[union-attr]


def _dub(client: TestClient) -> dict[str, Any]:
    out: dict[str, Any] = client.get(f"{V1}/episodes/{EP1}/dub").json()
    return out


def _wait_all(client: TestClient, job_ids: list[str]) -> None:
    deadline = time.monotonic() + 30
    for job_id in job_ids:
        while True:
            job = client.get(f"{V1}/jobs/{job_id}").json()
            if job["state"] in ("succeeded", "failed", "canceled"):
                assert job["state"] == "succeeded", job
                break
            assert time.monotonic() < deadline, "jobs did not finish"
            time.sleep(0.02)


def _dub_all(client: TestClient) -> dict[str, Any]:
    started: dict[str, Any] = client.post(f"{V1}/episodes/{EP1}/dub", json={}).json()
    _wait_all(client, started["jobs"])
    return started


def test_the_episodes_lines_before_dubbing(client: TestClient) -> None:
    dub = _dub(client)
    lines = dub["lines"]
    assert lines and dub["done"] == 0 and dub["total"] == len(lines)
    first = lines[0]
    assert (first["text"], first["voice_asset_id"], first["status"]) == (
        "……周屿？", "vlinwan", "missing"
    )  # fmt: skip
    # 「低声，愣住」 → whisper; 「OS」 → calm.
    by_text = {x["text"]: x for x in lines}
    assert by_text["……周屿？"]["emotion"] == "whisper"
    assert by_text["三年了。他凭什么。"]["emotion"] == "calm"
    assert all(x["audio"] is None and x["seconds"] > 0 for x in lines)
    assert [s["number"] for s in dub["scenes"]] == [1, 2]


def test_dub_the_whole_episode(client: TestClient) -> None:
    estimate = client.post(f"{V1}/episodes/{EP1}/dub", json={"dry_run": True}).json()
    todo = [x for x in _dub(client)["lines"] if x["status"] == "missing"]
    assert estimate["jobs"] == [] and estimate["lines"] == len(todo) > 0
    chars = sum(len(x["text"]) for x in todo)
    assert estimate["estimate_usd"] == pytest.approx(chars * 100 / 1e6)

    started = _dub_all(client)
    assert len(started["jobs"]) == len(todo)
    dub = _dub(client)
    done = [x for x in dub["lines"] if x["status"] == "done"]
    assert len(done) == len(todo) == dub["done"]
    for x in done:
        assert x["audio"]["role"] == "audio" and len(x["audio"]["waveform"]) == 64
        assert x["seconds"] == pytest.approx(x["audio"]["duration_s"])
    # A scene is as long as its lines' audio.
    for s in dub["scenes"]:
        mine = [x["seconds"] for x in dub["lines"] if x["scene_id"] == s["scene_id"]]
        assert s["seconds"] == pytest.approx(sum(mine))
    calls = [c for c in _rows(client, ModelCall) if c.component_id == "dub"]
    assert len(calls) == len(todo) and all(c.episode_id == EP1 for c in calls)
    # The whispered line goes to 2.6 HD (2.8 has no whisper), the rest to the voice's model.
    whisper = next(x for x in done if x["emotion"] == "whisper")
    product = next(p for p in _rows(client, Product) if p.id == whisper["product_id"])
    call = next(c for c in calls if c.product_id == product.id)
    assert call.model_key == "minimax/speech-2.6-hd"
    assert {c.model_key for c in calls} <= {"minimax/speech-2.6-hd", "minimax/speech-2.8-hd"}
    # Nothing left to dub.
    again = client.post(f"{V1}/episodes/{EP1}/dub", json={"dry_run": True}).json()
    assert again["lines"] == 0


def test_rewording_a_line_makes_only_its_audio_stale(client: TestClient) -> None:
    _dub_all(client)
    target = next(x for x in _dub(client)["lines"] if x["text"] == "……周屿？")
    preview = client.post(
        f"{V1}/impact/preview",
        json={
            "kind": "line_edit",
            "target_id": target["line_id"],
            "patch": {"text": "……是周屿吗？"},
        },
    ).json()
    client.post(f"{V1}/impact/apply", json={"impact_id": preview["id"], "action": "mark"})
    lines = _dub(client)["lines"]
    stale = [x["line_id"] for x in lines if x["status"] == "stale"]
    assert stale == [target["line_id"]]
    # 「全部配音」 dubs just that one again.
    started = _dub_all(client)
    assert len(started["jobs"]) == 1
    redone = next(x for x in _dub(client)["lines"] if x["line_id"] == target["line_id"])
    assert redone["status"] == "done" and redone["text"] == "……是周屿吗？"


def test_a_lines_emotion_by_hand(client: TestClient) -> None:
    line = _dub(client)["lines"][0]
    resp = client.patch(f"{V1}/lines/{line['line_id']}/dub", json={"emotion": "crying"})
    assert resp.status_code == 200, resp.text
    assert (resp.json()["emotion"], resp.json()["emotion_set"]) == ("crying", True)
    _dub_all(client)
    product = next(p for p in _rows(client, Product) if p.owner_id == line["line_id"])
    version = client.get(f"{V1}/products/{product.id}").json()["versions"][-1]
    assert version["payload"]["emotion"] == "crying"
    resp = client.patch(f"{V1}/lines/{line['line_id']}/dub", json={"emotion": None})
    assert (resp.json()["emotion"], resp.json()["emotion_set"]) == ("whisper", False)
    bad = client.patch(f"{V1}/lines/{line['line_id']}/dub", json={"emotion": "giggle"})
    assert bad.status_code == 422 and bad.json()["detail"]["code"] == "unknown_emotion"


def test_a_voice_must_be_locked_first(client: TestClient) -> None:
    """Unlock 林晚's voice: her lines wait for it, and 「全部配音」 says why."""
    preview = client.post(
        f"{V1}/impact/preview", json={"kind": "asset_unlock", "target_id": "vlinwan", "patch": {}}
    ).json()
    client.post(f"{V1}/impact/apply", json={"impact_id": preview["id"], "action": "mark"})
    lines = _dub(client)["lines"]
    mine = [x for x in lines if x["voice_asset_id"] == "vlinwan"]
    assert mine and all(x["status"] == "voice_not_locked" for x in mine)
    started = client.post(f"{V1}/episodes/{EP1}/dub", json={}).json()
    assert {s["line_id"] for s in started["skipped"]} >= {x["line_id"] for x in mine}
    assert {s["name"] for s in started["skipped"] if s["code"] == "voice_not_locked"} == {"林晚"}


def test_shot_seconds() -> None:
    timing = shot_seconds([1.2, 2.0], longest_s=3.0)
    assert timing.seconds == pytest.approx(0.3 + 3.2 + 0.2) and timing.split
    assert not shot_seconds([1.0]).split
