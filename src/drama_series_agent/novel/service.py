"""Importing and reading a series' novel (SPEC 4.1; 9.1 ``/series/{id}/novel``).

The novel is a product like the others (slot ``novel``, component ``import``): every import
appends a version (origin ``import``) and adopts it. So a re-import replaces the text while the
old one stays in the history, and whatever was built from it turns stale through the slice
hashes (``chapter:<idx>``, see ``novel_slicer``) without storing a flag. A novel locked by its
gate refuses the import (409 ``product_locked``); the impact preview for ``novel_replace``
comes with the gates.
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePath
from typing import Any

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from drama_series_agent.core.db import Database
from drama_series_agent.core.models_db import (
    Chapter,
    NovelSource,
    Product,
    ProductVersion,
    Series,
    utcnow,
)
from drama_series_agent.core.storage import BlobStore
from drama_series_agent.novel.parse import NovelParseError, ParsedNovel, parse_upload
from drama_series_agent.novel.schema import (
    ChapterOut,
    NovelImportOut,
    NovelOut,
    ParagraphOut,
    SourceOut,
    import_out,
)
from drama_series_agent.pipeline.drafts import VersionDraft
from drama_series_agent.pipeline.errors import PipelineError
from drama_series_agent.pipeline.hashing import hash_json
from drama_series_agent.pipeline.products import ProductService

NOVEL_SLOT = "novel"
IMPORT_COMPONENT = "import"
_PARSE_STATUS = {"unsupported_file": 415, "file_too_large": 413}
_TEXT_CACHE = 4


@dataclass(frozen=True)
class FixedIds:
    """The demo seed imports with the ids and times the MSW fixtures use."""

    product_id: str
    version_id: str
    source_id: str  # chapters are ``<source_id>-ch<n>``
    at: datetime


def chapter_hash(text: str, title: str | None, paras: list[list[int]] | tuple[Any, ...]) -> str:
    """What a chapter says: its title and paragraphs, not the blank lines around them."""
    return hash_json({"title": title, "paras": [text[s:e] for s, e in paras]})


async def novel_slicer(
    session: AsyncSession, product: Product, version: ProductVersion, name: str
) -> Any:
    """Slices of the ``novel`` product: ``chapter:<idx>`` is that chapter's title and hash."""
    if name == "":
        return version.payload_json
    kind, _, key = name.partition(":")
    if kind == "chapter":
        for c in version.payload_json.get("chapters", []):
            if str(c.get("idx")) == key:
                return c
    return None


def safe_filename(name: str | None) -> str:
    base = PurePath((name or "").replace("\\", "/")).name.strip()
    return base[:200] or "novel.txt"


