"""Reading an uploaded novel: decode it, split chapters and paragraphs (SPEC 4.1).

Pure functions, no database. Offsets are characters of the normalized text (no BOM, ``\\n``
line ends): that text is what the blob store keeps and what every source span points into.
A paragraph is a non-blank line without its surrounding whitespace (full-width spaces
included); a chapter starts at a heading line: a short line that starts like 「第 X 章 / 回 /
节」, 「Chapter N」, 楔子 … and does not end like a sentence, or has a Word heading style. A
text without headings is cut into parts of about ``PART_TARGET_CHARS`` at paragraph ends.
"""

from __future__ import annotations

import codecs
import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import PurePath
from typing import Literal

MAX_UPLOAD_BYTES = 30 * 1024 * 1024
PART_TARGET_CHARS = 6000
# Longer lines are prose even if they start like a heading (「第三章写到这里……」).
HEADING_MAX_CHARS = 40
EXTENSIONS = (".txt", ".docx")

_NUM = "0-9０-９零〇一二两三四五六七八九十百千万壹贰叁肆伍陆柒捌玖拾佰仟"
_HEADINGS = (
    re.compile(rf"^第\s*[{_NUM}]+\s*[章回节]"),
    re.compile(r"^chapter\s+(?:\d+|[ivxlcdm]+)\b", re.IGNORECASE),
    re.compile(r"^(?:楔子|序章|序言|引子|尾声|后记|番外|prologue|epilogue)", re.IGNORECASE),
)
# A heading does not end like a sentence: 「第三节课下课后，他来了。」 is prose.
_SENTENCE_END = tuple('。！？!?…”"」』，,；;')
_SPACES = re.compile(r"\s+")
_LINE_BREAKS = str.maketrans({"\r": "\n", " ": "\n", " ": "\n", "\x0b": "\n", "\x0c": "\n"})

SplitBy = Literal["heading", "length"]


class NovelParseError(Exception):
    """The upload cannot be read; ``code`` + ``params`` reach the UI."""

    def __init__(self, code: str, **params: object) -> None:
        super().__init__(code)
        self.code = code
        self.params = params


@dataclass(frozen=True)
class ChapterDraft:
    idx: int
    title: str | None
    start: int
    end: int
    para_start: int  # number of the first paragraph, counted across the book
    paras: tuple[tuple[int, int], ...]

    @property
    def chars(self) -> int:
        return sum(e - s for s, e in self.paras)


@dataclass(frozen=True)
class ParsedNovel:
    text: str
    encoding: str  # utf-8 / utf-16 / gb18030 / docx
    split_by: SplitBy
    chapters: tuple[ChapterDraft, ...]

    @property
    def chars(self) -> int:
        return sum(c.chars for c in self.chapters)


def parse_upload(filename: str, data: bytes) -> ParsedNovel:
    """A .txt or .docx upload → normalized text, chapters and paragraphs."""
    ext = PurePath(filename).suffix.lower()
    if ext not in EXTENSIONS:
        raise NovelParseError("unsupported_file", ext=ext or filename)
    if len(data) > MAX_UPLOAD_BYTES:
        raise NovelParseError("file_too_large", limit_mb=MAX_UPLOAD_BYTES // (1024 * 1024))
    if ext == ".docx":
        raw, heading_lines = read_docx(data)
        encoding = "docx"
    else:
        raw, encoding = decode_text(data)
        heading_lines = frozenset()
    text = normalize(raw)
    split_by, chapters = split_chapters(text, heading_lines)
    if not chapters:
        raise NovelParseError("novel_empty")
    return ParsedNovel(text=text, encoding=encoding, split_by=split_by, chapters=chapters)


def decode_text(data: bytes) -> tuple[str, str]:
    """BOM first, then strict UTF-8, then GB18030 (a superset of GBK / GB2312)."""
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        candidates = ["utf-16"]
    elif data.startswith(codecs.BOM_UTF8):
        candidates = ["utf-8-sig"]
    else:
        candidates = ["utf-8", "gb18030"]
    for encoding in candidates:
        try:
            text = data.decode(encoding)
        except UnicodeDecodeError:
            continue
        # UTF-16 without a BOM decodes as UTF-8 full of NULs; nothing textual has them.
        if "\x00" in text:
            break
        return text, "utf-8" if encoding == "utf-8-sig" else encoding
    raise NovelParseError("novel_unreadable", reason="encoding")


def read_docx(data: bytes) -> tuple[str, frozenset[int]]:
    """Paragraph texts joined by line breaks, and which lines have a Word heading style."""
    from docx import Document

    try:
        doc = Document(io.BytesIO(data))
    except (zipfile.BadZipFile, KeyError, ValueError) as exc:
        raise NovelParseError("novel_unreadable", reason="docx") from exc
    lines: list[str] = []
    headings: set[int] = set()
    for para in doc.paragraphs:
        style = para.style.name if para.style is not None else ""
        if style and (style.startswith("Heading") or style.startswith("标题")):
            headings.add(len(lines))
        # A soft line break inside a Word paragraph comes back as "\n".
        lines.extend(para.text.split("\n"))
    return "\n".join(lines), frozenset(headings)


def normalize(text: str) -> str:
    """No BOM, ``\\n`` line ends; nothing else changes, so offsets stay readable."""
    return text.removeprefix("﻿").replace("\r\n", "\n").translate(_LINE_BREAKS)


def is_heading(line: str) -> bool:
    return (
        len(line) <= HEADING_MAX_CHARS
        and not line.endswith(_SENTENCE_END)
        and any(p.match(line) for p in _HEADINGS)
    )


def heading_title(line: str) -> str:
    return _SPACES.sub(" ", line)


def split_chapters(
    text: str, heading_lines: frozenset[int] = frozenset()
) -> tuple[SplitBy, tuple[ChapterDraft, ...]]:
    """Chapters at heading lines, else parts of about ``PART_TARGET_CHARS``.

    Text before the first heading is a chapter without a title; a heading with nothing under
    it (a volume title right before a chapter title) is dropped.
    """
    lines: list[tuple[bool, int, int]] = []  # (heading, start, end) of non-blank lines
    pos = 0
    for n, line in enumerate(text.split("\n")):
        stripped = line.strip()
        if stripped:
            start = pos + len(line) - len(line.lstrip())
            heading = len(stripped) <= HEADING_MAX_CHARS and (
                n in heading_lines or is_heading(stripped)
            )
            lines.append((heading, start, start + len(stripped)))
        pos += len(line) + 1

    groups: list[tuple[str | None, int, list[tuple[int, int]]]] = []  # (title, start, paras)
    if any(h for h, _, _ in lines):
        split_by: SplitBy = "heading"
        for heading, start, end in lines:
            if heading:
                groups.append((heading_title(text[start:end]), start, []))
            elif groups:
                groups[-1][2].append((start, end))
            else:
                groups.append((None, start, [(start, end)]))
    else:
        split_by = "length"
        size = 0
        for _, start, end in lines:
            if not groups or (size and size + end - start > PART_TARGET_CHARS):
                groups.append((None, start, []))
                size = 0
            groups[-1][2].append((start, end))
            size += end - start

    chapters: list[ChapterDraft] = []
    para_start = 0
    for title, start, paras in groups:
        if not paras:
            continue
        chapters.append(
            ChapterDraft(
                idx=len(chapters),
                title=title,
                start=start,
                end=paras[-1][1],
                para_start=para_start,
                paras=tuple(paras),
            )
        )
        para_start += len(paras)
    return split_by, tuple(chapters)
