"""Reading and editing assets (SPEC 9.1 ``/series/{id}/assets``, ``/assets/{id}``,
``/episodes/{id}/assets/…``).

The ``asset`` and ``asset_use`` tables mirror the adopted ``asset_list`` versions of the series'
episodes (``materialize``). Mirroring only adds: an asset another episode uses is never retired.
Each asset owns one product, whose versions are its candidates:
- characters, scenes and props: ``ref_image`` (component ``img``);
- on-screen text: ``text_image`` (``text``);
- voices: ``voice`` (``voice``).

What the user sets lives on that product, not on the asset: the description is the prompt's
intent layer, and the text's characters and lettering and the voice's source are its settings.
A new analysis therefore never overwrites them; it only flags that the script now describes
the asset differently (``seed_changed``).

The status is worked out from the product: locked once locked, choosing once it has a version,
not generated before.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlmodel import col, delete, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from drama_series_agent.assets import ops
from drama_series_agent.assets.schema import (
    AssetOut,
    AssetPatch,
    AssetSceneOut,
    MatrixAssetOut,
    MatrixCellOut,
    MatrixOut,
    MatrixSceneOut,
    MessageOut,
    TextOut,
    VoiceLineOut,
    VoiceOut,
)
from drama_series_agent.core.db import Database
from drama_series_agent.core.models_db import (
    Asset,
    AssetUse,
    Episode,
    Job,
    Product,
    ProductVersion,
    Scene,
    ScriptLine,
    utcnow,
)
from drama_series_agent.episodes.service import scene_counts
from drama_series_agent.pipeline.components.assets import ASSET_LIST_SLOT, asset_list_product
from drama_series_agent.pipeline.errors import PipelineError
from drama_series_agent.pipeline.products import ProductService
from drama_series_agent.pipeline.runs import RunService

KIND_ORDER = {k: i for i, k in enumerate(ops.KINDS)}
VOICE_LINES = 2  # script lines shown to audition a voice with


async def asset_product(session: AsyncSession, asset_id: str) -> Product | None:
    query = select(Product).where(Product.owner_type == "asset", Product.owner_id == asset_id)
    return (await session.exec(query)).first()


async def materialize(session: AsyncSession, product: Product, version: ProductVersion) -> None:
    """Mirror an episode's adopted asset list: upsert its assets (never retiring others), give
    each new one its product, and replace the episode's appearances."""
    episode_id, series_id = product.owner_id, product.series_id
    rows = {
        a.id: a for a in (await session.exec(select(Asset).where(Asset.series_id == series_id)))
    }
    now = utcnow()
    for order, item in enumerate(ops.assets_of(version.payload_json)):
        row = rows.get(item["id"])
        made = row is not None and await _has_versions(session, row.id)
        if row is None:
            row = Asset(id=item["id"], series_id=series_id, kind=item["kind"], name=item["name"])
        old = dict(row.seed_json or {})
        seed = {
            "key": item.get("key"),
            "description": item.get("description") or "",
            "text": item.get("text"),
            "note": item.get("note"),
            "order": old.get("order", order) if row.id in rows else order,
        }
        # Already made from another description: say so, never overwrite what the user has.
        changed = bool(old.get("changed")) or (
            made and old.get("description") != seed["description"]
        )
        row.kind, row.name, row.bible_id = item["kind"], item["name"], item.get("bible_id")
        row.seed_json = {**seed, "changed": changed}
        row.retired = False
        row.updated_at = now
        session.add(row)
        if await asset_product(session, row.id) is None:
            session.add(
                Product(
                    series_id=series_id,
                    owner_type="asset",
                    owner_id=row.id,
                    slot=ops.slot_of(row.kind),
                    component_id=ops.component_of(row.kind),
                )
            )
    await session.exec(delete(AssetUse).where(col(AssetUse.episode_id) == episode_id))
    for item in ops.assets_of(version.payload_json):
        for use in item.get("uses") or []:
            session.add(
                AssetUse(
                    series_id=series_id,
                    asset_id=item["id"],
                    episode_id=episode_id,
                    scene_id=str(use["scene_id"]),
                    version_id=version.id,
                    line_ids_json=list(use.get("line_ids") or []),
                )
            )