class NovelService:
    def __init__(self, db: Database, store: BlobStore, products: ProductService) -> None:
        self._db = db
        self._store = store
        self._products = products
        self._texts: OrderedDict[str, str] = OrderedDict()

    # ------------------------------------------------------------------ import

    async def preview(self, series_id: str, filename: str, data: bytes) -> NovelImportOut:
        """What an import would find (encoding, chapters), without storing anything."""
        await self._require_series(series_id)
        name = safe_filename(filename)
        return import_out(await self._parse(name, data), name, dry_run=True)

    async def import_novel(
        self,
        series_id: str,
        filename: str,
        data: bytes,
        *,
        rights_confirmed: bool,
        fixed: FixedIds | None = None,
    ) -> NovelImportOut:
        if not rights_confirmed:
            raise PipelineError(422, "rights_not_confirmed")
        await self._require_series(series_id)
        name = safe_filename(filename)
        parsed = await self._parse(name, data)
        product = await self._products.ensure(
            series_id=series_id,
            owner_type="series",
            owner_id=series_id,
            slot=NOVEL_SLOT,
            component_id=IMPORT_COMPONENT,
            product_id=fixed.product_id if fixed else None,
        )
        if product.locked_hash:
            raise PipelineError(409, "product_locked", id=product.id)
        text_sha = await asyncio.to_thread(self._store.put_bytes, parsed.text.encode("utf-8"))
        original_sha = await asyncio.to_thread(self._store.put_bytes, data)

        async with self._db.session() as session:
            current = await self._adopted_source(session, product)
            if current is not None and current.sha256 == text_sha:
                ids = [c.id for c in await self._chapters(session, current.id)]
                return import_out(
                    parsed, name, dry_run=False, source_id=current.id, chapter_ids=ids,
                    unchanged=True,
                )  # fmt: skip
            at = fixed.at if fixed else utcnow()
            source = NovelSource(
                series_id=series_id,
                filename=name,
                sha256=text_sha,
                original_sha256=original_sha,
                encoding=parsed.encoding,
                split_by=parsed.split_by,
                chars=parsed.chars,
                rights_confirmed_at=at,
                created_at=at,
            )
            if fixed:
                source.id = fixed.source_id
            session.add(source)
            await session.flush()
            rows = []
            for c in parsed.chapters:
                row = Chapter(
                    source_id=source.id,
                    idx=c.idx,
                    title=c.title,
                    start=c.start,
                    end=c.end,
                    para_start=c.para_start,
                    paras_json=[[s, e] for s, e in c.paras],
                )
                if fixed:
                    row.id = f"{fixed.source_id}-ch{c.idx + 1}"
                session.add(row)
                rows.append(row)
            await session.commit()
            source_id, chapter_ids = source.id, [r.id for r in rows]

        text = parsed.text
        payload = {
            "source_id": source_id,
            "filename": name,
            "sha256": text_sha,
            "chapters": [
                {"idx": c.idx, "title": c.title, "hash": chapter_hash(text, c.title, c.paras)}
                for c in parsed.chapters
            ],
        }
        draft = VersionDraft(
            payload=payload,
            note=name,
            id=fixed.version_id if fixed else None,
            created_at=fixed.at if fixed else None,
        )
        await self._products.append(product.id, draft, origin="import", adopt=True)
        return import_out(parsed, name, dry_run=False, source_id=source_id, chapter_ids=chapter_ids)

    # ------------------------------------------------------------------ read

    async def get(self, series_id: str, chapter: int | None = None) -> NovelOut:
        """The adopted source's chapters and one chapter's paragraphs (the first by default)."""
        async with self._db.session() as session:
            await self._require_series(series_id, session)
            product = await self._product(session, series_id)
            source = await self._adopted_source(session, product) if product else None
            if source is None:
                return NovelOut(
                    series_id=series_id, source=None, chapters=[], chapter=None, paragraphs=[]
                )
            chapters = await self._chapters(session, source.id)
        idx = chapter or 0
        if idx >= len(chapters):
            raise PipelineError(404, "chapter_not_found", idx=idx)
        text = await self.text(source.sha256)
        shown = chapters[idx]
        return NovelOut(
            series_id=series_id,
            source=SourceOut(
                id=source.id,
                filename=source.filename,
                sha256=source.sha256,
                encoding=source.encoding,
                split_by=source.split_by,
                chars=source.chars,
                rights_confirmed_at=source.rights_confirmed_at,
                imported_at=source.created_at,
            ),
            chapters=[
                ChapterOut(
                    id=c.id,
                    idx=c.idx,
                    title=c.title,
                    start=c.start,
                    end=c.end,
                    para_start=c.para_start,
                    para_count=len(c.paras_json),
                    chars=sum(e - s for s, e in c.paras_json),
                )
                for c in chapters
            ],
            chapter=idx,
            paragraphs=[
                ParagraphOut(idx=shown.para_start + i, text=text[s:e], start=s, end=e)
                for i, (s, e) in enumerate(shown.paras_json)
            ],
        )

    async def text(self, sha256: str) -> str:
        """A source's normalized text (the few most recent are kept in memory)."""
        if sha256 in self._texts:
            self._texts.move_to_end(sha256)
            return self._texts[sha256]
        data = await asyncio.to_thread(self._store.read_bytes, sha256)
        text = data.decode("utf-8")
        self._texts[sha256] = text
        while len(self._texts) > _TEXT_CACHE:
            self._texts.popitem(last=False)
        return text

    # ------------------------------------------------------------------ internals

    @staticmethod
    async def _parse(filename: str, data: bytes) -> ParsedNovel:
        try:
            return await asyncio.to_thread(parse_upload, filename, data)
        except NovelParseError as exc:
            raise PipelineError(_PARSE_STATUS.get(exc.code, 422), exc.code, **exc.params) from exc

    async def _require_series(self, series_id: str, session: AsyncSession | None = None) -> None:
        if session is None:
            async with self._db.session() as own:
                found = await own.get(Series, series_id)
        else:
            found = await session.get(Series, series_id)
        if found is None:
            raise PipelineError(404, "series_not_found", id=series_id)

    @staticmethod
    async def _product(session: AsyncSession, series_id: str) -> Product | None:
        query = select(Product).where(
            Product.owner_type == "series",
            Product.owner_id == series_id,
            Product.slot == NOVEL_SLOT,
        )
        return (await session.exec(query)).first()

    @staticmethod
    async def _adopted_source(session: AsyncSession, product: Product) -> NovelSource | None:
        if product.adopted_version_id is None:
            return None
        version = await session.get(ProductVersion, product.adopted_version_id)
        if version is None:
            return None
        return await session.get(NovelSource, str(version.payload_json.get("source_id")))

    @staticmethod
    async def _chapters(session: AsyncSession, source_id: str) -> list[Chapter]:
        rows = await session.exec(
            select(Chapter).where(Chapter.source_id == source_id).order_by(col(Chapter.idx))
        )
        return list(rows.all())
