"""Importing and reading a series' novel (SPEC 4.1; 9.1 ``/series/{id}/novel``).

The novel is a product like the others (slot ``novel``, component ``import``): every import
appends a version (origin ``import``) and adopts it. So a re-import replaces the text while the
old one stays in the history, and whatever was built from it turns stale through the slice
hashes (``chapter:<idx>``, ``chapters``, see ``novel_slicer``) without storing a flag. Editing a
chapter by paragraphs (``edit_chapter``, M2 step 7b) works the same way: a new source with
encoding ``edited`` and an adopted ``edit`` version; the chapters it did not touch keep their
hashes. A novel locked by its gate refuses both (409 ``product_locked``): they go through the
impact preview (``novel_replace`` / ``novel_edit``, ``plan_replace`` / ``plan_edit``).

Components read the adopted text through ``book()``: chapters and paragraphs numbered across the
book, which is how prompts cite the novel (``[P12]``) and how answers map back to offsets.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import PurePath
from typing import Any, cast

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
from drama_series_agent.novel.parse import (
    NovelParseError,
    ParsedNovel,
    SplitBy,
    clean_paragraphs,
    clean_title,
    compose,
    parse_upload,
)
from drama_series_agent.novel.schema import (
    ChapterOut,
    NovelImportOut,
    NovelOut,
    ParagraphOut,
    SourceOut,
    import_out,
)
from drama_series_agent.pipeline.drafts import PlannedChange, VersionDraft
from drama_series_agent.pipeline.errors import PipelineError
from drama_series_agent.pipeline.hashing import hash_json
from drama_series_agent.pipeline.products import ProductService

NOVEL_SLOT = "novel"
IMPORT_COMPONENT = "import"
_PARSE_STATUS = {"unsupported_file": 415, "file_too_large": 413}
_TEXT_CACHE = 4
# A planned edit's payload names its source before the text is stored (``plan_edit``).
PENDING_SOURCE = "pending"


@dataclass(frozen=True)
class FixedIds:
    """The demo seed imports with the ids and times the MSW fixtures use."""

    product_id: str
    version_id: str
    source_id: str  # chapters are ``<source_id>-ch<n>``
    at: datetime


@dataclass
class Book:
    """A novel source as components read it: its chapters and paragraph offsets."""

    product_id: str | None  # the series' ``novel`` product (None for a source read by id)
    source: NovelSource
    chapters: list[Chapter]
    text: str
    # Paragraph number across the book (0-based) → (start, end) in ``text``.
    offsets: dict[int, tuple[int, int]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for c in self.chapters:
            for i, (s, e) in enumerate(c.paras_json):
                self.offsets[c.para_start + i] = (s, e)

    def paragraph(self, idx: int) -> str:
        s, e = self.offsets.get(idx, (0, 0))
        return self.text[s:e]

    def paragraphs(self, chapter: Chapter) -> list[int]:
        return [chapter.para_start + i for i in range(len(chapter.paras_json))]

    def span(self, idx: int) -> dict[str, Any] | None:
        """A paragraph as a source span ``{source_id, start, end}`` (SPEC 4.1)."""
        if idx not in self.offsets:
            return None
        s, e = self.offsets[idx]
        return {"source_id": self.source.id, "start": s, "end": e}


def chapter_hash(text: str, title: str | None, paras: list[list[int]] | tuple[Any, ...]) -> str:
    """What a chapter says: its title and paragraphs, not the blank lines around them."""
    return hash_json({"title": title, "paras": [text[s:e] for s, e in paras]})


async def novel_slicer(
    session: AsyncSession, product: Product, version: ProductVersion, name: str
) -> Any:
    """Slices of the ``novel`` product: ``chapter:<idx>`` is that chapter's title and hash."""
    if name == "":
        return version.payload_json
    if name == "chapters":  # the whole book, without file name or source id
        return [c.get("hash") for c in version.payload_json.get("chapters", [])]
    kind, _, key = name.partition(":")
    if kind == "chapter":
        for c in version.payload_json.get("chapters", []):
            if str(c.get("idx")) == key:
                return c
    return None


