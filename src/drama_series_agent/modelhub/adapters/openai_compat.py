"""One adapter for every OpenAI-compatible chat endpoint (SPEC 6.2): DeepSeek, Kimi, Qwen,
Doubao, GLM, MiniMax, Gemini's compatible endpoint, OpenAI, OpenRouter, Ollama, llama.cpp
and user-defined endpoints."""

from __future__ import annotations

import json
from typing import Any

import httpx

from drama_series_agent.modelhub.adapters.base import (
    CallContext,
    Estimate,
    Health,
    ModelError,
    ModelRequest,
    ModelResult,
    ModelSpec,
    Usage,
)
from drama_series_agent.modelhub.adapters.http import KeyGetter, error_for, send
from drama_series_agent.modelhub.adapters.mock import estimate_tokens
from drama_series_agent.modelhub.pricing import cost_usd
from drama_series_agent.utils.llm_client import normalize_base_url


class OpenAICompatAdapter:
    def __init__(
        self,
        spec: ModelSpec,
        *,
        get_key: KeyGetter,
        base_url: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        max_retries: int = 3,
        backoff_s: float = 1.0,
        request_timeout_s: float = 300.0,
    ) -> None:
        self.spec = spec
        self._get_key = get_key
        self._base_url = normalize_base_url(base_url or spec.base_url or "")
        self._transport = transport
        self.max_retries = max_retries
        self.backoff_s = backoff_s
        self.request_timeout_s = request_timeout_s

    @property
    def key(self) -> str:
        return self.spec.key

    # ------------------------------------------------------------------ protocol

    def estimate(self, req: ModelRequest) -> Estimate:
        usage = Usage(tokens_in=estimate_tokens(req.text()), tokens_out=req.max_tokens or 800)
        return Estimate(
            cost_usd=cost_usd(self.spec.pricing, usage),
            seconds=10.0,
            priced=self.spec.pricing.known,
        )

    async def health(self) -> Health:
        try:
            async with self._client() as client:
                resp = await client.get("/models", headers=self._headers())
        except ModelError as exc:
            return Health(ok=False, detail=exc.code)
        except httpx.HTTPError as exc:
            return Health(ok=False, detail=f"network_error: {type(exc).__name__}")
        if resp.status_code != 200:
            return Health(ok=False, detail=error_for(resp.status_code, resp.text).code)
        data = resp.json().get("data") or []
        ids = sorted(str(m.get("id")) for m in data if isinstance(m, dict) and m.get("id"))
        return Health(ok=True, models=ids)

    async def run(self, req: ModelRequest, ctx: CallContext) -> ModelResult:
        if not self.spec.model_id:
            raise ModelError("model_id_missing", f"{self.key}: fill model_id in providers.yaml")
        body = self._body(req)
        if body.get("stream"):
            return await self._run_stream(body, ctx)
        resp = await self._post(body)
        data = resp.json()
        try:
            text = data["choices"][0]["message"].get("content") or ""
        except (KeyError, IndexError, TypeError):
            raise ModelError("invalid_response", json.dumps(data)[:300]) from None
        return self._result(text, data.get("usage") or {}, req, data)

    # ------------------------------------------------------------------ internals

    def _client(self) -> httpx.AsyncClient:
        if not self._base_url:
            raise ModelError("base_url_missing", self.key)
        return httpx.AsyncClient(
            base_url=self._base_url, timeout=self.request_timeout_s, transport=self._transport
        )

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.spec.key_name:
            api_key = self._get_key(self.spec.key_name)
            if not api_key:
                raise ModelError("missing_key", self.spec.key_name)
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    def _body(self, req: ModelRequest) -> dict[str, Any]:
        messages = list(req.messages or [])
        if req.prompt:
            messages.append({"role": "user", "content": req.prompt})
        body: dict[str, Any] = {"model": self.spec.model_id, "messages": messages}
        if req.max_tokens:
            body["max_tokens"] = req.max_tokens
        if req.seed is not None:
            body["seed"] = req.seed
        if req.json_mode and self.spec.caps.json_mode:
            body["response_format"] = {"type": "json_object"}
        extra = self.spec.caps.model_extra or {}
        num_ctx = extra.get("num_ctx")
        if num_ctx:
            body["options"] = {"num_ctx": int(num_ctx)}
        for name, value in (extra.get("request") or {}).items():
            body.setdefault(name, value)  # providers.yaml ``request``, e.g. DeepSeek's thinking
        for name in ("temperature", "top_p", "stream"):
            if name in req.params:
                body[name] = req.params[name]
        if body.get("stream"):
            body["stream_options"] = {"include_usage": True}
        return body

    async def _post(self, body: dict[str, Any]) -> httpx.Response:
        headers = self._headers()
        async with self._client() as client:
            return await send(
                client,
                "POST",
                "/chat/completions",
                json=body,
                headers=headers,
                max_retries=self.max_retries,
                backoff_s=self.backoff_s,
            )

    async def _run_stream(self, body: dict[str, Any], ctx: CallContext) -> ModelResult:
        headers = self._headers()
        parts: list[str] = []
        usage: dict[str, Any] = {}
        async with (
            self._client() as client,
            client.stream("POST", "/chat/completions", json=body, headers=headers) as resp,
        ):
            if resp.status_code != 200:
                raise error_for(resp.status_code, (await resp.aread()).decode(errors="replace"))
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                chunk = json.loads(payload)
                usage = chunk.get("usage") or usage
                for choice in chunk.get("choices") or []:
                    delta = (choice.get("delta") or {}).get("content")
                    if delta:
                        parts.append(delta)
                        if ctx.on_delta is not None:
                            await ctx.on_delta(delta)
        req = ModelRequest(kind="llm", json_mode="response_format" in body)
        return self._result("".join(parts), usage, req, {"stream": True})

    def _result(
        self, text: str, usage: dict[str, Any], req: ModelRequest, raw: dict[str, Any]
    ) -> ModelResult:
        parsed: Any = None
        if req.json_mode:
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None  # components validate and retry (SPEC 5.1)
        return ModelResult(
            text=text,
            json=parsed,
            usage=Usage(
                tokens_in=usage.get("prompt_tokens"), tokens_out=usage.get("completion_tokens")
            ),
            raw={"id": raw.get("id"), "model": raw.get("model")},
        )
