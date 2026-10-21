"""What a run or an edit hands to the product service (``ProductService.append``), and an edit
worked out but not written yet (``PlannedChange``, for the impact preview)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession


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


@dataclass
class PlannedChange:
    """An edit worked out but not written (M2 step 10). The impact preview stages it in a
    transaction it rolls back, to see which slices it changes; 确认 calls ``commit``.

    Most edits adopt a new version (``payload``, staged as the product's adopted version);
    an edit that is not a version (a suggestion's decision) stages itself with ``stage``.
    """

    product_id: str
    series_id: str
    # The version it was made from: applying it later must find the same one.
    base_version_id: str | None
    commit: Callable[[], Awaitable[object]]
    payload: dict[str, Any] | None = None
    stage: Callable[[AsyncSession], Awaitable[None]] | None = None
    # What it writes, compared when it is applied (the payload, or the decision).
    content: Any = None
