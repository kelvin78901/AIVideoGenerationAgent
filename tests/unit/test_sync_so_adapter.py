"""sync.so lipsync-2-pro (口型修复, M6 step 7a) against respx fakes: never the network."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from drama_series_agent.core.config import get_config
from drama_series_agent.core.storage import BlobStore
from drama_series_agent.modelhub.adapters.base import CallContext, ModelError, ModelRequest
from drama_series_agent.modelhub.adapters.mock import sine_wav, solid_mp4
from drama_series_agent.modelhub.adapters.sync_so import SyncSoAdapter, billed_seconds
from drama_series_agent.modelhub.pricing import cost_usd
from drama_series_agent.modelhub.registry import specs_from_config

API = "https://api.sync.so"
S3 = "https://bucket.example.com"
CDN = "https://cdn.example.com/lip.mp4"
KEYS = {"SYNC_API_KEY": "sync-SECRET"}


def _spec() -> Any:
    return next(s for s in specs_from_config(get_config()) if s.key == "sync/lipsync-2-pro")


@pytest.fixture
def store(tmp_path: Path) -> BlobStore:
    return BlobStore(tmp_path / "blobs")


def _adapter(store: BlobStore) -> SyncSoAdapter:
    return SyncSoAdapter(_spec(), get_key=KEYS.get, store=store, backoff_s=0, poll_s=0)


async def _req(store: BlobStore, seconds: float = 5.0) -> ModelRequest:
    video = store.put_bytes(await solid_mp4(64, 112, seconds, 24, "336699", audio_hz=300))
    audio = store.put_bytes(sine_wav(seconds))
    params = {"video_in": video, "audio_in": audio, "duration_s": seconds, "fps": 24}
    return ModelRequest(kind="lipsync", prompt="", params=params)


def _uploads() -> tuple[respx.Route, respx.Route, respx.Route]:
    slots = respx.post(f"{API}/v2/assets/upload").mock(
        side_effect=[
            httpx.Response(201, json={"uploadUrl": f"{S3}/v?sig=1", "url": f"{S3}/v.mp4"}),
            httpx.Response(201, json={"uploadUrl": f"{S3}/a?sig=1", "url": f"{S3}/a.wav"}),
        ]
    )
    put = respx.put(url__startswith=S3).mock(return_value=httpx.Response(200))
    assets = respx.post(f"{API}/v2/assets").mock(
        side_effect=[
            httpx.Response(201, json={"id": "as-v"}),
            httpx.Response(201, json={"id": "as-a"}),
        ]
    )
    return slots, put, assets


def _job(status: str, **extra: Any) -> dict[str, Any]:
    return {"id": "gen-1", "model": "lipsync-2-pro", "status": status, **extra}


@respx.mock
async def test_uploads_the_take_and_the_dub_then_polls_and_bills_frames(store: BlobStore) -> None:
    slots, put, assets = _uploads()
    create = respx.post(f"{API}/v2/generate").mock(
        return_value=httpx.Response(201, json=_job("PENDING"))
    )
    respx.get(f"{API}/v2/generate/gen-1").mock(
        side_effect=[
            httpx.Response(200, json=_job("PENDING")),
            httpx.Response(200, json=_job("PROCESSING")),
            httpx.Response(200, json=_job("COMPLETED", outputUrl=CDN, outputDuration=5.0)),
        ]
    )
    made = await solid_mp4(64, 112, 5.0, 24, "993366", audio_hz=300)
    download = respx.get(CDN).mock(return_value=httpx.Response(200, content=made))
    seen: list[dict[str, Any]] = []

    async def progress(p: dict[str, Any]) -> None:
        seen.append(p)

    adapter = _adapter(store)
    req = await _req(store)
    result = await adapter.run(req, CallContext(on_progress=progress))

    # Each file: a presigned slot, the bytes PUT there without the key, then registered.
    asked = [json.loads(c.request.content) for c in slots.calls]
    assert [(a["fileName"], a["contentType"]) for a in asked] == [
        ("video.mp4", "video/mp4"),
        ("audio.wav", "audio/wav"),
    ]
    assert slots.calls[0].request.headers["x-api-key"] == "sync-SECRET"
    assert all("x-api-key" not in c.request.headers for c in put.calls)
    assert put.calls[0].request.content == store.path_for(req.params["video_in"]).read_bytes()
    registered = [json.loads(c.request.content) for c in assets.calls]
    assert [(r["url"], r["type"]) for r in registered] == [
        (f"{S3}/v.mp4", "VIDEO"),
        (f"{S3}/a.wav", "AUDIO"),
    ]
    assert json.loads(create.calls[0].request.content) == {
        "model": "lipsync-2-pro",
        "input": [{"type": "video", "assetId": "as-v"}, {"type": "audio", "assetId": "as-a"}],
        "options": {"sync_mode": "cut_off"},
    }
    assert [p["status"] for p in seen] == ["PENDING", "PROCESSING"]
    assert "x-api-key" not in download.calls[0].request.headers
    (video,) = result.files
    assert (video.mime, video.w, video.h) == ("video/mp4", 64, 112)
    # 120 frames at $0.00333 (the per-second price is quoted at 25 fps).
    assert result.usage.output_seconds == billed_seconds(5.0, 24) == 4.8
    cost = cost_usd(adapter.spec.pricing, result.usage)
    assert cost == pytest.approx(120 * 0.00333)
    assert adapter.estimate(req).cost_usd == pytest.approx(cost)


@respx.mock
@pytest.mark.parametrize(
    ("status", "code"),
    [("NO_OP", "lipsync_no_face"), ("FAILED", "provider_error"), ("REJECTED", "bad_request")],
)
async def test_what_did_not_work(store: BlobStore, status: str, code: str) -> None:
    _uploads()
    respx.post(f"{API}/v2/generate").mock(return_value=httpx.Response(201, json=_job("PENDING")))
    respx.get(f"{API}/v2/generate/gen-1").mock(
        return_value=httpx.Response(200, json=_job(status, error="no face", errorCode="x"))
    )
    with pytest.raises(ModelError) as caught:
        await _adapter(store).run(await _req(store), CallContext())
    assert caught.value.code == code and "no face" in str(caught.value)


@respx.mock
async def test_errors_on_the_way_in(store: BlobStore) -> None:
    respx.post(f"{API}/v2/assets/upload").mock(return_value=httpx.Response(401, text="nope"))
    with pytest.raises(ModelError) as caught:
        await _adapter(store).run(await _req(store), CallContext())
    assert caught.value.code == "auth_failed"
    with pytest.raises(ModelError) as caught:
        await SyncSoAdapter(_spec(), get_key={}.get, store=store).run(
            await _req(store), CallContext()
        )
    assert caught.value.code == "missing_key"


@respx.mock
async def test_health_lists_one_generation() -> None:
    route = respx.get(f"{API}/v2/generations").mock(return_value=httpx.Response(200, json=[]))
    health = await _adapter(BlobStore(Path("unused"))).health()
    assert health.ok and health.models == ["lipsync-2-pro"]
    assert route.calls[0].request.url.params["limit"] == "1"
    assert route.calls[0].request.headers["x-api-key"] == "sync-SECRET"
