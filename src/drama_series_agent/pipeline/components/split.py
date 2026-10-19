"""分集规划 (SPEC 5 ``split``): the adopted novel, its adopted additions and the story bible →
episodes and their beats (``episodes`` product).

Each episode gets a title, a hook, a cliffhanger, the planned length and scene count, and
3–10 beats with an emotion (-1..1, the emotion curve) and the paragraphs they come from. The
prompt carries the output spec's episode length, the bible's names, every chapter's summary
(设定提取 writes them) and the text itself with the accepted additions, in chunks as the other
whole-book components (``chunks``); a later chunk continues the numbering of the one before.
``episodes.ops.reconcile`` keeps the ids of the adopted plan (episode n stays episode n).

Mock mode: the demo novel is answered from ``tests/fixtures/demo/split.json`` (the demo seed's
plan is built from the same file); any other novel by simple deterministic rules.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from functools import cache
from typing import Annotated, Any, cast

from pydantic import AliasChoices, BaseModel, BeforeValidator, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from drama_series_agent.bible import merge as bible_ops
from drama_series_agent.bible.service import bible_product
from drama_series_agent.core.config import get_config
from drama_series_agent.core.models_db import OutputSpecRow, Product, ProductVersion
from drama_series_agent.core.paths import REPO_ROOT
from drama_series_agent.episodes import ops
from drama_series_agent.modelhub.adapters.base import Estimate, ModelRequest
from drama_series_agent.modelhub.adapters.mock import Responder, estimate_tokens
from drama_series_agent.novel.service import Book, NovelService
from drama_series_agent.pipeline.component import (
    CallResult,
    ComponentError,
    Inputs,
    RunContext,
    Services,
)
from drama_series_agent.pipeline.components.chunks import (
    Additions,
    ChunkedComponent,
    Piece,
    chunk_book,
    chunk_paragraphs,
    is_demo,
    render_chunk,
    user_text,
)
from drama_series_agent.pipeline.components.enrich import names_text
from drama_series_agent.pipeline.drafts import VersionDraft
from drama_series_agent.pipeline.errors import PipelineError
from drama_series_agent.prompts.compiler import Block
from drama_series_agent.suggestions import ops as suggestion_ops
from drama_series_agent.suggestions.service import ADOPTED_SLICE, adopted_additions

DEMO_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "demo" / "split.json"
DEFAULT_LENGTH = (30, 90)
MIN_CHUNK = 1000  # tokens of text per chunk at least, whatever the other blocks take

# --------------------------------------------------------------------------- model output


def _number(v: Any) -> Any:
    """``12``, ``"12"`` and ``"P12"`` are all 12."""
    if isinstance(v, str) and (m := re.search(r"\d+", v)):
        return int(m.group())
    return v


def _text(v: Any) -> Any:
    return "" if v is None else v


def _emotion(v: Any) -> Any:
    if isinstance(v, str):
        try:
            v = float(v)
        except ValueError:
            return 0.0
    return max(-1.0, min(1.0, float(v))) if isinstance(v, int | float) else 0.0


def _optional(v: Any) -> Any:
    return None if v in (None, "", 0, "0") else _number(v)


Number = Annotated[int, BeforeValidator(_number)]
Text = Annotated[str, BeforeValidator(_text)]


class PlannedBeat(BaseModel):
    text: Text = Field(default="", validation_alias=AliasChoices("text", "beat", "summary"))
    emotion: Annotated[float, BeforeValidator(_emotion)] = 0.0
    paras: list[Number] = Field(default_factory=list)


class PlannedEpisode(BaseModel):
    ep: Annotated[int | None, BeforeValidator(_optional)] = None
    title: Text = ""
    hook: Text = ""
    cliffhanger: Text = Field(default="", validation_alias=AliasChoices("cliffhanger", "cliff"))
    seconds: Annotated[int | None, BeforeValidator(_optional)] = None
    scenes: Annotated[int | None, BeforeValidator(_optional)] = None
    beats: list[PlannedBeat] = Field(default_factory=list)


class SplitOut(BaseModel):
    episodes: list[PlannedEpisode] = Field(default_factory=list)


# --------------------------------------------------------------------------- helpers


def length_of(episode_len: str | None) -> tuple[int, int]:
    """[shortest, longest] seconds of an output spec's 每集时长."""
    lengths = get_config().spec.episode_lengths
    pair = lengths.get(episode_len or "") or lengths.get("short")
    return (int(pair[0]), int(pair[1])) if pair and len(pair) == 2 else DEFAULT_LENGTH


