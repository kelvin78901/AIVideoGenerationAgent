"""MiniMax H3 (generation, Context-IR, Regenerate-2K) and Seedance 2.5 against respx fakes:
never the network (M5 step 6)."""

from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from drama_series_agent.core.config import get_config
from drama_series_agent.core.storage import BlobStore
from drama_series_agent.modelhub.adapters.base import CallContext, ModelError, ModelRequest
from drama_series_agent.modelhub.adapters.minimax_video import (
    MiniMaxVideoAdapter,
    host_of,
    seconds_for,
)
from drama_series_agent.modelhub.adapters.mock import mock_picture, sine_wav, solid_mp4
from drama_series_agent.modelhub.adapters.seedance import SeedanceAdapter, resolution_for
from drama_series_agent.modelhub.pricing import cost_usd
from drama_series_agent.modelhub.registry import specs_from_config

MM = "https://api.minimax.cn"
ARK = "https://ark.cn-beijing.volces.com/api/v3"
CDN = "https://cdn.example.com/out.mp4"
CNY = 7.1
KEYS = {"MINIMAX_API_KEY": "mm-SECRET", "ARK_API_KEY": "ark-SECRET"}
_CLIPS: dict[float, bytes] = {}


async def _clip(seconds: float) -> bytes:
    if seconds not in _CLIPS:
        _CLIPS[seconds] = await solid_mp4(64, 112, seconds, 24, "336699", audio_hz=300)
    return _CLIPS[seconds]


def _spec(key: str) -> Any:
    return next(s for s in specs_from_config(get_config()) if s.key == key)


@pytest.fixture
def store(tmp_path: Path) -> BlobStore:
    return BlobStore(tmp_path / "blobs")


def _mm(store: BlobStore, key: str = "minimax/h3-api") -> MiniMaxVideoAdapter:
    return MiniMaxVideoAdapter(_spec(key), get_key=KEYS.get, store=store, backoff_s=0, poll_s=0)


def _ark(store: BlobStore) -> SeedanceAdapter:
    return SeedanceAdapter(
        _spec("volc/seedance-2.5"), get_key=KEYS.get, store=store, backoff_s=0, poll_s=0
    )


def _picture(store: BlobStore, i: int = 0) -> str:
    return store.put_bytes(mock_picture(108, 192, "ref", i))


def _video_req(store: BlobStore, **params: Any) -> ModelRequest:
    base = {
        "n": 1,
        "width": 1080,
        "height": 1920,
        "aspect": "9:16",
        "duration_s": 6.4,
        "fps": 24,
        "first_frame": _picture(store),
        "with_audio": True,
    }
    return ModelRequest(kind="video", prompt="雨夜，林晚推门。", params={**base, **params})


def _task(status: str, **extra: Any) -> dict[str, Any]:
    return {"task": {"id": "t-1", "model": "MiniMax-H3", "status": status, **extra}}


def _done(**usage: Any) -> dict[str, Any]:
    return _task(
        "succeeded",
        content={"url": CDN},
        resolution="2K",
        duration=7,
        usage={"output_seconds": 7, "input_seconds": 0, "input_image_count": 1, **usage},
    )


def _sent(route: respx.Route) -> dict[str, Any]:
    body: dict[str, Any] = json.loads(route.calls[0].request.content)
    return body


def test_helpers() -> None:
    assert host_of("https://api.minimax.cn/v1") == MM
    assert host_of("https://api.minimax.io/v1/") == "https://api.minimax.io"
    assert seconds_for(6.4, (4, 15)) == 7 and seconds_for(5.02, (4, 15)) == 5
    assert seconds_for(2.0, (4, 15)) == 4 and seconds_for(40, (4, 30)) == 30
    offered = ["480p", "720p", "1080p"]
    assert resolution_for(1080, 1920, offered) == "1080p"
    assert resolution_for(768, 1344, offered) == "720p"
    assert resolution_for(1440, 2560, ["480p", "720p"]) == "720p"


# ---------------------------------------------------------------------- H3 generation