async def _nothing() -> None:
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
        # Called with the series id after a new text is adopted (creates the series' products).
        self.after_import: Callable[[str], Awaitable[None]] | None = None

    # ------------------------------------------------------------------ import

    async def preview(self, series_id: str, filename: str, data: bytes) -> NovelImportOut:
        """What an import would find (encoding, chapters). Only the file is kept, as
        ``upload_id``: replacing a confirmed novel previews the impact with it first
        (``plan_replace``)."""
        await self._require_series(series_id)
        name = safe_filename(filename)
        parsed = await self._parse(name, data)
        upload_id = await asyncio.to_thread(self._store.put_bytes, data)
        return import_out(parsed, name, dry_run=True, upload_id=upload_id)

    async def plan_replace(self, series_id: str, upload_id: str, filename: str) -> PlannedChange:
        """重新导入 a confirmed novel (the impact preview's ``novel_replace``): the file kept by
        the ``dry_run`` preview, parsed again; the commit imports it."""
        await self._require_series(series_id)
        try:
            data = await asyncio.to_thread(self._store.read_bytes, upload_id)
        except (ValueError, OSError) as exc:
            raise PipelineError(404, "upload_not_found", id=upload_id) from exc
        name = safe_filename(filename)
        parsed = await self._parse(name, data)
        text_sha = hashlib.sha256(parsed.text.encode("utf-8")).hexdigest()
        async with self._db.session() as session:
            product = await self._product(session, series_id)
            source = await self._adopted_source(session, product) if product else None
        if product is None or source is None:
            raise PipelineError(404, "novel_not_found", id=series_id)
        base_id = product.adopted_version_id
        if source.sha256 == text_sha:
            return PlannedChange(product.id, series_id, base_id, _nothing)

        async def commit() -> None:
            await self.import_novel(series_id, name, data, rights_confirmed=True)

        payload = self._payload(PENDING_SOURCE, name, text_sha, parsed)
        return PlannedChange(product.id, series_id, base_id, commit, payload, content=text_sha)

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
            source_id, chapter_ids = await self._add_source(
                session, series_id, name, parsed, text_sha, original_sha, at, at, fixed
            )
        draft = VersionDraft(
            payload=self._payload(source_id, name, text_sha, parsed),
            note=name,
            id=fixed.version_id if fixed else None,
            created_at=fixed.at if fixed else None,
        )
        await self._products.append(product.id, draft, origin="import", adopt=True)
        if self.after_import is not None:
            await self.after_import(series_id)
        return import_out(parsed, name, dry_run=False, source_id=source_id, chapter_ids=chapter_ids)

    # ------------------------------------------------------------------ edit

    async def edit_chapter(
        self, series_id: str, idx: int, title: str | None, paragraphs: Sequence[str]
    ) -> NovelOut:
        """逐段编辑: one chapter's title and paragraphs as the user left them (a line break
        starts a new paragraph, empty ones are dropped) → a new source and an adopted ``edit``
        version. Nothing changed → nothing is made. Returns the chapter as ``get`` shows it."""
        planned = await self.plan_edit(series_id, idx, title, paragraphs)
        await planned.commit()
        return await self.get(series_id, idx)

    async def plan_edit(
        self,
        series_id: str,
        idx: int,
        title: str | None,
        paragraphs: Sequence[str],
        *,
        allow_locked: bool = False,
    ) -> PlannedChange:
        """``edit_chapter`` worked out but not written; ``allow_locked`` for a confirmed novel
        (the impact preview, ``novel_edit``). The payload's source id is a placeholder until
        the commit stores the text."""
        paras = clean_paragraphs(paragraphs)
        if not paras:
            raise PipelineError(422, "chapter_empty", idx=idx)
        async with self._db.session() as session:
            await self._require_series(series_id, session)
            product = await self._product(session, series_id)
            source = await self._adopted_source(session, product) if product else None
            if product is None or source is None:
                raise PipelineError(404, "novel_not_found", id=series_id)
            if product.locked_hash and not allow_locked:
                raise PipelineError(409, "product_locked", id=product.id)
            chapters = await self._chapters(session, source.id)
        if idx >= len(chapters):
            raise PipelineError(404, "chapter_not_found", idx=idx)
        text = await self.text(source.sha256)
        before = [(c.title, [text[s:e] for s, e in c.paras_json]) for c in chapters]
        after = list(before)
        after[idx] = (clean_title(title), paras)
        base_id = product.adopted_version_id
        if after == before:
            return PlannedChange(product.id, series_id, base_id, _nothing)
        edited = compose(after, cast(SplitBy, source.split_by))
        data = edited.text.encode("utf-8")
        text_sha = hashlib.sha256(data).hexdigest()
        payload = self._payload(PENDING_SOURCE, source.filename, text_sha, edited)

        async def commit() -> None:
            await asyncio.to_thread(self._store.put_bytes, data)
            async with self._db.session() as session:
                source_id, _ = await self._add_source(
                    session,
                    series_id,
                    source.filename,
                    edited,
                    text_sha,
                    text_sha,
                    source.rights_confirmed_at,
                    utcnow(),
                )
            draft = VersionDraft(
                payload=self._payload(source_id, source.filename, text_sha, edited),
                note=source.filename,
            )
            await self._products.append(
                product.id, draft, origin="edit", parent_version_id=base_id, adopt=True
            )

        return PlannedChange(product.id, series_id, base_id, commit, payload, content=after)

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

    async def book(self, session: AsyncSession, series_id: str) -> Book | None:
        """The adopted novel of a series; None before anything is imported."""
        product = await self._product(session, series_id)
        source = await self._adopted_source(session, product) if product else None
        if product is None or source is None:
            return None
        chapters = await self._chapters(session, source.id)
        return Book(product.id, source, chapters, await self.text(source.sha256))

    async def book_of(self, session: AsyncSession, source_id: str) -> Book | None:
        """Any source by id (bible spans keep pointing at the text they were taken from)."""
        source = await session.get(NovelSource, source_id)
        if source is None:
            return None
        chapters = await self._chapters(session, source.id)
        return Book(None, source, chapters, await self.text(source.sha256))

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
    async def _add_source(
        session: AsyncSession,
        series_id: str,
        filename: str,
        parsed: ParsedNovel,
        text_sha: str,
        original_sha: str,
        rights_at: datetime,
        at: datetime,
        fixed: FixedIds | None = None,
    ) -> tuple[str, list[str]]:
        """A source row and its chapter rows (committed): (source id, chapter ids)."""
        source = NovelSource(
            series_id=series_id,
            filename=filename,
            sha256=text_sha,
            original_sha256=original_sha,
            encoding=parsed.encoding,
            split_by=parsed.split_by,
            chars=parsed.chars,
            rights_confirmed_at=rights_at,
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
        return source.id, [r.id for r in rows]

    @staticmethod
    def _payload(
        source_id: str, filename: str, text_sha: str, parsed: ParsedNovel
    ) -> dict[str, Any]:
        """A novel version: the source and each chapter's hash (what the slices read)."""
        text = parsed.text
        return {
            "source_id": source_id,
            "filename": filename,
            "sha256": text_sha,
            "chapters": [
                {"idx": c.idx, "title": c.title, "hash": chapter_hash(text, c.title, c.paras)}
                for c in parsed.chapters
            ],
        }

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
