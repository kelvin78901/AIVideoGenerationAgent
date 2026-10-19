"""Model registry: ``providers.yaml`` → ``ModelSpec`` → adapter.

In mock mode every model is served by ``MockAdapter`` with the real model's key and prices.
Mock mode is the default; real calls need ``DRAMA_MOCK=0`` explicitly.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable

from drama_series_agent.core.config import StudioConfig
from drama_series_agent.modelhub.adapters.base import (
    CallContext,
    Caps,
    Estimate,
    Health,
    ModelAdapter,
    ModelError,
    ModelRequest,
    ModelResult,
    ModelSpec,
    Pricing,
)
from drama_series_agent.modelhub.adapters.mock import MockAdapter, MockSettings, Responder
from drama_series_agent.modelhub.pricing import pricing_for_llm, pricing_for_media

AdapterFactory = Callable[[ModelSpec], ModelAdapter]


def is_mock_mode() -> bool:
    return os.environ.get("DRAMA_MOCK", "1") != "0"


def specs_from_config(cfg: StudioConfig) -> list[ModelSpec]:
    prov = cfg.providers
    specs: list[ModelSpec] = []
    for provider in prov.llm_providers:
        for model in provider.models:
            extra = model.model_extra or {}
            specs.append(
                ModelSpec(
                    key=model.key,
                    kind="llm",
                    where=provider.where,
                    display=model.display,
                    provider_id=provider.id,
                    model_id=model.model_id,
                    base_url=provider.base_url,
                    key_name=provider.key_name,
                    pricing=pricing_for_llm(model, prov.as_of),
                    caps=Caps(
                        json_mode=model.json_mode,
                        max_context=model.max_context or extra.get("context"),
                        num_ctx=model.max_context if provider.send_num_ctx else None,
                    ),
                )
            )
    for media in prov.media_models:
        specs.append(
            ModelSpec(
                key=media.key,
                kind=media.kind,
                where="api",
                display=media.display,
                provider_id=media.key.split("/", 1)[0],
                pricing=pricing_for_media(media, prov.as_of),
                caps=Caps.model_validate(media.caps),
            )
        )
    for local in prov.local_models:
        specs.append(
            ModelSpec(
                key=local.key,
                kind=local.kind,
                where="local",
                display=local.display,
                provider_id=local.key.split("/", 1)[0],
                runtime=local.runtime,
                pricing=Pricing(unit="free", as_of=prov.as_of),
            )
        )
    return specs


class UnavailableAdapter:
    """Placeholder for models whose real adapter is not implemented yet."""

    def __init__(self, spec: ModelSpec) -> None:
        self.spec = spec

    @property
    def key(self) -> str:
        return self.spec.key

    def estimate(self, req: ModelRequest) -> Estimate:
        return Estimate(cost_usd=0.0, seconds=0.0, priced=self.spec.pricing.known)

    async def health(self) -> Health:
        return Health(ok=False, detail="adapter_unavailable")

    async def run(self, req: ModelRequest, ctx: CallContext) -> ModelResult:
        raise ModelError("adapter_unavailable", f"no adapter for {self.spec.key} yet")


class Registry:
    def __init__(
        self,
        specs: Iterable[ModelSpec],
        *,
        mock: bool | None = None,
        mock_settings: MockSettings | None = None,
    ) -> None:
        self._specs = {s.key: s for s in specs}
        self.mock = is_mock_mode() if mock is None else mock
        self.mock_settings = mock_settings or MockSettings()
        self._factories: list[tuple[Callable[[ModelSpec], bool], AdapterFactory]] = []
        self._adapters: dict[str, ModelAdapter] = {}

    @classmethod
    def from_config(cls, cfg: StudioConfig, **kwargs: object) -> Registry:
        return cls(specs_from_config(cfg), **kwargs)  # type: ignore[arg-type]

    def add_factory(self, matches: Callable[[ModelSpec], bool], factory: AdapterFactory) -> None:
        """Real adapters register here, e.g. OpenAI-compatible for every ``llm`` spec."""
        self._factories.append((matches, factory))
        self._adapters.clear()

    def add_mock_responder(self, component: str, task: str, responder: Responder) -> None:
        """What Mock mode answers for (component, task); real adapters never see it."""
        self.mock_settings.responders[(component, task)] = responder

    def add_spec(self, spec: ModelSpec) -> None:
        self._specs[spec.key] = spec
        self._adapters.pop(spec.key, None)

    def spec(self, key: str) -> ModelSpec:
        try:
            return self._specs[key]
        except KeyError:
            raise ModelError("unknown_model", f"unknown model: {key}") from None

    def specs(self) -> list[ModelSpec]:
        return list(self._specs.values())

    def get(self, key: str) -> ModelAdapter:
        if key not in self._adapters:
            spec = self.spec(key)
            self._adapters[key] = self._build(spec)
        return self._adapters[key]

    def _build(self, spec: ModelSpec) -> ModelAdapter:
        if self.mock:
            return MockAdapter(spec, self.mock_settings)
        for matches, factory in self._factories:
            if matches(spec):
                return factory(spec)
        return UnavailableAdapter(spec)
