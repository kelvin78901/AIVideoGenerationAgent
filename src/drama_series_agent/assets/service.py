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

**Locking** (「锁定为参考」, ``lock``) turns the picked candidate into a ``pick`` version and
locks it (``ProductService.lock_pick``), and in the same transaction writes the asset's own
``gate_decision`` (gate ``assets``, scope the asset id) with the hash of that file. A character
then gets its side, back and four expressions drawn (``views``). **Unlocking** goes through the
impact preview (kind ``asset_unlock``): it changes no content, so the preview lists what uses
the locked picture straight from the dependency graph. **Uploading** a picture adds a version
with that one candidate (``origin: upload``), to lock or to start an API final from.

**On-screen text** is checked by OCR (``pipeline/components/text.py``): a candidate OCR read
differently from what it must say locks only with ``force`` (409 ``ocr_mismatch``); one not
checked (no OCR on this machine) locks as usual. An uploaded picture is read too.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta
from typing import Any

from loguru import logger
from sqlmodel import col, delete, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from drama_series_agent.assets import ops
from drama_series_agent.assets.schema import (
    AssetLockIn,
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
from drama_series_agent.core.events import EventBus, EventType
from drama_series_agent.core.models_db import (
    Asset,
    AssetUse,
    Episode,
    GateDecision,
    Job,
    Product,
    ProductVersion,
    Scene,
    ScriptLine,
    utcnow,
)
from drama_series_agent.core.storage import BlobStore
from drama_series_agent.episodes.schema import StepProgressOut
from drama_series_agent.episodes.service import (
    EpisodeService,
    gate_confirmed,
    latest_gate,
    scene_numbers,
)
from drama_series_agent.media.image import MAX_UPLOAD_BYTES, NotAnImage, image_info
from drama_series_agent.pipeline.components.assets import ASSET_LIST_SLOT, asset_list_product
from drama_series_agent.pipeline.components.dub import LINE_AUDIO_SLOT
from drama_series_agent.pipeline.components.text import (
    TEXT_IMAGE_SLOT,
    TextComponent,
    text_settings,
)
from drama_series_agent.pipeline.components.views import REF_VIEWS_SLOT, ViewsComponent
from drama_series_agent.pipeline.components.voice import VOICE_SLOT
from drama_series_agent.pipeline.drafts import PlannedChange, VersionDraft, file_entry
from drama_series_agent.pipeline.errors import PipelineError
from drama_series_agent.pipeline.gates import GateService
from drama_series_agent.pipeline.impact import ImpactService, series_graph
from drama_series_agent.pipeline.invalidation import Invalidation
from drama_series_agent.pipeline.products import ProductService
from drama_series_agent.pipeline.runs import RunService

KIND_ORDER = {k: i for i, k in enumerate(ops.KINDS)}
VOICE_LINES = 2  # script lines shown to audition a voice with
ASSET_GATE = "assets"
# Slots a picture can be uploaded to as a candidate.
UPLOAD_SLOTS = ("ref_image", TEXT_IMAGE_SLOT)
# The product each asset owns (its views are another one, ``ref_views``).
ASSET_SLOTS = ("ref_image", TEXT_IMAGE_SLOT, VOICE_SLOT)


async def asset_product(session: AsyncSession, asset_id: str) -> Product | None:
    query = select(Product).where(
        Product.owner_type == "asset",
        Product.owner_id == asset_id,
        col(Product.slot).in_(ASSET_SLOTS),
    )
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


async def record_asset_gate(
    session: AsyncSession, invalidation: Invalidation, product: Product, action: str
) -> None:
    """The asset's own ``gate_decision`` (scope: the asset): on ``confirm`` the hash of what is
    locked, which is the file's (media slicer). Written in the caller's transaction."""
    hashes: dict[str, str] = {}
    if action == "confirm":
        h = await invalidation.current_hash(session, product.id, "")
        if h:
            hashes[product.id] = h
    last = await latest_gate(session, ASSET_GATE, product.owner_id)
    at = utcnow()
    if last is not None and at <= last.decided_at:  # keep them in order
        at = last.decided_at + timedelta(microseconds=1)
    session.add(
        GateDecision(
            series_id=product.series_id,
            gate=ASSET_GATE,
            scope_id=product.owner_id,
            action=action,
            product_hashes_json=hashes,
            decided_at=at,
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
    def __init__(
        self,
        db: Database,
        products: ProductService,
        runs: RunService,
        *,
        bus: EventBus,
        store: BlobStore,
        invalidation: Invalidation,
        text: TextComponent | None = None,
    ) -> None:
        self._db = db
        self._products = products
        self._runs = runs
        self._bus = bus
        self._store = store
        self._invalidation = invalidation
        self._text = text  # OCR of uploaded on-screen text
        self._gates: GateService | None = None  # set by ``register``

    def register(self, impact: ImpactService, gates: GateService, episodes: EpisodeService) -> None:
        """The changes to assets the impact preview knows (unlocking), the episode's assets
        gate (the assets it uses) and its 素材 badge."""

        async def asset_unlock(target: str, patch: dict[str, Any]) -> PlannedChange:
            return await self.plan_unlock(target)

        async def asset_edit(target: str, patch: dict[str, Any]) -> PlannedChange:
            return await self.plan_edit(target, AssetPatch.model_validate(patch))

        impact.kind("asset_unlock", asset_unlock)
        impact.kind("asset_edit", asset_edit)
        gates.members(ASSET_GATE, self.episode_assets)
        episodes.counters["assets"] = self.badge
        self._gates = gates

    async def episode_assets(
        self, session: AsyncSession, episode_id: str
    ) -> list[tuple[str, Product]]:
        """The assets an episode uses (its 出场), in the analysis' order, with their products."""
        ids = set(
            (
                await session.exec(
                    select(AssetUse.asset_id).where(AssetUse.episode_id == episode_id)
                )
            ).all()
        )
        assets = [
            a
            for a in (await session.exec(select(Asset).where(col(Asset.id).in_(ids)))).all()
            if not a.retired
        ]
        assets.sort(key=lambda a: (int((a.seed_json or {}).get("order", 0)), a.id))
        products = {
            p.owner_id: p
            for p in (
                await session.exec(
                    select(Product).where(
                        Product.owner_type == "asset",
                        col(Product.owner_id).in_(ids),
                        col(Product.slot).in_(ASSET_SLOTS),
                    )
                )
            ).all()
        }
        return [(a.name, products[a.id]) for a in assets if a.id in products]

    async def badge(self, session: AsyncSession, episode_id: str) -> StepProgressOut:
        """素材 n / m: the episode's assets locked; 待更新: those and its lines' dubbing."""
        members = [p for _, p in await self.episode_assets(session, episode_id)]
        line_ids = list(
            (
                await session.exec(
                    select(ScriptLine.id).where(
                        ScriptLine.episode_id == episode_id, col(ScriptLine.retired).is_(False)
                    )
                )
            ).all()
        )
        dubs = list(
            (
                await session.exec(
                    select(Product).where(
                        Product.owner_type == "line",
                        col(Product.owner_id).in_(line_ids),
                        Product.slot == LINE_AUDIO_SLOT,
                    )
                )
            ).all()
        )
        stale = await self._invalidation.stale_ids(session, [*members, *dubs])
        confirmed = await gate_confirmed(session, ASSET_GATE, episode_id)
        state = "confirmed" if confirmed else "in_progress" if members else "not_started"
        return StepProgressOut(
            state=state,
            done=sum(1 for p in members if p.locked_hash),
            total=len(members),
            stale=len(stale),
        )

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
            numbers = await scene_numbers(session, episode.series_id)
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
        # By kind, then as the analysis listed them (rows made in one go share a timestamp).
        assets.sort(
            key=lambda a: (
                KIND_ORDER.get(a.kind, 9),
                int((a.seed_json or {}).get("order") or 0),
                a.id,
            )
        )
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
            await self._require(session, asset_id)
            product = await asset_product(session, asset_id)
            if product is None:
                raise PipelineError(409, "product_missing", id=asset_id)
            if product.locked_hash and (body.intent is not None or body.text or body.voice):
                raise PipelineError(409, "product_locked", id=product.id)
        await self._write_patch(asset_id, body)
        return await self.get(asset_id)

    async def _write_patch(self, asset_id: str, body: AssetPatch) -> None:
        async with self._db.session() as session:
            asset = await self._require(session, asset_id)
            product = await asset_product(session, asset_id)
            assert product is not None
            current = product.current_version_id
            text_now = text_settings(asset, product.settings_json) if asset.kind == "text" else {}
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

    async def lock(self, asset_id: str, body: AssetLockIn | None = None) -> AssetOut:
        """「锁定为参考」: the picked candidate of the version on screen (or of ``body``'s), with
        the asset's gate decision; then a character's views are drawn. On-screen text OCR read
        differently takes ``force``. A version without candidates (a voice's final) is locked
        as a whole; a voice's auditions cannot be (409 ``voice_needs_final``)."""
        body = body or AssetLockIn()
        async with self._db.session() as session:
            asset = await self._require(session, asset_id)
            product = await asset_product(session, asset_id)
            if product is None:
                raise PipelineError(409, "product_missing", id=asset_id)
            if product.locked_hash:
                raise PipelineError(409, "product_locked", id=product.id)
            version_id = body.version_id or product.current_version_id
            if version_id is None:
                raise PipelineError(409, "nothing_to_lock", id=asset_id)
            pick = product.pick_json or {}
            idx: int | None = body.idx
            if idx is None:
                idx = int(pick.get("idx") or 0) if pick.get("version_id") == version_id else 0
            kind = asset.kind
            v = await session.get(ProductVersion, version_id)
            has_candidates = v is not None and any(
                f.get("role") == "candidate" for f in v.files_json
            )
            if product.slot == VOICE_SLOT and has_candidates:
                raise PipelineError(409, "voice_needs_final", id=asset_id)
            if v is not None and v.product_id == product.id and not has_candidates:
                idx = None
            if product.slot == TEXT_IMAGE_SLOT and not body.force and idx is not None:
                await _refuse_ocr_mismatch(session, product, version_id, idx)

        async def record(session: AsyncSession, p: Product, v: ProductVersion) -> None:
            await record_asset_gate(session, self._invalidation, p, "confirm")

        await self._products.lock_pick(product.id, version_id, idx, record=record)
        await self._gate_updated(product, "confirm")
        if kind == "character":
            await self.draw_views(asset_id)
        return await self.get(asset_id)

    async def upload(self, asset_id: str, filename: str, data: bytes) -> AssetOut:
        """「上传参考图」: the picture becomes a version with that one candidate, picked."""
        if len(data) > MAX_UPLOAD_BYTES:
            raise PipelineError(413, "file_too_large", limit=MAX_UPLOAD_BYTES)
        try:
            info = image_info(data)
        except NotAnImage:
            raise PipelineError(422, "not_an_image", filename=filename) from None
        async with self._db.session() as session:
            asset = await self._require(session, asset_id)
            product = await asset_product(session, asset_id)
            if product is None or product.slot not in UPLOAD_SLOTS:
                raise PipelineError(422, "upload_not_supported", kind=asset.kind)
            if product.locked_hash:
                raise PipelineError(409, "product_locked", id=product.id)
            intent = (product.prompt_json or {}).get("intent") or asset.seed_json.get("description")
        sha = self._store.put_bytes(data)
        name = filename[:200]
        payload: dict[str, Any] = {"candidates": [{}]}
        if product.slot == TEXT_IMAGE_SLOT and self._text is not None:
            checked, text = await self._text.check_upload(asset, product, sha)
            payload = {"candidates": [checked], "text": text}
        draft = VersionDraft(
            payload=payload,
            files=[file_entry("candidate", sha, info.mime, w=info.w, h=info.h, idx=0)],
            intent=str(intent or ""),
            params={"filename": name},
            note=name or None,
        )
        v = await self._products.append(product.id, draft, origin="upload", adopt=False)
        await self._products.set_pick(product.id, v.id, 0)
        return await self.get(asset_id)

    async def draw_views(self, asset_id: str) -> Job | None:
        """补视图 of a locked character, unless the views already follow this picture."""
        async with self._db.session() as session:
            asset = await self._require(session, asset_id)
        p = await self._products.ensure(
            series_id=asset.series_id,
            owner_type="asset",
            owner_id=asset.id,
            slot=REF_VIEWS_SLOT,
            component_id=ViewsComponent.id,
        )
        async with self._db.session() as session:
            stale = await self._invalidation.stale_ids(session, [p])
        if p.adopted_version_id and p.id not in stale:
            return None
        try:
            return await self._runs.start(p.id, "run")
        except PipelineError as exc:  # already drawing, or no model for it here
            logger.warning("views of {} not started: {}", asset_id, exc.code)
            return None

    async def plan_unlock(self, asset_id: str) -> PlannedChange:
        """解锁 (kind ``asset_unlock``): nothing changes until another picture is locked, so the
        lines are what uses the locked one (from the dependency graph)."""
        async with self._db.session() as session:
            asset = await self._require(session, asset_id)
            product = await asset_product(session, asset_id)
            if product is None or not product.locked_hash:
                raise PipelineError(409, "not_locked", id=asset_id)
            lines = await self._uses(session, asset, product)
        locked_hash = product.locked_hash

        async def commit() -> None:
            await self._products.unlock(product.id)
            async with self._db.session() as session:
                p = await session.get(Product, product.id)
                assert p is not None
                await record_asset_gate(session, self._invalidation, p, "reopen")
                await session.commit()
            await self._gate_updated(product, "reopen")
            # The episodes that use it were confirmed with it locked.
            if self._gates is not None:
                await self._gates.reopen_using(ASSET_GATE, product.id)

        return PlannedChange(
            product_id=product.id,
            series_id=product.series_id,
            base_version_id=product.adopted_version_id,
            commit=commit,
            content=locked_hash,
            lines=lines,
            unaffected={"code": "unlock_keeps_ref", "params": {}},
            relock=False,
        )

    async def plan_edit(self, asset_id: str, body: AssetPatch) -> PlannedChange:
        """改一条已锁定的素材 (kind ``asset_edit``: its description, on-screen text settings or
        voice source). The locked reference stays until the user locks a new one, so the lines
        are the redraw (确认并同步 makes new candidates), what follows a new lock, and the scenes
        it is in."""
        if body.pick is not None:
            raise PipelineError(422, "invalid_patch", kind="asset_edit", issues="pick")
        async with self._db.session() as session:
            asset = await self._require(session, asset_id)
            product = await asset_product(session, asset_id)
            if product is None or not product.locked_hash:
                raise PipelineError(409, "not_locked", id=asset_id)
            uses = await self._uses(session, asset, product)
            numbers = await scene_numbers(session, product.series_id)
            scenes = sorted(
                {
                    numbers.get(u.scene_id, 0)
                    for u in (
                        await session.exec(select(AssetUse).where(AssetUse.asset_id == asset_id))
                    ).all()
                }
            )
        _, est = await self._runs.describe(product)
        lines: list[dict[str, Any]] = [
            {
                "code": "asset_redraw",
                "params": {"name": asset.name, "kind": asset.kind},
                # None when free (a local draft), as the impact's other lines.
                "cost_usd": est.cost_usd if est is not None and est.cost_usd else None,
                "optional": False,
            },
            *uses,
        ]
        if scenes:
            lines.append(
                {
                    "code": "asset_in_scenes",
                    "params": {"scenes": "、".join(str(n) for n in scenes), "count": len(scenes)},
                    "cost_usd": None,
                    "optional": False,
                }
            )

        async def commit() -> None:
            await self._write_patch(asset_id, body)

        async def redraw() -> list[str]:
            return [(await self._runs.start(product.id, "rerun")).id]

        return PlannedChange(
            product_id=product.id,
            series_id=product.series_id,
            base_version_id=product.adopted_version_id,
            commit=commit,
            content=body.model_dump(exclude_none=True),
            lines=lines,
            unaffected={"code": "edit_keeps_ref", "params": {"name": asset.name}},
            rerun=redraw,
        )

    # ------------------------------------------------------------------ internals

    async def _uses(
        self, session: AsyncSession, asset: Asset, product: Product
    ) -> list[dict[str, Any]]:
        """Impact lines for what reads the locked reference: views, assets drawn from it
        (names), the lines dubbed in a voice (how many)."""
        nodes, edges = await series_graph(session, product.series_id)
        users = sorted({down for down, up, _ in edges if up == product.id})
        owners = {nodes[u].owner_id for u in users if u in nodes}
        names = {
            a.id: a.name
            for a in (await session.exec(select(Asset).where(col(Asset.id).in_(owners))))
        }
        by_slot: dict[str, list[str]] = {}
        for u in users:
            node = nodes.get(u)
            if node is not None:
                by_slot.setdefault(node.slot, []).append(names.get(node.owner_id, node.owner_id))
        lines: list[dict[str, Any]] = []
        for slot, who in by_slot.items():
            params: dict[str, Any] = {"count": len(who), "names": "、".join(who)}
            if slot == REF_VIEWS_SLOT:
                params = {"name": asset.name}
            elif slot == LINE_AUDIO_SLOT:
                params = {"name": asset.name, "count": len(who)}
            lines.append({"code": f"uses_{slot}", "params": params, "cost_usd": None})
        for line in lines:
            line["optional"] = False
        return lines

    async def _gate_updated(self, product: Product, action: str) -> None:
        await self._bus.publish(
            EventType.GATE_UPDATED,
            {
                "gate": ASSET_GATE,
                "scope_id": product.owner_id,
                "series_id": product.series_id,
                "action": action,
            },
        )

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
                        Product.owner_type == "asset",
                        col(Product.owner_id).in_(ids),
                        col(Product.slot).in_(ASSET_SLOTS),
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
        numbers = await scene_numbers(session, series_id)
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
            # 「选这个」 is about the version on screen.
            pick = p.pick_json or {}
            on_screen = pick.get("version_id") == p.current_version_id
            picked = int(pick.get("idx") or 0) if on_screen else 0
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
                        pick=picked,
                        text=_text(a, settings),
                        voice=_voice(a, settings, here or mine, lines),
                        note=seed.get("note"),
                        seed_changed=bool(seed.get("changed")),
                    ),
                )
            )
        ranked.sort(key=lambda r: r[0])
        return [o for _, o in ranked]


async def _refuse_ocr_mismatch(
    session: AsyncSession, product: Product, version_id: str, idx: int
) -> None:
    """409 ``ocr_mismatch`` when OCR read the candidate differently from what it must say."""
    v = await session.get(ProductVersion, version_id)
    if v is None or v.product_id != product.id:
        return  # lock_pick says what is wrong
    candidates = (v.payload_json or {}).get("candidates") or []
    entry = candidates[idx] if 0 <= idx < len(candidates) else {}
    if isinstance(entry, dict) and entry.get("ocr_ok") is False:
        exact = str(((v.payload_json or {}).get("text") or {}).get("exact") or "")
        raise PipelineError(
            409,
            "ocr_mismatch",
            id=product.owner_id,
            idx=idx,
            read=entry.get("ocr") or "",
            exact=exact,
            issue=entry.get("ocr_issue") or "",
        )


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
    return TextOut.model_validate(text_settings(asset, settings))


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