async def _has_versions(session: AsyncSession, asset_id: str) -> bool:
    p = await asset_product(session, asset_id)
    if p is None:
        return False
    n = (
        await session.exec(
            select(func.count())
            .select_from(ProductVersion)
            .where(ProductVersion.product_id == p.id)
        )
    ).one()
    return bool(n)


class AssetService:
    def __init__(self, db: Database, products: ProductService, runs: RunService) -> None:
        self._db = db
        self._products = products
        self._runs = runs

    # ------------------------------------------------------------------ reads

    async def list_assets(self, series_id: str, episode_id: str | None = None) -> list[AssetOut]:
        """The series' assets, characters first; ``scenes`` and the source are about
        ``episode_id`` when given."""
        async with self._db.session() as session:
            assets = list(
                (
                    await session.exec(
                        select(Asset).where(
                            Asset.series_id == series_id, col(Asset.retired).is_(False)
                        )
                    )
                ).all()
            )
            return await self._out(session, series_id, assets, episode_id)

    async def get(self, asset_id: str, episode_id: str | None = None) -> AssetOut:
        async with self._db.session() as session:
            asset = await self._require(session, asset_id)
            return (await self._out(session, asset.series_id, [asset], episode_id))[0]

    async def matrix(self, episode_id: str) -> MatrixOut:
        async with self._db.session() as session:
            episode = await session.get(Episode, episode_id)
            if episode is None:
                raise PipelineError(404, "episode_not_found", id=episode_id)
            numbers = await _scene_numbers(session, episode.series_id)
            scenes = list(
                (
                    await session.exec(
                        select(Scene)
                        .where(Scene.episode_id == episode_id, col(Scene.retired).is_(False))
                        .order_by(col(Scene.idx))
                    )
                ).all()
            )
            uses = list(
                (
                    await session.exec(select(AssetUse).where(AssetUse.episode_id == episode_id))
                ).all()
            )
            ids = {u.asset_id for u in uses}
            assets = [
                a
                for a in (await session.exec(select(Asset).where(col(Asset.id).in_(ids)))).all()
                if not a.retired
            ]
        assets.sort(key=lambda a: (KIND_ORDER.get(a.kind, 9), a.created_at, a.id))
        live = {s.id for s in scenes}
        return MatrixOut(
            episode_id=episode_id,
            scenes=[
                MatrixSceneOut(id=s.id, number=numbers.get(s.id, s.idx), heading=s.heading)
                for s in scenes
            ],
            assets=[MatrixAssetOut.model_validate(a, from_attributes=True) for a in assets],
            cells=[
                MatrixCellOut(asset_id=u.asset_id, scene_id=u.scene_id, line_ids=u.line_ids_json)
                for u in uses
                if u.scene_id in live
            ],
        )

    # ------------------------------------------------------------------ writes

    async def patch(self, asset_id: str, body: AssetPatch) -> AssetOut:
        """改描述 (the prompt's intent layer), 「选这个」, the text's characters and lettering,
        the voice's source. A locked asset refuses (409 ``product_locked``): changing it goes
        through the impact preview."""
        async with self._db.session() as session:
            asset = await self._require(session, asset_id)
            product = await asset_product(session, asset_id)
            if product is None:
                raise PipelineError(409, "product_missing", id=asset_id)
            if product.locked_hash and (body.intent is not None or body.text or body.voice):
                raise PipelineError(409, "product_locked", id=product.id)
            current = product.current_version_id
            text_now = dict(
                (product.settings_json or {}).get("text") or asset.seed_json.get("text") or {}
            )
        if body.intent is not None:
            await self._runs.save_prompt(product.id, body.intent, None)
            async with self._db.session() as session:
                row = await self._require(session, asset_id)
                row.seed_json = {**row.seed_json, "changed": False}
                row.updated_at = utcnow()
                session.add(row)
                await session.commit()
        if body.pick is not None:
            if current is None:
                raise PipelineError(409, "nothing_to_pick", id=asset_id)
            await self._products.set_pick(product.id, current, body.pick)
        if body.text is not None:
            changes = body.text.model_dump(exclude_none=True)
            await self._products.update_settings(product.id, {"text": {**text_now, **changes}})
        if body.voice is not None:
            await self._products.update_settings(product.id, {"voice": body.voice.model_dump()})
        return await self.get(asset_id)

    async def analyze(self, episode_id: str) -> Job:
        """「重新分析剧本」: run the episode's 素材分析 (every run is adopted; the list only
        adds)."""
        async with self._db.session() as session:
            episode = await session.get(Episode, episode_id)
            if episode is None:
                raise PipelineError(404, "episode_not_found", id=episode_id)
            product = await asset_list_product(session, episode_id)
        if product is None:
            product = await self._products.ensure(
                series_id=episode.series_id,
                owner_type="episode",
                owner_id=episode_id,
                slot=ASSET_LIST_SLOT,
                component_id="assets",
            )
        return await self._runs.start(product.id, "run")

    # ------------------------------------------------------------------ internals

    async def _require(self, session: AsyncSession, asset_id: str) -> Asset:
        asset = await session.get(Asset, asset_id)
        if asset is None or asset.retired:
            raise PipelineError(404, "asset_not_found", id=asset_id)
        return asset

    async def _out(
        self,
        session: AsyncSession,
        series_id: str,
        assets: Sequence[Asset],
        episode_id: str | None,
    ) -> list[AssetOut]:
        ids = [a.id for a in assets]
        products = {
            p.owner_id: p
            for p in (
                await session.exec(
                    select(Product).where(
                        Product.owner_type == "asset", col(Product.owner_id).in_(ids)
                    )
                )
            ).all()
        }
        made = set(
            (
                await session.exec(
                    select(ProductVersion.product_id).where(
                        col(ProductVersion.product_id).in_([p.id for p in products.values()])
                    )
                )
            ).all()
        )
        uses: dict[str, list[AssetUse]] = {}
        for u in (
            await session.exec(select(AssetUse).where(col(AssetUse.asset_id).in_(ids)))
        ).all():
            uses.setdefault(u.asset_id, []).append(u)
        numbers = await _scene_numbers(session, series_id)
        episodes = {
            e.id: e.idx
            for e in (await session.exec(select(Episode).where(Episode.series_id == series_id)))
        }
        line_ids = {i for us in uses.values() for u in us for i in u.line_ids_json}
        lines = {
            r.id: r
            for r in (
                await session.exec(select(ScriptLine).where(col(ScriptLine.id).in_(line_ids)))
            ).all()
        }

        def at(u: AssetUse) -> tuple[int, int, int]:
            first = lines.get(u.line_ids_json[0]) if u.line_ids_json else None
            return (
                episodes.get(u.episode_id, 0),
                numbers.get(u.scene_id, 0),
                first.idx if first is not None else 0,
            )

        ranked: list[tuple[tuple[Any, ...], AssetOut]] = []
        for a in assets:
            p = products.get(a.id)
            if p is None:
                continue
            mine = sorted(uses.get(a.id, []), key=at)
            here = [u for u in mine if episode_id is None or u.episode_id == episode_id]
            settings = p.settings_json or {}
            seed = a.seed_json or {}
            intent = str((p.prompt_json or {}).get("intent") or seed.get("description") or "")
            # Each kind in order of first appearance; unused ones last, in the list's order.
            first = at(mine[0]) if mine else (10**9, 0, 0)
            key = (KIND_ORDER.get(a.kind, 9), first, int(seed.get("order") or 0))
            ranked.append(
                (
                    key,
                    AssetOut(
                        id=a.id,
                        series_id=a.series_id,
                        kind=a.kind,
                        name=a.name,
                        intent=intent,
                        source=_source(a, here, mine, numbers, episodes, lines),
                        shots=[],
                        scenes=[
                            AssetSceneOut(
                                scene_id=u.scene_id,
                                episode_id=u.episode_id,
                                number=numbers.get(u.scene_id, 0),
                                line_ids=list(u.line_ids_json),
                            )
                            for u in here
                        ],
                        product_id=p.id,
                        status=(
                            "locked"
                            if p.locked_hash
                            else "choosing"
                            if p.id in made
                            else "not_generated"
                        ),
                        pick=int((p.pick_json or {}).get("idx") or 0),
                        text=_text(a, settings),
                        voice=_voice(a, settings, here or mine, lines),
                        note=seed.get("note"),
                        seed_changed=bool(seed.get("changed")),
                    ),
                )
            )
        ranked.sort(key=lambda r: r[0])
        return [o for _, o in ranked]


