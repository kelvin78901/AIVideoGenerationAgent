"""MiniMax speech (T2A v2 and voice design) against respx fakes: never the network."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
import respx

from drama_series_agent.core.config import get_config
from drama_series_agent.modelhub.adapters.base import CallContext, ModelError, ModelRequest
from drama_series_agent.modelhub.adapters.minimax import MiniMaxSpeechAdapter, billed_chars
from drama_series_agent.modelhub.adapters.mock import sine_wav
from drama_series_agent.modelhub.pricing import cost_usd
from drama_series_agent.modelhub.registry import specs_from_config

BASE = "https://api.minimax.io/v1"
KEY = "mm-SECRET"
WAV = sine_wav(0.5)


def _adapter(key: str = "minimax/speech-2.8-hd") -> MiniMaxSpeechAdapter:
    spec = next(s for s in specs_from_config(get_config()) if s.key == key)
    return MiniMaxSpeechAdapter(
        spec, get_key=lambda name: KEY if name == "MINIMAX_API_KEY" else None, backoff_s=0
    )


def _ok(**extra: Any) -> dict[str, Any]:
    return {
        "data": {"audio": WAV.hex(), "status": 2},
        "extra_info": {"audio_length": 1500, "usage_characters": 20, **extra},
        "trace_id": "t-1",
        "base_resp": {"status_code": 0, "status_msg": "success"},
    }


def _failed(code: int) -> dict[str, Any]:
    return {"base_resp": {"status_code": code, "status_msg": "nope"}}


def _tts(**params: Any) -> ModelRequest:
    return ModelRequest(kind="tts", prompt="三年了。他凭什么。", params=params)


def test_billed_characters_count_cjk_twice() -> None:
    assert billed_chars("三年了。") == 8 and billed_chars("ok!") == 3


@respx.mock
async def test_t2a_request_and_the_first_use_fee() -> None:
    route = respx.post(f"{BASE}/t2a_v2").mock(
        return_value=httpx.Response(200, json=_ok(usage_voice_count=1))
    )
    adapter = _adapter()
    req = _tts(voice_id="v-1", emotion="angry", vol=2.0, charge_design=True, tone="咬牙")
    result = await adapter.run(req, CallContext())
    sent = json.loads(route.calls.last.request.content)
    assert sent == {
        "language_boost": "auto",
        "model": "speech-2.8-hd",
        "text": "三年了。他凭什么。",
        "stream": False,
        "voice_setting": {
            "voice_id": "v-1",
            "speed": 1,
            "vol": 2.0,
            "pitch": 0,
            "emotion": "angry",
        },
        "audio_setting": {"sample_rate": 44100, "format": "wav", "channel": 1},
        "output_format": "hex",
    }
    assert route.calls.last.request.headers["authorization"] == f"Bearer {KEY}"
    (f,) = result.files
    assert (f.data, f.mime, f.duration_s) == (WAV, "audio/wav", 1.5)
    assert result.usage.chars == 20 and result.usage.calls == {"voice_design": 1}
    assert cost_usd(adapter.spec.pricing, result.usage) == pytest.approx(3 + 20 * 100 / 1e6)


@respx.mock
async def test_no_voice_fee_unless_minimax_bills_one() -> None:
    respx.post(f"{BASE}/t2a_v2").mock(return_value=httpx.Response(200, json=_ok()))
    adapter = _adapter()
    result = await adapter.run(_tts(voice_id="v-1", charge_design=True), CallContext())
    assert result.usage.calls is None
    assert cost_usd(adapter.spec.pricing, result.usage) == pytest.approx(20 * 100 / 1e6)
    # The estimate still counts the $3 the first synthesis is expected to cost.
    est = adapter.estimate(_tts(voice_id="v-1", charge_design=True)).cost_usd
    assert est == pytest.approx(3 + billed_chars("三年了。他凭什么。") * 100 / 1e6)


@respx.mock
async def test_voice_design_returns_the_id_and_its_trial() -> None:
    route = respx.post(f"{BASE}/voice_design").mock(
        return_value=httpx.Response(
            200,
            json={
                "voice_id": "ttv-voice-1",
                "trial_audio": WAV.hex(),
                "base_resp": {"status_code": 0, "status_msg": "success"},
            },
        )
    )
    adapter = _adapter()
    lines = "我" * 600
    req = ModelRequest(
        kind="voice_design", prompt=lines, params={"design": "二十多岁的女声，偏低沉"}
    )
    result = await adapter.run(req, CallContext())
    sent = json.loads(route.calls.last.request.content)
    assert sent == {"prompt": "二十多岁的女声，偏低沉", "preview_text": "我" * 500}
    assert result.json == {"voice_id": "ttv-voice-1"} and result.files[0].data == WAV
    assert result.usage.calls == {"design_preview_char": 1000}
    assert cost_usd(adapter.spec.pricing, result.usage) == pytest.approx(1000 * 60 / 1e6)
    assert adapter.estimate(req).cost_usd == pytest.approx(1000 * 60 / 1e6)


@respx.mock
async def test_base_resp_errors() -> None:
    route = respx.post(f"{BASE}/t2a_v2")
    adapter = _adapter()
    route.mock(
        side_effect=[httpx.Response(200, json=_failed(1002)), httpx.Response(200, json=_ok())]
    )
    assert len((await adapter.run(_tts(voice_id="v"), CallContext())).files) == 1
    assert route.call_count == 2
    for status, code in (
        (1008, "insufficient_balance"),
        (2054, "voice_not_found"),
        (1026, "content_blocked"),
        (1004, "auth_failed"),
    ):
        route.mock(return_value=httpx.Response(200, json=_failed(status)))
        with pytest.raises(ModelError) as exc:
            await adapter.run(_tts(voice_id="v"), CallContext())
        assert exc.value.code == code
    with pytest.raises(ModelError) as exc:
        await adapter.run(_tts(), CallContext())
    assert exc.value.code == "voice_id_missing"


@respx.mock
async def test_whisper_runs_on_2_6() -> None:
    route = respx.post(f"{BASE}/t2a_v2").mock(return_value=httpx.Response(200, json=_ok()))
    await _adapter("minimax/speech-2.6-hd").run(
        _tts(voice_id="v", emotion="whisper"), CallContext()
    )
    sent = json.loads(route.calls.last.request.content)
    assert sent["model"] == "speech-2.6-hd" and sent["voice_setting"]["emotion"] == "whisper"


@respx.mock
async def test_health_lists_voices_for_free() -> None:
    route = respx.post(f"{BASE}/get_voice").mock(
        return_value=httpx.Response(
            200, json={"voice_generation": [], "base_resp": {"status_code": 0}}
        )
    )
    health = await _adapter().health()
    assert health.ok and health.models == ["speech-2.8-hd"]
    assert json.loads(route.calls.last.request.content) == {"voice_type": "voice_generation"}
    route.mock(return_value=httpx.Response(200, json=_failed(2049)))
    assert (await _adapter().health()).detail == "auth_failed"
    spec = _adapter().spec
    assert (
        await MiniMaxSpeechAdapter(spec, get_key=lambda _n: None).health()
    ).detail == "missing_key"