def length_text(seconds: tuple[int, int]) -> str:
    return f"每集时长：{seconds[0]}–{seconds[1]} 秒"


def summaries_text(book: Book, chapters: Sequence[Mapping[str, Any]]) -> str:
    """Every chapter's summary with its paragraph numbers (1-based as in the text)."""
    by_idx = {int(c["idx"]): str(c.get("summary") or "") for c in chapters}
    lines = []
    for c in book.chapters:
        paras = book.paragraphs(c)
        if not paras:
            continue
        span = f"P{paras[0] + 1}–P{paras[-1] + 1}"
        summary = by_idx.get(c.idx, "")
        lines.append(f"{Piece(c, []).heading()}（{span}）{('：' + summary) if summary else ''}")
    return "\n".join(lines)


def continued_text(episodes: Sequence[Mapping[str, Any]]) -> str:
    """[上一块]: where the chunk before stopped."""
    last = episodes[-1]
    paras = [p for b in last.get("beats") or [] for p in b.get("paras") or []]
    upto = f"，最后一段是 P{max(paras) + 1}" if paras else ""
    n = len(episodes)
    return (
        f"已经切到第 {n} 集《{last.get('title') or ''}》{upto}。"
        f"这一集没讲完就接着写它（ep 写 {n}），否则 ep 从 {n + 1} 开始。"
    )


def collect(
    book: Book, chunk: Sequence[Piece], out: SplitOut, seconds: tuple[int, int]
) -> list[dict[str, Any]]:
    """One chunk's episodes (with the model's ``ep``, see ``extend``): paragraph numbers outside
    the chunk are dropped (0-based after), beats without text and episodes without beats too."""
    allowed = {i for piece in chunk for i in piece.paras}
    found: list[dict[str, Any]] = []
    for e in out.episodes:
        beats = []
        for b in e.beats:
            text = b.text.strip()
            if not text:
                continue
            paras = sorted({p - 1 for p in b.paras if p - 1 in allowed})
            beats.append(
                {
                    "text": text,
                    "emotion": round(b.emotion, 2),
                    "paras": paras,
                    "source_spans": [s for p in paras if (s := book.span(p)) is not None],
                }
            )
        if not beats:
            continue
        found.append(
            {
                "ep": e.ep,
                "title": e.title.strip(),
                "hook": e.hook.strip() or None,
                "cliffhanger": e.cliffhanger.strip() or None,
                "target_seconds": e.seconds if e.seconds and e.seconds > 0 else sum(seconds) // 2,
                "scene_count": e.scenes if e.scenes and e.scenes > 0 else None,
                "beats": beats,
            }
        )
    return found


def extend(found: list[dict[str, Any]], new: Sequence[Mapping[str, Any]]) -> None:
    """Add a chunk's episodes to the plan so far. The chunk's first episode continues the last
    one when the model gave it that number ([上一块]); an untitled episode is 「第 N 集」."""
    for i, item in enumerate(new):
        e = dict(item)
        ep = e.pop("ep", None)
        if i == 0 and found and ep == len(found):
            last = found[-1]
            last["beats"] = [*last["beats"], *e["beats"]]
            last["hook"] = last["hook"] or e["hook"]
            last["cliffhanger"] = e["cliffhanger"] or last["cliffhanger"]
            for key in ("target_seconds", "scene_count"):
                values = [v for v in (last[key], e[key]) if v]
                last[key] = max(values) if values else None
            continue
        e["title"] = e["title"] or f"第 {len(found) + 1} 集"
        found.append(e)


def payload_of(book: Book, episodes: list[dict[str, Any]]) -> dict[str, Any]:
    return {"source_id": book.source.id, "episodes": episodes}


# --------------------------------------------------------------------------- the component