@respx.mock
async def test_h3_image_to_video_polls_downloads_and_bills_2k(store: BlobStore) -> None:
    create = respx.post(f"{MM}/v2/video_generation").mock(
        return_value=httpx.Response(200, json={"task_id": "t-1"})
    )
    respx.get(f"{MM}/v2/query/video_generation/t-1").mock(
        side_effect=[
            httpx.Response(200, json=_task("queued")),
            httpx.Response(200, json=_task("running")),
            httpx.Response(200, json=_task("running")),
            httpx.Response(200, json=_done()),
        ]
    )
    download = respx.get(CDN).mock(return_value=httpx.Response(200, content=await _clip(7)))
    seen: list[dict[str, Any]] = []

    async def progress(p: dict[str, Any]) -> None:
        seen.append(p)

    adapter = _mm(store)
    req = _video_req(store, refs=[_picture(store, 1)])
    result = await adapter.run(req, CallContext(on_progress=progress))

    sent = _sent(create)
    assert create.calls[0].request.headers["authorization"] == "Bearer mm-SECRET"
    assert {k: v for k, v in sent.items() if k != "content"} == {
        "model": "MiniMax-H3",
        "duration": 7,
        "ratio": "9:16",
        "resolution": "2K",
    }
    text, first = sent["content"]
    assert text == {"type": "text", "text": "雨夜，林晚推门。"}
    # Image to video: the first frame is a hard anchor; the locked picture is left out.
    assert first["role"] == "first_frame"
    assert first["image_url"]["url"].startswith("data:image/png;base64,")
    assert "authorization" not in download.calls[0].request.headers
    assert [p["status"] for p in seen] == ["queued", "running"]
    (video,) = result.files
    assert (video.mime, video.w, video.h) == ("video/mp4", 64, 112)
    assert result.usage.output_seconds == 7 and result.usage.resolution == "2k"
    cost = cost_usd(adapter.spec.pricing, result.usage, resolution=result.usage.resolution)
    assert cost == pytest.approx(7 * 0.80 / CNY)
    # The estimate prices the same call (2K, 7 s) up front.
    assert adapter.estimate(req).cost_usd == pytest.approx(cost)
    assert _mm(store).estimate(_video_req(store, width=768, height=1344)).cost_usd == (
        pytest.approx(7 * 0.50 / CNY)
    )


@respx.mock
async def test_h3_with_audio_is_reference_to_video(store: BlobStore) -> None:
    create = respx.post(f"{MM}/v2/video_generation").mock(
        return_value=httpx.Response(200, json={"task_id": "t-1"})
    )
    respx.get(f"{MM}/v2/query/video_generation/t-1").mock(
        return_value=httpx.Response(200, json=_done(input_image_count=7))
    )
    respx.get(CDN).mock(return_value=httpx.Response(200, content=await _clip(7)))
    voices = [store.put_bytes(sine_wav(3.0, 200 + i)) for i in range(4)]
    refs = [_picture(store, i) for i in range(1, 11)]
    result = await _mm(store).run(_video_req(store, refs=refs, ref_audio=voices), CallContext())

    content = _sent(create)["content"]
    roles = [c.get("role") for c in content]
    # The first frame becomes <Picture 1>, then the locked pictures: 9 in all; 3 voices at most.
    assert roles == [None] + ["reference_image"] * 9 + ["reference_audio"] * 3
    assert content[3]["image_url"]["url"].startswith("data:image/")
    assert content[-1]["audio_url"]["url"].startswith("data:audio/wav;base64,")
    assert result.usage.calls == {"extra_image": 2}  # 7 pictures, 5 free


@respx.mock
async def test_dubbed_lines_go_as_the_one_reference_audio(store: BlobStore) -> None:
    create = respx.post(f"{MM}/v2/video_generation").mock(
        return_value=httpx.Response(200, json={"task_id": "t-1"})
    )
    respx.get(f"{MM}/v2/query/video_generation/t-1").mock(
        return_value=httpx.Response(200, json=_done())
    )
    respx.get(CDN).mock(return_value=httpx.Response(200, content=await _clip(7)))
    track = store.put_bytes(sine_wav(6.4))
    req = _video_req(store, dialogue_audio=track, ref_audio=[store.put_bytes(sine_wav(2))])
    await _mm(store).run(req, CallContext())
    content = _sent(create)["content"]
    assert [c.get("role") for c in content] == [None, "reference_image", "reference_audio"]
    url = content[2]["audio_url"]["url"]
    assert base64.b64decode(url.split(",", 1)[1]) == store.path_for(track).read_bytes()


