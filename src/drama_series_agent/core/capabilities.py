"""Which local models this machine can run (SPEC 7.3, 12.2-1).

A local model in ``providers.yaml`` may say what it needs: ``requires_cuda`` and ``needs`` (ids
of ``setup-manifest.yaml`` items). The last scan says which items this machine has; an item the
installer finished since then counts too. A local model with an unmet need cannot run here, so
``resolve()`` routes around it (``restrict``):

- ``local_model`` → ``None``; a ``local`` / ``hybrid`` component goes ``api`` (``off`` when it
  has no API model, e.g. ControlNet on a Mac);
- ``fallback.to`` → ``None`` (the router then takes the next in ``alt_order``);
- dropped from ``alt_order``.

A local model without ``needs`` (nothing in the manifest covers it) counts as runnable; if it
fails at run time the usual fallback applies. Before the first scan nothing is filtered.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from drama_series_agent.core.config import LlmModel, LocalModel, ProvidersConfig

CUDA = "cuda"
# Scan statuses that mean "this machine has it": an outdated item or one whose check only
# warned is still there (same rule as the installer's dependency check).
FOUND_STATUSES = frozenset({"ok", "old", "warn"})


@dataclass(frozen=True)
class Capabilities:
    cuda: bool
    found: frozenset[str]  # setup item ids present on this machine

    @classmethod
    def of(cls, *, cuda: bool, found: Iterable[str]) -> Capabilities:
        return cls(cuda=cuda, found=frozenset(found))

    def missing(self, model: LocalModel | LlmModel) -> list[str]:
        """What ``model`` lacks here: ``cuda`` first, then item ids in ``needs`` order."""
        out = [CUDA] if model.requires_cuda and not self.cuda else []
        return out + [n for n in model.needs if n not in self.found]


def local_model(providers: ProvidersConfig, key: str) -> LocalModel | LlmModel | None:
    """The ``providers.yaml`` row of a local model; ``None`` for API models and unknown keys."""
    for m in providers.local_models:
        if m.key == key:
            return m
    for p in providers.llm_providers:
        if p.where == "local":
            for llm in p.models:
                if llm.key == key:
                    return llm
    return None


def unmet(providers: ProvidersConfig, caps: Capabilities, key: str) -> list[str]:
    """Why ``key`` cannot run on this machine; empty when it can (or is not a local model)."""
    model = local_model(providers, key)
    return caps.missing(model) if model is not None else []


def restrict(
    values: dict[str, Any], providers: ProvidersConfig, caps: Capabilities
) -> dict[str, list[str]]:
    """Route resolved ``values`` around local models this machine cannot run (in place).

    Returns the models taken out, each with what it lacks.
    """
    gone: dict[str, list[str]] = {}

    def blocked(key: Any) -> bool:
        if not isinstance(key, str):
            return False
        if key not in gone and (lacks := unmet(providers, caps, key)):
            gone[key] = lacks
        return key in gone

    if blocked(values.get("local_model")):
        values["local_model"] = None
        if values.get("mode") in ("local", "hybrid"):
            values["mode"] = "api" if values.get("api_model") else "off"
    fallback = values.get("fallback")
    if isinstance(fallback, dict) and blocked(fallback.get("to")):
        fallback["to"] = None
    if isinstance(values.get("alt_order"), list):
        values["alt_order"] = [m for m in values["alt_order"] if not blocked(m)]
    return gone
