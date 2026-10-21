"""The whole novel in chunks (M2 plan 设计要点「长小说」), for the components that read all of it
(设定提取, 小说补全).

Whole chapters are packed in order; a chunk is at most 60% of the smallest context window on
the route (the model and its fallback), so a long novel never overflows and the fallback can
take any chunk. It is also small enough that the answer fits in the component's ``max_tokens``:
the answer grows with the text (设定提取 wrote about as many tokens as it read in the M2 live
run), and a 1M-token window would otherwise put a whole long novel in one call whose JSON gets
cut off. A chapter longer than a chunk is split by paragraphs (「（续）」). Paragraphs are
numbered across the book, 1-based in the prompt as on screen (``[P12]``); the model only cites
numbers and the backend turns them into spans. Adopted additions (小说补全) follow their
paragraph on the same line after ``ADDITION_MARK``, so the numbers never move.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from functools import cache
from typing import ClassVar

from drama_series_agent.core.models_db import Chapter
from drama_series_agent.core.paths import REPO_ROOT
from drama_series_agent.modelhub.adapters.base import ModelError, ModelRequest
from drama_series_agent.modelhub.adapters.mock import estimate_tokens
from drama_series_agent.modelhub.router import Router
from drama_series_agent.novel.service import Book
from drama_series_agent.pipeline.component import Component, Inputs

CHUNK_SHARE = 0.6
OUTPUT_HEADROOM = 0.8  # the answer to a chunk may use this much of max_tokens
DEFAULT_CONTEXT = 32768  # a model whose window is not configured
ADDITION_MARK = "【补写】"
DEMO_NOVEL = REPO_ROOT / "tests" / "fixtures" / "demo" / "雨停之前.txt"

# Paragraph number (0-based) → the adopted additions appended to it, in order.
Additions = Mapping[int, Sequence[str]]


@dataclass
class Piece:
    """Paragraphs of one chapter in a chunk; ``cont`` = not the chapter's first part."""

    chapter: Chapter
    paras: list[int]
    cont: bool = False

    def heading(self) -> str:
        title = f" {self.chapter.title}" if self.chapter.title else ""
        return f"[第 {self.chapter.idx + 1} 章]{title}{'（续）' if self.cont else ''}"


def line(book: Book, idx: int, additions: Additions | None = None) -> str:
    extra = "".join(f"{ADDITION_MARK}{a}" for a in (additions or {}).get(idx, ()))
    return f"[P{idx + 1}] {book.paragraph(idx)}{extra}"


def chunk_book(book: Book, limit: int, additions: Additions | None = None) -> list[list[Piece]]:
    """Whole chapters packed in order, each chunk at most ``limit`` tokens (estimated); a
    chapter over the limit is split by paragraphs. A single huge paragraph is never cut."""
    parts: list[tuple[Piece, int]] = []
    for c in book.chapters:
        head = estimate_tokens(Piece(c, [], True).heading()) + 2
        piece, cost = Piece(c, []), head
        for idx in book.paragraphs(c):
            t = estimate_tokens(line(book, idx, additions)) + 1
            if piece.paras and cost + t > limit:
                parts.append((piece, cost))
                piece, cost = Piece(c, [], cont=True), head
            piece.paras.append(idx)
            cost += t
        if piece.paras:
            parts.append((piece, cost))
    chunks: list[list[Piece]] = []
    current: list[Piece] = []
    used = 0
    for piece, cost in parts:
        if current and used + cost > limit:
            chunks.append(current)
            current, used = [], 0
        current.append(piece)
        used += cost
    if current:
        chunks.append(current)
    return chunks


def render_chunk(book: Book, chunk: Sequence[Piece], additions: Additions | None = None) -> str:
    return "\n\n".join(
        "\n".join([piece.heading(), *(line(book, i, additions) for i in piece.paras)])
        for piece in chunk
    )


class ChunkedComponent(Component):
    """A component that sends the whole book, chunk by chunk."""

    # Answer tokens per chunk token (``estimate_tokens``), from the M2 live run with margin.
    output_ratio: ClassVar[float] = 1.0

    def chunk_limit(self, inputs: Inputs, model: str) -> int:
        window = min(int(inputs.context["chain_context"]), self.context_of(model))
        by_output = int(OUTPUT_HEADROOM * self.max_tokens / self.output_ratio)
        return min(int(CHUNK_SHARE * window), by_output)

    def context_of(self, model: str) -> int:
        try:
            return self.services.registry.spec(model).caps.max_context or DEFAULT_CONTEXT
        except ModelError:
            return DEFAULT_CONTEXT

    async def chain_context(self) -> int:
        """The smallest window among the route's model and its fallback."""
        settings = await self.services.router.settings(self.id)
        chain: list[str] = []
        with suppress(ModelError):
            chain.append(Router.primary_model(settings))
        fallback = settings.values.get("fallback") or {}
        if fallback.get("enabled") and fallback.get("to"):
            chain.append(str(fallback["to"]))
        return min((self.context_of(m) for m in chain), default=DEFAULT_CONTEXT)


# --------------------------------------------------------------------------- Mock mode

PARA_LINE = re.compile(r"^\[P(\d+)\] (.*)$", re.MULTILINE)


def user_text(req: ModelRequest) -> str:
    return "\n".join(str(m.get("content")) for m in req.messages or [] if m.get("role") == "user")


def chunk_paragraphs(text: str) -> dict[int, str]:
    """The paragraphs (1-based) a chunk sent, without their additions."""
    return {int(n): t.split(ADDITION_MARK)[0] for n, t in PARA_LINE.findall(text)}


@cache
def _demo_text() -> str:
    return DEMO_NOVEL.read_text(encoding="utf-8") if DEMO_NOVEL.is_file() else ""


def is_demo(paras: Mapping[int, str]) -> bool:
    """Every paragraph of the chunk is from the demo novel (its fixtures answer it)."""
    text = _demo_text()
    return bool(text and paras) and all(t.strip() and t in text for t in paras.values())