@respx.mock
async def test_h3_errors(store: BlobStore) -> None:
    def err(status: int, code: int) -> httpx.Response:
        body = {"type": "error", "error": {"type": "x", "message": f"nope ({code})"}}
        return httpx.Response(status, json=body)

    route = respx.post(f"{MM}/v2/video_generation")
    route.mock(return_value=err(402, 1008))
    with pytest.raises(ModelError) as exc:
        await _mm(store).run(_video_req(store), CallContext())
    assert exc.value.code == "insufficient_balance"

    route.mock(return_value=err(422, 1026))
    with pytest.raises(ModelError) as exc:
        await _mm(store).run(_video_req(store), CallContext())
    assert exc.value.code == "content_blocked"

    # A rate limit is retried; a task that fails reports its code.
    route.mock(side_effect=[err(429, 1002), httpx.Response(200, json={"task_id": "t-1"})])
    respx.get(f"{MM}/v2/query/video_generation/t-1").mock(
        return_value=httpx.Response(
            200, json=_task("failed", error={"code": "1027", "message": "sensitive output"})
        )
    )
    with pytest.raises(ModelError) as exc:
        await _mm(store).run(_video_req(store), CallContext())
    assert exc.value.code == "content_blocked" and route.call_count == 4

    with pytest.raises(ModelError) as exc:
        await MiniMaxVideoAdapter(_spec("minimax/h3-api"), get_key=lambda _: None, store=store).run(
            _video_req(store), CallContext()
        )
    assert exc.value.code == "missing_key"


@respx.mock
async def test_a_short_video_is_refused_but_billed(store: BlobStore) -> None:
    respx.post(f"{MM}/v2/video_generation").mock(
        return_value=httpx.Response(200, json={"task_id": "t-1"})
    )
    respx.get(f"{MM}/v2/query/video_generation/t-1").mock(
        return_value=httpx.Response(200, json=_done())
    )
    respx.get(CDN).mock(return_value=httpx.Response(200, content=await _clip(2)))
    with pytest.raises(ModelError) as exc:
        await _mm(store).run(_video_req(store), CallContext())
    assert exc.value.code == "video_too_short" and exc.value.billed


@respx.mock
async def test_a_canceled_call_cancels_the_queued_task(store: BlobStore) -> None:
    respx.post(f"{MM}/v2/video_generation").mock(
        return_value=httpx.Response(200, json={"task_id": "t-1"})
    )
    respx.get(f"{MM}/v2/query/video_generation/t-1").mock(
        return_value=httpx.Response(200, json=_task("queued"))
    )
    delete = respx.delete(f"{MM}/v2/video_generation/t-1").mock(
        return_value=httpx.Response(200, json={})
    )
    adapter = _mm(store)
    adapter.poll_s = 0.01
    run = asyncio.create_task(adapter.run(_video_req(store), CallContext()))
    await asyncio.sleep(0.1)
    run.cancel()
    with pytest.raises(asyncio.CancelledError):
        await run
    assert delete.called


# ---------------------------------------------------------------------- Context-IR, Regenerate


@respx.mock
async def test_context_ir_answers_the_prompt_and_its_tokens(store: BlobStore) -> None:
    create = respx.post(f"{MM}/v2/h3_context_ir").mock(
        return_value=httpx.Response(200, json={"task_id": "t-1"})
    )
    respx.get(f"{MM}/v2/query/video_generation/t-1").mock(
        return_value=httpx.Response(
            200,
            json=_task(
                "succeeded",
                content={"prompt": "integrated_multimodal_description: [Shot 1] Rain."},
                usage={"total_tokens": 9090, "prompt_tokens": 5664, "completion_tokens": 3426},
                task_type="h3_context_ir",
            ),
        )
    )
    adapter = _mm(store, "minimax/context-ir")
    req = _video_req(store)
    result = await adapter.run(
        ModelRequest(kind="llm_aux", prompt=req.prompt, json_mode=True, params=req.params),
        CallContext(),
    )
    sent = _sent(create)
    assert {k: v for k, v in sent.items() if k != "content"} == {
        "model": "MiniMax-H3",
        "duration": 7,
        "ratio": "9:16",
    }
    assert [c.get("role") for c in sent["content"]] == [None, "first_frame"]
    assert (
        result.text
        == result.json["prompt"]
        == ("integrated_multimodal_description: [Shot 1] Rain.")
    )
    assert (result.usage.tokens_in, result.usage.tokens_out) == (5664, 3426)
    assert cost_usd(adapter.spec.pricing, result.usage) == pytest.approx(
        (5664 * 5.80 + 3426 * 23.00) / 1e6 / CNY
    )


