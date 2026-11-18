"""2K 精修 of a take (M6 step 6, component ``up``), in Mock mode.

``POST /versions/{id}/upscale`` on a take queues ``up`` on the shot's video product: one version
at the delivery size (origin ``upscale``, parent = the take, ``stage = final``), the take's
sound kept as it is, QA'd like every take. Once checked it is adopted when the take was the
adopted one, nothing failed and the product is not locked; otherwise a candidate. The video
product's estimate prices it for the button (``estimate.finishing.up``).
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_qa_api import (
    V1,
    _checks,
    _confirm_storyboard,
    _qa_settled,
    _rows,
    _set_mock_qa,
    _shots,
    _state,
    _take,
    _wait,
    client,
)

from drama_series_agent.core.models_db import Dependency, ModelCall
from drama_series_agent.media.audio import ffmpeg_exe
from drama_series_agent.media.video import probe
from drama_series_agent.pipeline.components import up

__all__ = ["client"]


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    seen: list[Any] = []
    real = up.UpComponent.media_call

    async def spy(self: Any, ctx: Any, req: Any, *args: Any, **kwargs: Any) -> Any:
        seen.append(req)
        return await real(self, ctx, req, *args, **kwargs)

    monkeypatch.setattr(up.UpComponent, "media_call", spy)
    return seen


def _product(client: TestClient, label: str) -> dict[str, Any]:
    pid = _shots(client)[label]["video_product_id"]
    product: dict[str, Any] = client.get(f"{V1}/products/{pid}").json()
    return product


def _upscale(client: TestClient, version_id: str) -> Any:
    return client.post(f"{V1}/versions/{version_id}/upscale", json={})


def _finished(client: TestClient, version_id: str, label: str) -> dict[str, Any]:
    resp = _upscale(client, version_id)
    assert resp.status_code == 200, resp.text
    job = resp.json()
    assert job["component_id"] == "up"
    _wait(client, job["id"])
    _qa_settled(client)
    return _product(client, label)


def _bytes(client: TestClient, f: dict[str, Any]) -> bytes:
    return _state(client).store.path_for(f["sha256"]).read_bytes()


def _sound(data: bytes) -> bytes:
    """The clip's sound stream as stored (copied out, not decoded)."""
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "in.mp4"
        src.write_bytes(data)
        cmd = [ffmpeg_exe(), "-v", "error", "-i", str(src), "-map", "0:a:0", "-c", "copy"]
        out = subprocess.run([*cmd, "-f", "data", "-"], check=True, capture_output=True).stdout
        assert out
        return out


def _video(v: dict[str, Any]) -> dict[str, Any]:
    return next(f for f in v["files"] if f["role"] == "video")


def _deps(client: TestClient, version_id: str) -> list[tuple[str, str, str]]:
    rows = _rows(client, Dependency, Dependency.version_id == version_id)
    return sorted((d.upstream_product_id, d.upstream_hash, d.slice) for d in rows)


def test_an_adopted_take_finished_at_2k_is_adopted_after_qa(
    client: TestClient, sent: list[Any]
) -> None:
    _confirm_storyboard(client)
    take = _take(client, "1-04")
    client.post(f"{V1}/versions/{take['id']}/adopt").raise_for_status()
    before = _product(client, "1-04")

    # The button's price and time: SeedVR2 locally, free but for QA's look at it (the time is
    # the adapter's: the real one says 40 s a second of the shot, a Mock its own delay).
    finishing = before["estimate"]["finishing"]["up"]
    assert (finishing["model_key"], finishing["where"]) == ("comfy/seedvr2", "local")
    assert finishing["cost_usd"] < 0.01 and finishing["seconds"] is not None

    product = _finished(client, take["id"], "1-04")
    v = product["versions"][-1]
    assert (v["origin"], v["parent_version_id"], v["stage"]) == ("upscale", take["id"], "final")
    assert v["model_key"] == "comfy/seedvr2"
    assert v["params"]["finish"] == {"kind": "upscale", "version_id": take["id"]}
    assert product["prompt"] == before["prompt"]
    assert _deps(client, v["id"]) == _deps(client, take["id"])

    # At the delivery size and frame rate, from the take as stored; its sound as it was.
    (req,) = sent
    assert (req.kind, req.params["video_in"]) == ("upscale", _video(take)["sha256"])
    assert (req.params["width"], req.params["height"], req.params["fps"]) == (1080, 1920, 24)
    clip = _video(v)
    assert (clip["w"], clip["h"]) == (1080, 1920)
    info = client.portal.call(probe, _bytes(client, clip))  # type: ignore[union-attr]
    assert info.has_audio and info.fps == 24
    assert _sound(_bytes(client, clip)) == _sound(_bytes(client, _video(take)))
    assert v["payload"]["resolution"] == "1080p"
    assert any(f["role"] == "sheet" for f in v["files"])

    # Checked like a take, the scores on the call that made it; then adopted.
    assert v["qa"] is not None and v["qa_pass"] is True
    (call,) = _rows(client, ModelCall, ModelCall.id == v["params"]["call_id"])
    assert call.component_id == "up" and call.qa_pass is True
    assert product["adopted_version_id"] == v["id"]


