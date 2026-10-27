"""Model registry: ``providers.yaml`` → ``ModelSpec`` → adapter.

In mock mode every model is served by ``MockAdapter`` with the real model's key and prices.
Mock mode is the default; real calls need ``DRAMA_MOCK=0`` explicitly. ``DRAMA_REAL_LOCAL=1``
keeps Mock but runs the local ComfyUI workflows and Python workers for real: free local
models on this machine, while API and writing models stay Mock (the local smoke test).
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable

from drama_series_agent.core.config import LocalModel, StudioConfig
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


# Runtimes ``DRAMA_REAL_LOCAL=1`` runs for real in Mock mode (not local LLM servers).
REAL_LOCAL_RUNTIMES = frozenset({"comfyui", "python"})


def is_mock_mode() -> bool:
    return os.environ.get("DRAMA_MOCK", "1") != "0"


def is_real_local() -> bool:
    return os.environ.get("DRAMA_REAL_LOCAL") == "1"


def specs_from_config(cfg: StudioConfig) -> list[ModelSpec]:
    """Every model in the config. ``get_config()`` has the provider accounts on it already
    (``core/config.py:with_accounts``): each provider on its current site, its writing models
    the picked ones, the user's prices and model ids."""
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
                        request=model.request or None,
                    ),
                )
            )
    for media in prov.media_models:
        account = prov.provider(media.account) if media.account else None
        specs.append(
            ModelSpec(
                key=media.key,
                kind=media.kind,
                where="api",
                display=media.display,
                provider_id=media.key.split("/", 1)[0],
                model_id=media.model_id,
                base_url=media.base_url or (account.base_url if account else None),
                key_name=account.key_name if account else None,
                adapter=media.adapter,
                pricing=pricing_for_media(media, prov.as_of),
                caps=Caps.model_validate(media.caps),
            )
        )
    specs += [local_spec(local, prov.as_of) for local in prov.local_models]
    return specs


def local_spec(local: LocalModel, as_of: str | None = None) -> ModelSpec:
    """A ``providers.yaml`` local model (or a library workflow, ``wflib``) as a spec."""
    return ModelSpec(
        key=local.key,
        kind=local.kind,
        where="local",
        display=local.display,
        provider_id=local.key.split("/", 1)[0],
        runtime=local.runtime,
        workflow=local.workflow,
        workflow_root=local.workflow_root,
        worker=local.worker,
        env=local.env,
        worker_args=dict(local.args),
        gpu=local.gpu,
        pricing=Pricing(unit="free", as_of=as_of),
        caps=Caps.model_validate(local.caps),
    )


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
        real_local: bool | None = None,
    ) -> None:
        self._specs = {s.key: s for s in specs}
        self.mock = is_mock_mode() if mock is None else mock
        self.real_local = is_real_local() if real_local is None else real_local
        self.mock_settings = mock_settings or MockSettings()
        self._factories: list[tuple[Callable[[ModelSpec], bool], AdapterFactory]] = []
        self._adapters: dict[str, ModelAdapter] = {}

    @classmethod
    def from_config(cls, cfg: StudioConfig, **kwargs: object) -> Registry:
        return cls(specs_from_config(cfg), **kwargs)  # type: ignore[arg-type]

    def reload(self, cfg: StudioConfig) -> None:
        """The provider accounts changed (a site, a pick, a price): the API models are built
        again from ``cfg``; writing models no longer picked are dropped."""
        fresh = {s.key: s for s in specs_from_config(cfg) if s.where == "api"}
        for key, spec in list(self._specs.items()):
            if spec.where == "api" and key not in fresh:
                del self._specs[key]
                self._adapters.pop(key, None)
        for spec in fresh.values():
            if self._specs.get(spec.key) != spec:
                self.add_spec(spec)

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

    async def aclose(self) -> None:
        """Stop what adapters keep running (local model workers)."""
        for adapter in list(self._adapters.values()):
            stop = getattr(adapter, "stop", None)
            if stop is not None:
                await stop()

    def _build(self, spec: ModelSpec) -> ModelAdapter:
        real = self.real_local and spec.where == "local" and spec.runtime in REAL_LOCAL_RUNTIMES
        if self.mock and not real:
            return MockAdapter(spec, self.mock_settings)
        for matches, factory in self._factories:
            if matches(spec):
                return factory(spec)
        return UnavailableAdapter(spec)