@respx.mock
async def test_regenerate_2k_resends_the_inputs_with_the_draft(store: BlobStore) -> None:
    create = respx.post(f"{MM}/v2/video_regeneration").mock(
        return_value=httpx.Response(200, json={"task_id": "t-1"})
    )
    respx.get(f"{MM}/v2/query/video_generation/t-1").mock(
        return_value=httpx.Response(200, json=_done(input_image_count=1))
    )
    respx.get(CDN).mock(return_value=httpx.Response(200, content=await _clip(7)))
    adapter = _mm(store, "minimax/h3-regenerate-2k")
    draft = store.put_bytes(await _clip(7))
    req = ModelRequest(
        kind="upscale",
        prompt="the prompt sent for the draft",
        params={**_video_req(store).params, "video_in": draft},
    )
    result = await adapter.run(req, CallContext())
    sent = _sent(create)
    assert {k: v for k, v in sent.items() if k != "content"} == {
        "model": "MiniMax-H3",
        "resolution": "2K",
    }
    assert [c.get("role") for c in sent["content"]] == [None, "first_frame", "base_video"]
    assert sent["content"][2]["video_url"]["url"].startswith("data:video/mp4;base64,")
    assert cost_usd(adapter.spec.pricing, result.usage) == pytest.approx(7 * 0.30 / CNY)
    # The estimate counts the draft as input video too (the safe side).
    assert adapter.estimate(req).cost_usd == pytest.approx(7 * 0.60 / CNY)

    req.params.pop("video_in")
    with pytest.raises(ModelError) as exc:
        await adapter.run(req, CallContext())
    assert exc.value.code == "bad_request"


@respx.mock
async def test_h3_health_lists_one_task() -> None:
    route = respx.get(f"{MM}/v2/query/video_generation").mock(
        return_value=httpx.Response(200, json={"tasks": []})
    )
    health = await _mm(BlobStore(Path("unused"))).health()
    assert health.ok and health.models == ["MiniMax-H3"]
    assert route.calls[0].request.url.params["page_size"] == "1"


# ---------------------------------------------------------------------- Seedance 2.5


def _ark_task(status: str, **extra: Any) -> dict[str, Any]:
    return {"id": "cgt-1", "model": "doubao-seedance-2-5-260628", "status": status, **extra}


@respx.mock
async def test_seedance_first_frame_job_billed_by_tokens(store: BlobStore) -> None:
    create = respx.post(f"{ARK}/contents/generations/tasks").mock(
        return_value=httpx.Response(200, json={"id": "cgt-1"})
    )
    tokens = 1080 * 1920 * 24 * 7 // 1024
    respx.get(f"{ARK}/contents/generations/tasks/cgt-1").mock(
        side_effect=[
            httpx.Response(200, json=_ark_task("running")),
            httpx.Response(
                200,
                json=_ark_task(
                    "succeeded",
                    content={"video_url": CDN},
                    resolution="1080p",
                    duration=7,
                    usage={"completion_tokens": tokens, "total_tokens": tokens},
                ),
            ),
        ]
    )
    respx.get(CDN).mock(return_value=httpx.Response(200, content=await _clip(7)))
    adapter = _ark(store)
    req = _video_req(store, dialogue_audio=store.put_bytes(sine_wav(6.4)))
    result = await adapter.run(req, CallContext())

    sent = _sent(create)
    assert create.calls[0].request.headers["authorization"] == "Bearer ark-SECRET"
    assert {k: v for k, v in sent.items() if k != "content"} == {
        "model": "doubao-seedance-2-5-260628",
        "resolution": "1080p",
        "ratio": "adaptive",
        "duration": 7,
        # 先配音: no sound of its own (the lines are laid on in post).
        "generate_audio": False,
        "watermark": False,
    }
    assert [c.get("role") for c in sent["content"]] == [None, "first_frame"]
    assert result.usage.tokens == {"video_1080p": tokens}
    cost = cost_usd(adapter.spec.pricing, result.usage, resolution=result.usage.resolution)
    assert cost == pytest.approx(tokens * 77 / 1e6 / CNY)
    # The estimate (9:16 per second) is close to the bill.
    assert adapter.estimate(req).cost_usd == pytest.approx(cost, rel=0.01)
    plain = adapter._body(_video_req(store))  # no dubbed lines: Seedance makes the sound
    assert plain["generate_audio"] is True


@respx.mock
async def test_seedance_errors(store: BlobStore) -> None:
    route = respx.post(f"{ARK}/contents/generations/tasks")
    route.mock(
        return_value=httpx.Response(
            403, json={"error": {"code": "AccountOverdueError", "message": "overdue"}}
        )
    )
    with pytest.raises(ModelError) as exc:
        await _ark(store).run(_video_req(store), CallContext())
    assert exc.value.code == "insufficient_balance"

    route.mock(return_value=httpx.Response(200, json={"id": "cgt-1"}))
    respx.get(f"{ARK}/contents/generations/tasks/cgt-1").mock(
        return_value=httpx.Response(
            200,
            json=_ark_task(
                "failed",
                error={"code": "OutputVideoSensitiveContentDetected", "message": "no"},
            ),
        )
    )
    with pytest.raises(ModelError) as exc:
        await _ark(store).run(_video_req(store), CallContext())
    assert exc.value.code == "content_blocked"
