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


def file_entry(
    role: str,
    sha256: str,
    mime: str,
    *,
    w: int | None = None,
    h: int | None = None,
    duration_s: float | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """One ``files[]`` item of a version (SPEC 4.2); ``extra`` e.g. a candidate's ``idx``."""
    return {
        "role": role,
        "path": f"blobs/sha256/{sha256[:2]}/{sha256}",
        "sha256": sha256,
        "mime": mime,
        "duration_s": duration_s,
        "w": w,
        "h": h,
        **extra,
    }


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
    # Made by a local ComfyUI workflow (SPEC 6.4.5).
    workflow_id: str | None = None
    workflow_sha256: str | None = None
    comfy_env_hash: str | None = None
    # The demo seed inserts versions with the ids and times of the MSW fixtures.
    id: str | None = None
    created_at: datetime | None = None


@dataclass
class PlannedChange:
    """An edit worked out but not written (M2 step 10). The impact preview stages it in a
    transaction it rolls back, to see which slices it changes; 确认 calls ``commit``.

    Most edits adopt a new version (``payload``, staged as the product's adopted version);
    an edit that is not a version (a suggestion's decision) stages itself with ``stage``.
    A change that touches no content (unlocking an asset, M3) changes no hash, so its planner
    lists what it affects itself (``lines``, ``unaffected``).
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
    # Impact lines worked out by the planner: {code, params, cost_usd, optional}.
    lines: list[dict[str, Any]] = field(default_factory=list)
    unaffected: dict[str, Any] | None = None
    # False when the change is the unlock itself: the product stays unlocked after ``commit``.
    relock: bool = True
    # 确认并同步 of a change whose follow-up is not a rerun of what it made stale (M3: editing a
    # locked asset draws new candidates of it): returns the job ids it started.
    rerun: Callable[[], Awaitable[list[str]]] | None = None
    # What it makes 待更新 per step when no product it adopts says so (M4: the output spec).
    stale: dict[str, int] = field(default_factory=dict)
