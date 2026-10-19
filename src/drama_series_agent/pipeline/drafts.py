"""What a run or an edit hands to the product service (``ProductService.append``)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class DependencyDraft:
    upstream_product_id: str
    upstream_hash: str
    slice: str = ""


@dataclass
class VersionDraft:
    """What a run or an edit produced; ``append`` turns it into a version."""

    payload: dict[str, Any]
    files: list[dict[str, Any]] = field(default_factory=list)
    intent: str | None = None
    compiled: str | None = None
    compiled_overridden: bool = False
    model_key: str | None = None
    where: str | None = None
    seed: int | None = None
    params: dict[str, Any] = field(default_factory=dict)
    cost_usd: float = 0.0
    job_id: str | None = None
    fallback_reason: str | None = None
    stage: str | None = None
    note: str | None = None
    dependencies: list[DependencyDraft] = field(default_factory=list)
    # The demo seed inserts versions with the ids and times of the MSW fixtures.
    id: str | None = None
    created_at: datetime | None = None