def _faces_off(client: TestClient) -> None:
    """From now on the Mock face tool sees someone else in every clip."""

    def face(req: Any) -> dict[str, Any]:
        refs = req.params.get("refs") or []
        return {"faces": [{"asset_id": r.get("asset_id"), "sim": 0.05} for r in refs]}

    _state(client).registry.add_mock_responder("qa", "face", face)


def test_a_finished_take_stays_a_candidate(client: TestClient) -> None:
    _confirm_storyboard(client)
    take = _take(client, "1-04")

    # Nothing adopted: the take finished is one more to pick from.
    product = _finished(client, take["id"], "1-04")
    first = product["versions"][-1]
    assert first["qa_pass"] is True and product["adopted_version_id"] is None

    # Locked (the takes gate confirmed): made and passing, never adopted.
    client.post(f"{V1}/versions/{take['id']}/adopt").raise_for_status()
    client.post(f"{V1}/products/{product['id']}/lock").raise_for_status()
    product = _finished(client, take["id"], "1-04")
    assert product["versions"][-1]["qa_pass"] is True
    assert product["adopted_version_id"] == take["id"]
    client.post(f"{V1}/products/{product['id']}/unlock").raise_for_status()

    # Worse than the take (its face no longer passes): the adopted take stays.
    _faces_off(client)
    product = _finished(client, take["id"], "1-04")
    v = product["versions"][-1]
    assert (_checks(v)["face"]["ok"], v["qa_pass"]) == (False, False)
    assert product["adopted_version_id"] == take["id"]


def test_a_take_kept_failing_is_finished_and_adopted(client: TestClient) -> None:
    """Kelvin 2026-11-17 (不比原片差就采纳): a check the adopted take failed already, and was
    kept anyway, does not hold its 2K back."""
    _confirm_storyboard(client)
    take = _take(client, "1-04")
    client.post(f"{V1}/versions/{take['id']}/adopt").raise_for_status()
    _set_mock_qa(client, take["id"], {"face": 0.05})
    resp = client.post(f"{V1}/versions/{take['id']}/qa")
    _wait(client, resp.json()["id"])
    _faces_off(client)
    product = _finished(client, take["id"], "1-04")
    v = product["versions"][-1]
    assert (_checks(v)["face"]["ok"], v["qa_pass"]) == (False, False)
    assert product["adopted_version_id"] == v["id"]


def test_a_re_qa_does_not_adopt(client: TestClient) -> None:
    _confirm_storyboard(client)
    take = _take(client, "1-04")
    product = _finished(client, take["id"], "1-04")
    v = product["versions"][-1]
    client.post(f"{V1}/versions/{take['id']}/adopt").raise_for_status()
    _set_mock_qa(client, v["id"], {})
    resp = client.post(f"{V1}/versions/{v['id']}/qa")
    _wait(client, resp.json()["id"])
    # Checked again after the user adopted the take: only the first check adopts.
    assert _product(client, "1-04")["adopted_version_id"] == take["id"]


def test_what_is_refused(client: TestClient) -> None:
    _confirm_storyboard(client)
    pid = _shots(client)["1-04"]["video_product_id"]
    # An API take is made at the delivery size already.
    resp = client.post(f"{V1}/products/{pid}/run", json={"mode": "run", "count": 1, "where": "api"})
    assert resp.status_code == 200, resp.text
    _wait(client, resp.json()["id"])
    _qa_settled(client)
    api_take = _product(client, "1-04")["versions"][-1]
    assert api_take["where"] == "api"
    resp = _upscale(client, api_take["id"])
    assert (resp.status_code, resp.json()["detail"]["code"]) == (409, "upscale_not_needed")

    # The API route (Regenerate-2K) takes only a local H3 draft.
    body = {"scope": "component", "scope_id": None, "component_id": "up"}
    data = {"mode": "api", "api_model": "minimax/h3-regenerate-2k"}
    client.put(f"{V1}/config/override", json={**body, "data": data}).raise_for_status()
    local = _take(client, "1-04")
    assert local["where"] == "local" and any(f["role"] == "raw" for f in local["files"])
    product = _finished(client, local["id"], "1-04")
    v = product["versions"][-1]
    assert (v["model_key"], v["origin"], v["stage"]) == (
        "minimax/h3-regenerate-2k",
        "upscale",
        "final",
    )
    assert v["params"]["finish"]["version_id"] == local["id"] and v["cost_usd"] > 0
