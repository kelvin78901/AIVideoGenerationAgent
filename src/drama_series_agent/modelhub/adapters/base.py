"""Adapter protocol and the request / result types shared by every model (SPEC 6.1)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

Where = Literal["local", "api"]


class Caps(BaseModel):
    """What a model can do. Unknown vendor-specific capabilities are kept as extra fields."""

    model_config = ConfigDict(extra="allow")

    aspects: list[str] | None = None
    max_refs: int | None = None
    durations: list[float] | None = None
    audio_in: bool = False
    control_video: bool = False
    resolutions: list[str] | None = None
    json_mode: bool = False
    langs: list[str] | None = None
    max_context: int | None = None


PriceUnit = Literal["token", "image", "second", "minute", "char", "call", "world", "free"]


class Pricing(BaseModel):
    """Unit prices. Token prices are per million tokens; ``price`` is per ``unit``."""

    unit: PriceUnit = "free"
    price_in: float | None = None
    price_out: float | None = None
    price: float | None = None
    input_price_per_second: float | None = None
    price_by_res: dict[str, float] | None = None
    # Flat prices of extra services billed per use (MiniMax's voice design $3), counted by
    # ``Usage.calls``.
    extras: dict[str, float] | None = None
    currency: str = "USD"
    as_of: str | None = None
    offpeak: dict[str, Any] | None = None

    @property
    def known(self) -> bool:
        if self.unit == "free":
            return True
        if self.unit == "token":
            return self.price_in is not None and self.price_out is not None
        return self.price is not None or bool(self.price_by_res)

    def snapshot(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class ModelRequest(BaseModel):
    kind: str
    messages: list[dict[str, Any]] | None = None
    prompt: str | None = None
    json_mode: bool = False
    max_tokens: int | None = None
    seed: int | None = None
    # Model-specific knobs (width, height, duration_s, voice, refs, ...). Mock adapters also
    # read ``mock_delay_s`` here.
    params: dict[str, Any] = Field(default_factory=dict)
    # Who is asking, never sent to a provider: ``component`` and ``task`` (``run``,
    # ``rewrite_line`` …). Mock mode answers with the responder registered for that pair.
    meta: dict[str, Any] = Field(default_factory=dict)

    def text(self) -> str:
        """All prompt text, for estimates and mocks."""
        parts = [self.prompt or ""]
        for msg in self.messages or []:
            content = msg.get("content")
            if isinstance(content, str):
                parts.append(content)
        return "\n".join(p for p in parts if p)


class Usage(BaseModel):
    tokens_in: int | None = None
    tokens_out: int | None = None
    images: int | None = None
    output_seconds: float | None = None
    chars: int | None = None
    input_seconds: float | None = None
    # Extra services used, priced by ``Pricing.extras`` (e.g. ``{"voice_design": 1}``).
    calls: dict[str, int] | None = None


@dataclass
class OutputFile:
    role: str  # "image", "audio", "video", ...
    mime: str
    data: bytes | None = None
    path: Path | None = None
    w: int | None = None
    h: int | None = None
    duration_s: float | None = None


@dataclass
class ModelResult:
    text: str | None = None
    json: Any = None
    files: list[OutputFile] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Estimate:
    cost_usd: float
    seconds: float
    priced: bool = True  # False when the model has no known price yet


@dataclass(frozen=True)
class Health:
    ok: bool
    detail: str | None = None
    models: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CallContext:
    """Who a call belongs to; copied onto the ``model_call`` row."""

    component_id: str | None = None
    series_id: str | None = None
    episode_id: str | None = None
    scene_id: str | None = None
    shot_id: str | None = None
    product_id: str | None = None
    version_id: str | None = None
    job_id: str | None = None
    attempt: int = 1
    is_switch: bool = False
    # A call made without a job that the user agreed to pay up to this much for (e.g. a
    # rewrite proposal over the per-call cap); jobs carry it on the job row instead.
    confirmed_usd: float | None = None
    # Streaming LLMs push text deltas here (e.g. to forward them over SSE).
    on_delta: Callable[[str], Awaitable[None]] | None = None


class ModelError(Exception):
    """A failed model call. ``code`` is stable and translated by the front end."""

    def __init__(
        self,
        code: str,
        message: str = "",
        *,
        retryable: bool = False,
        status: int | None = None,
        billed: bool = False,
    ) -> None:
        super().__init__(message or code)
        self.code = code
        self.retryable = retryable
        self.status = status
        self.billed = billed


@dataclass(frozen=True)
class ModelSpec:
    """Static description of one model, built from ``providers.yaml`` (or the DB)."""

    key: str
    kind: str
    where: Where
    display: str
    provider_id: str | None = None
    model_id: str | None = None
    base_url: str | None = None
    key_name: str | None = None
    runtime: str | None = None
    workflow: str | None = None  # a ComfyUI model's workflow folder (SPEC 6.4)
    pricing: Pricing = field(default_factory=Pricing)
    caps: Caps = field(default_factory=Caps)


@runtime_checkable
class ModelAdapter(Protocol):
    spec: ModelSpec

    @property
    def key(self) -> str: ...

    async def run(self, req: ModelRequest, ctx: CallContext) -> ModelResult: ...

    def estimate(self, req: ModelRequest) -> Estimate: ...

    async def health(self) -> Health: ...