class SplitComponent(ChunkedComponent):
    id = "split"
    slot = "episodes"
    owner_type = "series"
    max_tokens = 4000

    def __init__(self, services: Services, novel: NovelService) -> None:
        super().__init__(services)
        self.novel = novel

    async def inputs(self, session: AsyncSession, product: Product) -> Inputs:
        inv = self.services.invalidation
        series_id = product.series_id
        book = await self.novel.book(session, series_id)
        if book is None or book.product_id is None:
            raise PipelineError(409, "upstream_not_ready", slot="novel")
        bible = await bible_product(session, series_id)
        adopted = (
            await session.get(ProductVersion, bible.adopted_version_id)
            if bible is not None and bible.adopted_version_id
            else None
        )
        if bible is None or adopted is None:
            raise PipelineError(409, "upstream_not_ready", slot="bible")
        deps = [
            await inv.dependency(session, book.product_id, "chapters"),
            await inv.dependency(session, bible.id, "chapters"),
            await inv.dependency(session, bible.id, "names"),
        ]
        additions: dict[int, list[str]] = {}
        enrich = await adopted_additions(session, series_id, self.novel, book)
        if enrich is not None:
            enrich_id, accepted = enrich
            deps.append(await inv.dependency(session, enrich_id, ADOPTED_SLICE))
            additions = suggestion_ops.by_paragraph(accepted)
        spec = await session.get(OutputSpecRow, series_id)
        seconds = length_of(spec.episode_len if spec is not None else None)
        blocks = [Block("成片规格", length_text(seconds))]
        names = names_text(bible_ops.names_of(adopted.payload_json))
        if names:
            blocks.append(Block("设定", names))
        summaries = summaries_text(book, adopted.payload_json.get("chapters") or [])
        if summaries:
            blocks.append(Block("章节摘要", summaries))
        base = None
        if product.adopted_version_id:
            v = await session.get(ProductVersion, product.adopted_version_id)
            base = v.payload_json if v is not None else None
        return Inputs(
            blocks=blocks,
            deps=deps,
            context={
                "book": book,
                "additions": additions,
                "seconds": seconds,
                "base": base,
                "chain_context": await self.chain_context(),
            },
        )

    def output_schema(self) -> type[BaseModel]:
        return SplitOut

    def mock_responders(self) -> dict[str, Responder]:
        return {"run": mock_split}

    # ------------------------------------------------------------------ run

    async def run(self, ctx: RunContext, inputs: Inputs) -> VersionDraft:
        book: Book = inputs.context["book"]
        seconds = inputs.context["seconds"]
        sent: list[dict[str, Any]] = [{"role": "system", "content": ctx.compiled}]
        results: list[CallResult] = []
        found: list[dict[str, Any]] = []
        for chunk in self._chunks(inputs, ctx.model_key):
            messages = self._messages(ctx.compiled, inputs, chunk, found)
            result = await self.call_json(ctx, messages, SplitOut)
            results.append(result)
            sent += messages[1:]
            extend(found, collect(book, chunk, cast(SplitOut, result.data), seconds))
        if not results:
            raise ComponentError("novel_empty")
        if not found:
            raise ComponentError("no_episodes")
        episodes = ops.reconcile(found, inputs.context["base"])
        return self.draft(ctx, inputs, payload_of(book, episodes), results, sent)

    def estimate(self, inputs: Inputs, compiled: str, model: str) -> Estimate:
        """Every chunk (a later one with a one-line [上一块])."""
        adapter = self.services.registry.get(model)
        placeholder: list[dict[str, Any]] = [{"title": "", "beats": []}]
        estimates = [
            adapter.estimate(
                self.request(self._messages(compiled, inputs, c, placeholder if i else []), None)
            )
            for i, c in enumerate(self._chunks(inputs, model))
        ]
        return Estimate(
            cost_usd=sum(e.cost_usd for e in estimates),
            seconds=sum(e.seconds for e in estimates),
            priced=all(e.priced for e in estimates),
        )

    # ------------------------------------------------------------------ helpers

    def _chunks(self, inputs: Inputs, model: str) -> list[list[Piece]]:
        """Chunks of the text; the other blocks (spec, names, summaries) go with each one."""
        others = sum(estimate_tokens(b.text) for b in inputs.blocks)
        limit = max(MIN_CHUNK, self.chunk_limit(inputs, model) - others)
        return chunk_book(inputs.context["book"], limit, inputs.context["additions"])

    def _messages(
        self,
        compiled: str,
        inputs: Inputs,
        chunk: Sequence[Piece],
        before: Sequence[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        book: Book = inputs.context["book"]
        additions: Additions = inputs.context["additions"]
        blocks = list(inputs.blocks)
        if before:
            blocks.append(Block("上一块", continued_text(before)))
        blocks.append(Block("原文", render_chunk(book, chunk, additions)))
        return self.services.compiler.messages(compiled, blocks)


# --------------------------------------------------------------------------- Mock mode

_HEADING = re.compile(r"^\[第 (\d+) 章\]\s*(.*?)(（续）)?$")
_PARA = re.compile(r"^\[P(\d+)\] (.*)$")
_SO_FAR = re.compile(r"^已经切到第 (\d+) 集")
_EMOTIONS = (-0.2, 0.1, 0.3, -0.4, 0.2, -0.1)
BEAT_PARAS = 3
MAX_BEATS = 8


@cache
def demo_fixture() -> dict[str, Any] | None:
    if not DEMO_FIXTURE.is_file():
        return None
    data: dict[str, Any] = json.loads(DEMO_FIXTURE.read_text(encoding="utf-8"))
    return data


def demo_answer(demo: Mapping[str, Any], paras: set[int]) -> dict[str, Any]:
    """The fixture's episodes with the beats that start in the paragraphs (1-based) a chunk
    holds; an episode cut by the chunk keeps its number, so the next chunk continues it."""
    episodes = []
    for e in demo["episodes"]:
        beats = [
            {k: v for k, v in b.items() if k != "id"}
            for b in e["beats"]
            if min(b["paras"]) in paras
        ]
        if beats:
            episodes.append({**{k: v for k, v in e.items() if k != "id"}, "beats": beats})
    return {"episodes": episodes}


def mock_split(req: ModelRequest) -> dict[str, Any]:
    text = user_text(req)
    paras = chunk_paragraphs(text)
    demo = demo_fixture()
    if demo and is_demo(paras):
        return demo_answer(demo, set(paras))
    return _rules(text)


def _rules(text: str) -> dict[str, Any]:
    """Any other novel: one episode per chapter part of the chunk (the rest of a chapter the
    chunk before began continues its episode), a beat per three paragraphs (at most eight),
    the last beat the episode's cliffhanger."""
    parts: list[tuple[str, bool, list[tuple[int, str]]]] = []
    so_far = 0
    in_text = False
    for line in text.splitlines():
        if m := _SO_FAR.match(line):
            so_far = int(m.group(1))
        elif line == "[原文]":
            in_text = True
        elif in_text and (m := _HEADING.match(line)):
            parts.append((m.group(2).strip(), bool(m.group(3)), []))
        elif in_text and parts and (m := _PARA.match(line)):
            parts[-1][2].append((int(m.group(1)), m.group(2).split("【补写】")[0]))
    episodes: list[dict[str, Any]] = []
    ep = so_far
    for title, cont, lines in parts:
        if not lines:
            continue
        ep = ep if cont and not episodes and so_far else ep + 1
        size = max(BEAT_PARAS, math.ceil(len(lines) / MAX_BEATS))
        groups = [lines[i : i + size] for i in range(0, len(lines), size)]
        beats = [
            {
                "text": g[0][1][:24],
                "emotion": 0.6 if n == len(groups) - 1 else _EMOTIONS[n % len(_EMOTIONS)],
                "paras": [p for p, _ in g],
            }
            for n, g in enumerate(groups)
        ]
        episodes.append(
            {
                "ep": ep,
                "title": title,
                "hook": lines[0][1][:20],
                "cliffhanger": lines[-1][1][:20],
                "seconds": 60,
                "scenes": max(1, math.ceil(len(beats) / 3)),
                "beats": beats,
            }
        )
    return {"episodes": episodes}


def demo_payload(book: Book) -> dict[str, Any] | None:
    """The demo series' plan: the fixture's answer for the whole book, assembled exactly as a
    run assembles it (ids from the fixture). None without the fixture."""
    demo = demo_fixture()
    if demo is None:
        return None
    chunk = [Piece(c, book.paragraphs(c)) for c in book.chapters]
    numbers = {i + 1 for piece in chunk for i in piece.paras}
    found: list[dict[str, Any]] = []
    answer = SplitOut.model_validate(demo_answer(demo, numbers))
    extend(found, collect(book, chunk, answer, (30, 90)))

    def ids(e: Mapping[str, Any]) -> list[dict[str, Any]]:
        return [{"id": b["id"], "text": b["text"]} for b in e["beats"]]

    base = {
        "episodes": [
            {"id": e["id"], "idx": n, "beats": ids(e)} for n, e in enumerate(demo["episodes"], 1)
        ]
    }
    return payload_of(book, ops.reconcile(found, base))