async def _scene_numbers(session: AsyncSession, series_id: str) -> dict[str, int]:
    """Scene id → its series-wide 场号 (as the script page numbers them)."""
    offsets: dict[str, int] = {}
    first = 1
    for e in await scene_counts(session, series_id):
        offsets[e["id"]] = first
        first += int(e["scene_count"] or 0)
    out: dict[str, int] = {}
    rows = (await session.exec(select(Scene).where(Scene.series_id == series_id))).all()
    for s in rows:
        out[s.id] = offsets.get(s.episode_id, 1) + s.idx - 1
    return out


def _source(
    asset: Asset,
    here: Sequence[AssetUse],
    everywhere: Sequence[AssetUse],
    numbers: dict[str, int],
    episodes: dict[str, int],
    lines: dict[str, ScriptLine],
) -> MessageOut:
    """Where the script first has it: ``components:asset.source.<code>``."""
    note = (asset.seed_json or {}).get("note")
    if not here:
        if everywhere:
            u = everywhere[0]
            where = {"episode": episodes.get(u.episode_id, 0), "scene": numbers.get(u.scene_id, 0)}
            return MessageOut(code="episode_scene", params=where)
        return MessageOut(code="note", params={"note": note or ""})
    if asset.kind == "voice":
        count = sum(len(u.line_ids_json) for u in here)
        return MessageOut(code="dialogue_count", params={"count": count})
    u = here[0]
    scene = numbers.get(u.scene_id, 0)
    first = lines.get(u.line_ids_json[0]) if u.line_ids_json else None
    if asset.kind == "scene" or first is None:
        return MessageOut(code="scene_heading", params={"scene": scene})
    params: dict[str, Any] = {"scene": scene, "line": first.idx}
    if note:
        return MessageOut(code="script_line_note", params={**params, "note": note})
    return MessageOut(code="script_line", params=params)


def _text(asset: Asset, settings: dict[str, Any]) -> TextOut | None:
    if asset.kind != "text":
        return None
    seed = (asset.seed_json or {}).get("text") or {}
    merged = {
        "exact": "",
        "method": "composite",
        "style": "printed",
        **seed,
        **(settings.get("text") or {}),
    }
    return TextOut.model_validate(merged)


def _voice(
    asset: Asset,
    settings: dict[str, Any],
    uses: Sequence[AssetUse],
    lines: dict[str, ScriptLine],
) -> VoiceOut | None:
    if asset.kind != "voice":
        return None
    picked = []
    for u in uses:
        for i in u.line_ids_json:
            line = lines.get(i)
            if line is not None and not line.retired:
                picked.append(VoiceLineOut(text=line.text, tone=line.tone or ""))
    method = (settings.get("voice") or {}).get("method") or "design"
    return VoiceOut(method=method, lines=picked[:VOICE_LINES])
