from __future__ import annotations

import json
from dataclasses import replace

import httpx
import pytest
import respx

from drama_series_agent.modelhub.adapters.base import (
    CallContext,
    Caps,
    ModelError,
    ModelRequest,
    ModelSpec,
    Pricing,
)
from drama_series_agent.modelhub.adapters.openai_compat import OpenAICompatAdapter

BASE = "https://api.example.com/v1"
KEY = "sk-test-SECRET-123456"


def _adapter(**kwargs: object) -> OpenAICompatAdapter:
    spec = ModelSpec(
        key="example/pro",
        kind="llm",
        where="api",
        display="Example Pro",
        provider_id="example",
        model_id="example-pro-2026",
        base_url=BASE,
        key_name="EXAMPLE_API_KEY",
        pricing=Pricing(unit="token", price_in=1.0, price_out=2.0),
        caps=Caps(json_mode=True),
    )
    return OpenAICompatAdapter(
        spec,
        get_key=lambda name: KEY if name == "EXAMPLE_API_KEY" else None,
        backoff_s=0,
        **kwargs,  # type: ignore[arg-type]
    )


def _completion(text: str) -> dict[str, object]:
    return {
        "id": "cmpl-1",
        "model": "example-pro-2026",
        "choices": [{"message": {"role": "assistant", "content": text}}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 34},
    }


@respx.mock
async def test_chat_completion_request_and_usage() -> None:
    route = respx.post(f"{BASE}/chat/completions").mock(
        return_value=httpx.Response(200, json=_completion('{"scenes": []}'))
    )
    req = ModelRequest(
        kind="llm",
        messages=[{"role": "system", "content": "你是编剧"}],
        prompt="写第一场",
        json_mode=True,
        max_tokens=500,
        params={"temperature": 0.3},
    )
    result = await _adapter().run(req, CallContext())
    sent = json.loads(route.calls.last.request.content)
    assert sent["model"] == "example-pro-2026"
    assert sent["messages"][-1] == {"role": "user", "content": "写第一场"}
    assert sent["response_format"] == {"type": "json_object"}
    assert sent["max_tokens"] == 500 and sent["temperature"] == 0.3
    assert route.calls.last.request.headers["authorization"] == f"Bearer {KEY}"
    assert result.json == {"scenes": []}
    assert (result.usage.tokens_in, result.usage.tokens_out) == (12, 34)


@respx.mock
async def test_model_request_fields_are_sent_without_replacing_the_adapters() -> None:
    # providers.yaml ``request`` (e.g. DeepSeek's thinking switch) goes into every body; it
    # never replaces the model, and a request's own params still win.
    route = respx.post(f"{BASE}/chat/completions").mock(
        return_value=httpx.Response(200, json=_completion("ok"))
    )
    caps = Caps(
        json_mode=True,
        request={"thinking": {"type": "disabled"}, "model": "other", "temperature": 1.0},
    )
    adapter = OpenAICompatAdapter(
        replace(_adapter().spec, caps=caps), get_key=lambda name: KEY, backoff_s=0
    )
    req = ModelRequest(kind="llm", prompt="写第一场", params={"temperature": 0.3})
    await adapter.run(req, CallContext())
    sent = json.loads(route.calls.last.request.content)
    assert sent["thinking"] == {"type": "disabled"}
    assert sent["model"] == "example-pro-2026" and sent["temperature"] == 0.3


@respx.mock
async def test_retries_429_then_succeeds() -> None:
    route = respx.post(f"{BASE}/chat/completions").mock(
        side_effect=[
            httpx.Response(429, headers={"retry-after": "0"}, text="slow down"),
            httpx.Response(503, text="busy"),
            httpx.Response(200, json=_completion("好")),
        ]
    )
    result = await _adapter().run(ModelRequest(kind="llm", prompt="x"), CallContext())
    assert result.text == "好"
    assert route.call_count == 3


@respx.mock
async def test_gives_up_after_max_retries() -> None:
    respx.post(f"{BASE}/chat/completions").mock(return_value=httpx.Response(429, text="no"))
    with pytest.raises(ModelError) as err:
        await _adapter(max_retries=2).run(ModelRequest(kind="llm", prompt="x"), CallContext())
    assert err.value.code == "rate_limited" and err.value.retryable


@respx.mock
@pytest.mark.parametrize(
    ("status", "code"), [(401, "auth_failed"), (404, "model_not_found"), (400, "bad_request")]
)
async def test_non_retryable_errors(status: int, code: str) -> None:
    route = respx.post(f"{BASE}/chat/completions").mock(return_value=httpx.Response(status))
    with pytest.raises(ModelError) as err:
        await _adapter().run(ModelRequest(kind="llm", prompt="x"), CallContext())
    assert err.value.code == code
    assert route.call_count == 1


async def test_missing_key_and_model_id() -> None:
    spec = _adapter().spec
    no_key = OpenAICompatAdapter(spec, get_key=lambda _n: None)
    with pytest.raises(ModelError) as err:
        await no_key.run(ModelRequest(kind="llm", prompt="x"), CallContext())
    assert err.value.code == "missing_key"
    from dataclasses import replace

    no_id = OpenAICompatAdapter(replace(spec, model_id=None), get_key=lambda _n: KEY)
    with pytest.raises(ModelError) as err:
        await no_id.run(ModelRequest(kind="llm", prompt="x"), CallContext())
    assert err.value.code == "model_id_missing"


@respx.mock
async def test_streaming_forwards_deltas() -> None:
    chunks = [
        {"choices": [{"delta": {"content": "雨"}}]},
        {"choices": [{"delta": {"content": "停"}}]},
        {"choices": [], "usage": {"prompt_tokens": 5, "completion_tokens": 2}},
    ]
    body = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
    respx.post(f"{BASE}/chat/completions").mock(
        return_value=httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})
    )
    seen: list[str] = []

    async def on_delta(text: str) -> None:
        seen.append(text)

    result = await _adapter().run(
        ModelRequest(kind="llm", prompt="x", params={"stream": True}),
        CallContext(on_delta=on_delta),
    )
    assert seen == ["雨", "停"]
    assert result.text == "雨停" and result.usage.tokens_out == 2


@respx.mock
async def test_health_lists_models() -> None:
    respx.get(f"{BASE}/models").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "b"}, {"id": "a"}]})
    )
    health = await _adapter().health()
    assert health.ok and health.models == ["a", "b"]


@respx.mock
async def test_health_reports_bad_key() -> None:
    respx.get(f"{BASE}/models").mock(return_value=httpx.Response(401))
    health = await _adapter().health()
    assert not health.ok and health.detail == "auth_failed"
