"""口型修复 of a take (M6 step 7a, component ``lip``), in Mock mode.

``POST /versions/{id}/lipsync`` on a take queues ``lip`` on the shot's video product: one version
(origin ``lipsync``, parent = the take) whose mouths follow the shot's dubbed lines, the dub as
its sound, QA'd like every take and adopted as 2K 精修 is. A batch whose only failure is lip
sync is repaired by QA's policy (``params.auto: auto_lip``); a repair that fails too goes on to
the reruns. 1-04 is a 原生同步 dialogue shot; 1-03 an insert nobody speaks in.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_qa_api import (
    EP1,
    V1,
    _confirm_storyboard,
    _requa,
    _rows,
    _set_mock_qa,
    _settled,
    _shots,
    _state,
    _take,
    _wait,
    client,
)
from test_take_upscale_api import _bytes, _deps, _product, _video
from test_takes_api import _dub_shot

from drama_series_agent.core.models_db import ModelCall
from drama_series_agent.media.audio import dialogue_track
from drama_series_agent.media.video import probe
from drama_series_agent.modelhub.adapters.base import ModelRequest
from drama_series_agent.pipeline.components import lip

__all__ = ["client"]


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    seen: list[Any] = []
    real = lip.LipComponent.media_call

    async def spy(self: Any, ctx: Any, req: Any, *args: Any, **kwargs: Any) -> Any:
        seen.append(req)
        return await real(self, ctx, req, *args, **kwargs)

    monkeypatch.setattr(lip.LipComponent, "media_call", spy)
    return seen


def _lipsync(client: TestClient, version_id: str) -> Any:
    return client.post(f"{V1}/versions/{version_id}/lipsync")


def _dubbed(client: TestClient, label: str) -> None:
    _dub_shot(client, _shots(client)[label])


def _lips_off(client: TestClient) -> None:
    """From now on the Mock lip-sync tool finds every clip out of sync."""

    def sync(req: ModelRequest) -> dict[str, Any]:
        return {"in_sync": 0.2, "conf": 0.2, "offset": 9}

    _state(client).registry.add_mock_responder("qa", "lipsync", sync)


def test_an_adopted_take_repaired_is_adopted_after_qa(client: TestClient, sent: list[Any]) -> None:
    _confirm_storyboard(client)
    _dubbed(client, "1-04")
    take = _take(client, "1-04")
    client.post(f"{V1}/versions/{take['id']}/adopt").raise_for_status()
    before = _product(client, "1-04")

    # The button's price and time: LatentSync locally (Mock, nothing scanned), free but QA.
    finishing = before["estimate"]["finishing"]["lip"]
    assert (finishing["model_key"], finishing["where"]) == ("local/latentsync", "local")
    assert finishing["cost_usd"] < 0.01 and finishing["seconds"] is not None

    resp = _lipsync(client, take["id"])
    assert resp.status_code == 200, resp.text
    assert resp.json()["component_id"] == "lip"
    _wait(client, resp.json()["id"])
    _settled(client)
    product = _product(client, "1-04")
    v = product["versions"][-1]
    assert (v["origin"], v["parent_version_id"], v["stage"]) == ("lipsync", take["id"], "draft")
    assert v["params"]["finish"] == {"kind": "lipsync", "version_id": take["id"]}
    assert "auto" not in v["params"] and product["prompt"] == before["prompt"]

    # The take as stored, and the shot's dub from where its lines start in it (the take lost
    # its first 0.3 s, the request had them at 0.3 s: at 0).
    (req,) = sent
    assert (req.kind, req.params["video_in"]) == ("lipsync", _video(take)["sha256"])
    assert v["payload"]["lip"] == {"lines": 1, "lead_s": 0.0}
    assert req.params["fps"] == 24 and req.params["duration_s"] == _video(take)["duration_s"]
    track = _state(client).store.path_for(req.params["audio_in"]).read_bytes()
    dubs = [
        _state(client).store.path_for(f["sha256"]).read_bytes()
        for f in _line_audio_files(client, "1-04")
    ]
    assert track == dialogue_track(dubs, req.params["duration_s"], 0.0)
    clip = _video(v)
    info = client.portal.call(probe, _bytes(client, clip))  # type: ignore[union-attr]
    assert info.has_audio and abs(info.duration_s - _video(take)["duration_s"]) < 0.1
    # The take's dependencies and the dubs'.
    deps = _deps(client, v["id"])
    assert set(_deps(client, take["id"])) <= set(deps) and len(deps) > len(
        _deps(client, take["id"])
    )

    # Checked like a take, scores on its call; then adopted.
    assert v["qa_pass"] is True
    (call,) = _rows(client, ModelCall, ModelCall.id == v["params"]["call_id"])
    assert call.component_id == "lip" and call.qa_pass is True
    assert product["adopted_version_id"] == v["id"]


def _line_audio_files(client: TestClient, label: str) -> list[dict[str, Any]]:
    """The adopted dub of each on-screen line of the shot, in speaking order."""
    dub = client.get(f"{V1}/episodes/{EP1}/dub").json()["lines"]
    ids = _shots(client)[label]["line_ids"]
    out: list[dict[str, Any]] = []
    for line in sorted(
        (x for x in dub if x["line_id"] in ids), key=lambda x: ids.index(x["line_id"])
    ):
        product = client.get(f"{V1}/products/{line['product_id']}").json()
        v = next(v for v in product["versions"] if v["id"] == product["adopted_version_id"])
        out.append(next(f for f in v["files"] if f["role"] == "audio"))
    return out


def test_what_is_refused(client: TestClient) -> None:
    _confirm_storyboard(client)
    # Nobody speaks in the insert.
    insert = _take(client, "1-03")
    resp = _lipsync(client, insert["id"])
    assert (resp.status_code, resp.json()["detail"]["code"]) == (409, "lipsync_no_dialogue")
    # A line not dubbed yet.
    take = _take(client, "1-04")
    resp = _lipsync(client, take["id"])
    detail = resp.json()["detail"]
    assert (resp.status_code, detail["code"], detail["params"]["count"]) == (
        409,
        "line_audio_missing",
        1,
    )
    assert _lipsync(client, "nope").status_code == 404


def test_only_lip_sync_failing_is_repaired_by_qa(client: TestClient) -> None:
    _confirm_storyboard(client)
    _dubbed(client, "1-04")
    take = _take(client, "1-04")
    _set_mock_qa(client, take["id"], {"lipsync": 0.2})
    _requa(client, take["id"])
    _settled(client)

    product = _product(client, "1-04")
    first, repair = product["versions"]
    assert (first["qa_pass"], first["qa"]["policy"]["action"]) == (False, "lip")
    assert (repair["origin"], repair["params"]["auto"]) == ("lipsync", "auto_lip")
    assert repair["params"]["finish"]["version_id"] == take["id"]
    # It passed: nothing more, and nothing adopted (the person picks).
    assert repair["qa_pass"] is True and product["adopted_version_id"] is None
    codes = [e["message"]["code"] for e in client.get(f"{V1}/episodes/{EP1}/generate-log").json()]
    assert codes[0] == "take_fail_lip"


def test_a_repair_that_fails_goes_on_to_the_reruns(client: TestClient) -> None:
    _confirm_storyboard(client)
    client.put(f"{V1}/series/demo/generate-rules", json={"qa_retry_max": 1}).raise_for_status()
    _dubbed(client, "1-04")
    _lips_off(client)
    pid = _shots(client)["1-04"]["video_product_id"]
    client.post(f"{V1}/products/{pid}/run", json={"mode": "run", "count": 1}).raise_for_status()
    _settled(client)

    versions = client.get(f"{V1}/products/{pid}").json()["versions"]
    # Each batch is repaired once; the repair failing too, a rerun, then the fallback, then stop.
    assert [(v["origin"], v["qa_pass"]) for v in versions] == [
        ("run", False),
        ("lipsync", False),
        ("auto_qa_rerun", False),
        ("lipsync", False),
        ("fallback", False),
        ("lipsync", False),
    ]
    take, repair = versions[0], versions[1]
    assert repair["params"]["finish"]["version_id"] == take["id"]
    # The rerun answers the take (told to fix the lips); the decision is noted on the repair.
    assert versions[2]["params"]["fixes"] == ["- 说台词时嘴型要对上声音"]
    assert take["qa"]["policy"]["action"] == "lip"
    assert repair["qa"]["policy"]["action"] == "rerun"


def test_a_shot_not_dubbed_gets_a_rerun_instead(client: TestClient) -> None:
    _confirm_storyboard(client)
    client.put(f"{V1}/series/demo/generate-rules", json={"qa_retry_max": 1}).raise_for_status()
    take = _take(client, "1-04")
    _set_mock_qa(client, take["id"], {"lipsync": 0.2})
    _requa(client, take["id"])
    _settled(client)
    versions = _product(client, "1-04")["versions"]
    assert [v["origin"] for v in versions] == ["run", "auto_qa_rerun"]
    assert versions[0]["qa"]["policy"]["action"] == "rerun"


def test_the_api_route_is_offered_and_taken(client: TestClient, sent: list[Any]) -> None:
    """The menu offers both of the route's models: LatentSync here, sync.so on the API."""
    _confirm_storyboard(client)
    _dubbed(client, "1-04")
    take = _take(client, "1-04")
    alt = _product(client, "1-04")["estimate"]["finishing"]["lip"]["alt"]
    assert (alt["model_key"], alt["where"], alt["alt"]) == ("sync/lipsync-2-pro", "api", None)
    assert alt["cost_usd"] > 0

    resp = client.post(f"{V1}/versions/{take['id']}/lipsync", json={"where": "api"})
    assert resp.status_code == 200, resp.text
    _wait(client, resp.json()["id"])
    v = _product(client, "1-04")["versions"][-1]
    assert (v["origin"], v["model_key"]) == ("lipsync", "sync/lipsync-2-pro")
    assert (
        client.post(f"{V1}/versions/{take['id']}/lipsync", json={"where": "moon"}).status_code
        == 422
    )
