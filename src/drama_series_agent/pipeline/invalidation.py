"""Staleness (SPEC 4.2; PLAN 失效传播): a product is stale when a slice it was built from changed.

Each ``dependency`` row stores the hash of one upstream slice at build time (an episode's
beats, the bible entries used …). The current hash is recomputed from the upstream product's
adopted version, so nothing stores a "stale" flag and undoing a change makes the product fresh
again. Only direct dependencies count here; what lies further down is listed by the impact
preview.

A slot whose slices are not just keys of the payload registers a slicer (``slicer()``); the
default reads ``payload[slice]`` (``""`` = the whole payload).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from typing import Any

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from drama_series_agent.core.models_db import Dependency, Product, ProductVersion
from drama_series_agent.pipeline.drafts import DependencyDraft
from drama_series_agent.pipeline.hashing import hash_json

# Fields that only change how something is shown or rerun, never what downstream builds from
# (``frozen`` only keeps a bible entry as it is when extraction runs again).
DISPLAY_KEYS = frozenset({"idx", "edited", "duration_s", "overlay_shot", "frozen"})

Slicer = Callable[[AsyncSession, Product, ProductVersion, str], Awaitable[Any]]


def strip_display(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: strip_display(v) for k, v in value.items() if k not in DISPLAY_KEYS}
    if isinstance(value, list):
        return [strip_display(v) for v in value]
    return value


def slice_hash(value: Any) -> str:
    return hash_json(strip_display(value))


async def _default_slicer(
    session: AsyncSession, product: Product, version: ProductVersion, name: str
) -> Any:
    return version.payload_json if name == "" else version.payload_json.get(name)


class Invalidation:
    def __init__(self) -> None:
        self._slicers: dict[str, Slicer] = {}

    def slicer(self, slot: str, fn: Slicer) -> None:
        self._slicers[slot] = fn

    async def current_hash(
        self, session: AsyncSession, upstream_product_id: str, name: str = ""
    ) -> str | None:
        """Hash of a slice of the upstream's adopted version; None when nothing is adopted."""
        product = await session.get(Product, upstream_product_id)
        if product is None or product.adopted_version_id is None:
            return None
        version = await session.get(ProductVersion, product.adopted_version_id)
        if version is None:
            return None
        fn = self._slicers.get(product.slot, _default_slicer)
        return slice_hash(await fn(session, product, version, name))

    async def dependency(
        self, session: AsyncSession, upstream_product_id: str, name: str = ""
    ) -> DependencyDraft:
        """The dependency row a component writes for a slice it reads (raises if not adopted)."""
        h = await self.current_hash(session, upstream_product_id, name)
        if h is None:
            raise LookupError(f"upstream {upstream_product_id} has nothing adopted")
        return DependencyDraft(upstream_product_id=upstream_product_id, upstream_hash=h, slice=name)

    async def stale_ids(self, session: AsyncSession, products: Iterable[Product]) -> set[str]:
        """Products whose adopted (else current) version was built from slices that changed."""
        by_version = {
            v: p.id
            for p in products
            if (v := p.adopted_version_id or p.current_version_id) is not None
        }
        if not by_version:
            return set()
        rows = (
            await session.exec(
                select(Dependency).where(col(Dependency.version_id).in_(list(by_version)))
            )
        ).all()
        hashes: dict[tuple[str, str], str | None] = {}
        stale: set[str] = set()
        for dep in rows:
            key = (dep.upstream_product_id, dep.slice)
            if key not in hashes:
                hashes[key] = await self.current_hash(session, *key)
            if hashes[key] != dep.upstream_hash:
                stale.add(by_version[dep.version_id])
        return stale
