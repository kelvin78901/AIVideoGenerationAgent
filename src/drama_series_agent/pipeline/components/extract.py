"""设定提取 (SPEC 5 ``extract``): the adopted novel and its adopted additions → the story bible
(``bible`` product).

The novel goes out in chunks (``chunks``), each paragraph followed by the additions the user
accepted in 小说补全 (M2 plan 计划变更 5); the bible depends on those through the ``adopted`` slice,
so accepting or undoing one makes it stale. ``bible.merge`` then groups the chunks' answers,
keeps the ids and frozen entries of the adopted version, and one more call judges the pairs
that may still be the same (→ merge suggestions for the user). Each chapter also gets a
summary, which episode planning reads.

Mock mode: the demo novel is answered from ``tests/fixtures/demo/extract.json`` (the demo
seed's bible is built from the same file); any other novel by simple deterministic rules.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from functools import cache
from typing import Annotated, Any, Literal, cast

from pydantic import BaseModel, BeforeValidator, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from drama_series_agent.bible import merge as ops
from drama_series_agent.core.models_db import Product, ProductVersion
from drama_series_agent.core.paths import REPO_ROOT
from drama_series_agent.modelhub.adapters.base import Estimate, ModelRequest
from drama_series_agent.modelhub.adapters.mock import Responder
from drama_series_agent.novel.service import Book, NovelService
from drama_series_agent.pipeline.component import (
    CallResult,
    ComponentError,
    Inputs,
    RunContext,
    Services,
)
from drama_series_agent.pipeline.components.chunks import (
    ADDITION_MARK,
    Additions,
    ChunkedComponent,
    Piece,
    chunk_book,
    chunk_paragraphs,
    is_demo,
    render_chunk,
    user_text,
)
from drama_series_agent.pipeline.drafts import VersionDraft
from drama_series_agent.pipeline.errors import PipelineError
from drama_series_agent.prompts.compiler import Block
from drama_series_agent.suggestions import ops as suggestion_ops
from drama_series_agent.suggestions.service import ADOPTED_SLICE, adopted_additions

JUDGE_MAX_TOKENS = 1500
DEMO_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "demo" / "extract.json"

# --------------------------------------------------------------------------- model output

_KINDS = {
    "人物": "character", "角色": "character", "地点": "location", "场景": "location",
    "道具": "prop", "物品": "prop", "事件": "event", "时间": "event", "时间线": "event",
    "时间点": "event", "关系": "relation", "人物关系": "relation",
}  # fmt: skip


def _kind(v: Any) -> Any:
    return _KINDS.get(v.strip(), v.strip().lower()) if isinstance(v, str) else v


def _number(v: Any) -> Any:
    """``12``, ``"12"`` and ``"P12"`` are all paragraph 12."""
    if isinstance(v, str) and (m := re.search(r"\d+", v)):
        return int(m.group())
    return v


def _text(v: Any) -> Any:
    return "" if v is None else v


def _names(v: Any) -> Any:
    if v is None:
        return []
    return [n for n in re.split(r"[、,，/]", v) if n.strip()] if isinstance(v, str) else v


Number = Annotated[int, BeforeValidator(_number)]
Text = Annotated[str, BeforeValidator(_text)]


class ExtractedEntity(BaseModel):
    kind: Annotated[
        Literal["character", "location", "prop", "event", "relation"], BeforeValidator(_kind)
    ]
    name: str = Field(min_length=1)
    aliases: Annotated[list[str], BeforeValidator(_names)] = Field(default_factory=list)
    summary: Text = ""
    details: dict[str, Any] = Field(default_factory=dict)
    paras: list[Number] = Field(default_factory=list)


class ChapterSummary(BaseModel):
    chapter: Number
    summary: Text = ""


class ExtractOut(BaseModel):
    entities: list[ExtractedEntity] = Field(default_factory=list)
    chapters: list[ChapterSummary] = Field(default_factory=list)


class Verdict(BaseModel):
    pair: Number
    same: bool
    reason: Text = ""


class JudgeOut(BaseModel):
    verdicts: list[Verdict] = Field(default_factory=list)


# --------------------------------------------------------------------------- answers


def collect(
    chunk: Sequence[Piece],
    out: ExtractOut,
    found: list[ops.Found],
    summaries: dict[int, list[str]],
) -> None:
    """One chunk's answer: paragraph numbers outside the chunk are dropped (0-based after)."""
    allowed = {i for piece in chunk for i in piece.paras}
    numbers = {piece.chapter.idx + 1: piece.chapter.idx for piece in chunk}
    for e in out.entities:
        found.append(
            ops.Found(
                kind=e.kind,
                name=e.name.strip(),
                aliases=[a.strip() for a in e.aliases],
                summary=e.summary,
                details=dict(e.details),
                paras=sorted({p - 1 for p in e.paras if p - 1 in allowed}),
            )
        )
    for s in out.chapters:
        idx = numbers.get(s.chapter)
        if idx is not None and s.summary.strip():
            summaries.setdefault(idx, []).append(s.summary.strip())


def judge_data(book: Book, pairs: Sequence[tuple[dict[str, Any], dict[str, Any]]]) -> str:
    """The pairs to judge, numbered, each name with the first paragraph that mentions it."""

    def label(e: dict[str, Any]) -> str:
        aliases = e.get("aliases") or []
        return str(e["name"]) + (f"（又名：{'、'.join(aliases)}）" if aliases else "")

    lines = ["[待核对]"]
    for n, (a, b) in enumerate(pairs, 1):
        kind = ops.KIND_LABEL.get(a["kind"], a["kind"])
        lines.append(f"{n}. {kind}：{label(a)} ⇄ {label(b)}")
        for e in (a, b):
            if e.get("paras"):
                text = book.paragraph(e["paras"][0])
                lines.append(f"   - {e['name']}：{text[:60]}{'…' if len(text) > 60 else ''}")
    return "\n".join(lines)


def payload_of(
    book: Book,
    entities: list[dict[str, Any]],
    summaries: dict[int, list[str]],
    merges: list[dict[str, Any]],
    distinct: list[list[str]],
) -> dict[str, Any]:
    return {
        "source_id": book.source.id,
        "entities": entities,
        "chapters": [
            {"idx": c.idx, "title": c.title, "summary": "".join(summaries.get(c.idx, []))}
            for c in book.chapters
        ],
        "merge_suggestions": merges,
        "distinct": distinct,
    }


# --------------------------------------------------------------------------- the component


class ExtractComponent(ChunkedComponent):
    id = "extract"
    slot = "bible"
    owner_type = "series"
    max_tokens = 8000
    output_ratio = 1.4  # 2999 out for 2741 in (M2 step 13)

    def __init__(self, services: Services, novel: NovelService) -> None:
        super().__init__(services)
        self.novel = novel

    async def inputs(self, session: AsyncSession, product: Product) -> Inputs:
        book = await self.novel.book(session, product.series_id)
        if book is None or book.product_id is None:
            raise PipelineError(409, "upstream_not_ready", slot="novel")
        inv = self.services.invalidation
        deps = [await inv.dependency(session, book.product_id, "chapters")]
        additions: dict[int, list[str]] = {}
        enrich = await adopted_additions(session, product.series_id, self.novel, book)
        if enrich is not None:
            enrich_id, accepted = enrich
            deps.append(await inv.dependency(session, enrich_id, ADOPTED_SLICE))
            additions = suggestion_ops.by_paragraph(accepted)
        base = None
        if product.adopted_version_id:
            adopted = await session.get(ProductVersion, product.adopted_version_id)
            base = adopted.payload_json if adopted is not None else None
        return Inputs(
            blocks=[],
            deps=deps,
            context={
                "book": book,
                "additions": additions,
                "base": base,
                "chain_context": await self.chain_context(),
            },
        )

    def output_schema(self) -> type[BaseModel]:
        return ExtractOut

    def mock_responders(self) -> dict[str, Responder]:
        return {"run": mock_extract, "judge": mock_judge}

    # ------------------------------------------------------------------ run

    async def run(self, ctx: RunContext, inputs: Inputs) -> VersionDraft:
        book: Book = inputs.context["book"]
        sent: list[dict[str, Any]] = [{"role": "system", "content": ctx.compiled}]
        results: list[CallResult] = []
        found: list[ops.Found] = []
        summaries: dict[int, list[str]] = {}
        additions = inputs.context["additions"]
        for chunk in chunk_book(book, self.chunk_limit(inputs, ctx.model_key), additions):
            messages = self._messages(ctx.compiled, book, chunk, additions)
            result = await self.call_json(ctx, messages, ExtractOut)
            results.append(result)
            sent += messages[1:]
            collect(chunk, cast(ExtractOut, result.data), found, summaries)
        if not results:
            raise ComponentError("novel_empty")
        entities, distinct = ops.reconcile(ops.group(found), inputs.context["base"], book.span)
        merges: list[dict[str, Any]] = []
        pairs = ops.candidates(entities, distinct)
        if pairs:
            messages = self._judge_messages(book, pairs)
            result = await self.call_json(
                ctx, messages, JudgeOut, task="judge", max_tokens=JUDGE_MAX_TOKENS
            )
            results.append(result)
            sent += messages
            verdicts = cast(JudgeOut, result.data).verdicts
            merges = ops.suggestions(pairs, [(v.pair, v.same, v.reason) for v in verdicts])
        payload = payload_of(book, entities, summaries, merges, distinct)
        return self.draft(ctx, inputs, payload, results, sent)

    def estimate(self, inputs: Inputs, compiled: str, model: str) -> Estimate:
        """Every chunk plus the judging call (an upper bound: it is skipped when no names
        look alike)."""
        book: Book = inputs.context["book"]
        additions = inputs.context["additions"]
        adapter = self.services.registry.get(model)
        requests = [
            self.request(self._messages(compiled, book, chunk, additions), None)
            for chunk in chunk_book(book, self.chunk_limit(inputs, model), additions)
        ]
        judge = self._judge_messages(book, [])
        requests.append(self.request(judge, None, "judge", JUDGE_MAX_TOKENS))
        estimates = [adapter.estimate(r) for r in requests]
        return Estimate(
            cost_usd=sum(e.cost_usd for e in estimates),
            seconds=sum(e.seconds for e in estimates),
            priced=all(e.priced for e in estimates),
        )

    # ------------------------------------------------------------------ helpers

    def _messages(
        self, compiled: str, book: Book, chunk: Sequence[Piece], additions: Additions | None = None
    ) -> list[dict[str, Any]]:
        text = render_chunk(book, chunk, additions)
        return self.services.compiler.messages(compiled, [Block("原文", text)])

    def _judge_messages(
        self, book: Book, pairs: Sequence[tuple[dict[str, Any], dict[str, Any]]]
    ) -> list[dict[str, Any]]:
        system = self.services.compiler.render("extract/judge.j2")
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": judge_data(book, pairs)},
        ]


# --------------------------------------------------------------------------- Mock mode

# A chapter's first part (a later part's heading ends with 「（续）」): only that one is
# summarized, as a model reading the whole chapter would.
_CHAPTER = re.compile(r"^\[第 (\d+) 章\](?!.*（续）$)", re.MULTILINE)
_HEADING = re.compile(r"^\[第 \d+ 章\]")
_PARA = re.compile(r"^\[P(\d+)\] (.*)$", re.MULTILINE)
_PAIR = re.compile(r"^(\d+)\. [^：\n]+：(.+?) ⇄ (.+)$", re.MULTILINE)
_HAN1 = re.compile(r"[㐀-鿿]")
_HAN2 = re.compile(r"[㐀-鿿]{2}")
_STOP = frozenset({
    "一个", "没有", "自己", "什么", "我们", "他们", "你们", "这个", "那个", "时候", "知道", "已经",
    "还是", "一下", "起来", "出来", "就是", "不是", "可以", "因为", "所以", "但是", "然后", "如果",
    "这样", "那样", "现在", "只是", "一样", "这里", "那里", "看着", "一声", "一边", "一直", "两个",
    "东西", "地方", "觉得", "一眼", "一句", "下来", "过来", "回来", "一点", "有点", "好像", "那天",
    "今天", "他的", "她的", "我的", "你的",
})  # fmt: skip


@cache
def demo_fixture() -> dict[str, Any] | None:
    if not DEMO_FIXTURE.is_file():
        return None
    data: dict[str, Any] = json.loads(DEMO_FIXTURE.read_text(encoding="utf-8"))
    return data


def demo_answer(demo: dict[str, Any], paras: set[int], chapters: set[int]) -> dict[str, Any]:
    """The fixture's answer for the paragraphs (1-based) and chapters a chunk holds."""
    entities = []
    for e in demo["entities"]:
        hits = [p for p in e["paras"] if p in paras]
        if hits:
            entities.append({**{k: v for k, v in e.items() if k != "id"}, "paras": hits})
    return {
        "entities": entities,
        "chapters": [c for c in demo["chapters"] if c["chapter"] in chapters],
    }


def mock_extract(req: ModelRequest) -> dict[str, Any]:
    """The demo novel (with or without its additions) from the fixture, else rules."""
    text = user_text(req).replace(ADDITION_MARK, "")
    paras = chunk_paragraphs(user_text(req))
    chapters = {int(n) for n in _CHAPTER.findall(text)}
    demo = demo_fixture()
    if demo and is_demo(paras):
        return demo_answer(demo, set(paras), chapters)
    return _rules(text, {int(n): t for n, t in _PARA.findall(text)})


def _rules(text: str, paras: dict[int, str]) -> dict[str, Any]:
    """Any other novel: the three most repeated two-character words are characters; each
    chapter's summary is the start of its first paragraph."""
    seen: dict[str, list[int]] = {}
    for n, t in sorted(paras.items()):
        for i in range(len(t) - 1):
            word = t[i : i + 2]
            if _HAN2.fullmatch(word) and word not in _STOP:
                hits = seen.setdefault(word, [])
                if n not in hits:
                    hits.append(n)
    ranked = sorted(
        (w for w, hits in seen.items() if len(hits) >= 2), key=lambda w: (-len(seen[w]), seen[w][0])
    )
    picked: list[str] = []
    for word in ranked:
        if not any(set(word) & set(p) for p in picked):
            picked.append(word)
        if len(picked) == 3:
            break
    summaries: list[dict[str, Any]] = []
    chapter = None
    for line in text.splitlines():
        if _HEADING.match(line):
            chapter = int(m.group(1)) if (m := _CHAPTER.match(line)) else None
        elif (
            chapter is not None
            and (m := _PARA.match(line))
            and all(s["chapter"] != chapter for s in summaries)
        ):
            summaries.append({"chapter": chapter, "summary": m.group(2)[:40]})
    return {
        "entities": [
            {"kind": "character", "name": w, "aliases": [], "summary": "", "paras": seen[w]}
            for w in picked
        ],
        "chapters": summaries,
    }


def _side(text: str) -> list[str]:
    name, _, rest = text.strip().partition("（又名：")
    return [name.strip(), *(a for a in rest.rstrip("）").split("、") if a.strip())]


def _alike(a: list[str], b: list[str]) -> bool:
    for x in a:
        for y in b:
            nx, ny = ops.normalize(x), ops.normalize(y)
            shared = set(_HAN1.findall(nx)) & set(_HAN1.findall(ny))
            if len(shared) >= 2 or (min(len(nx), len(ny)) >= 2 and (nx in ny or ny in nx)):
                return True
    return False


def mock_judge(req: ModelRequest) -> dict[str, Any]:
    """The fixture's verdict for a known pair; otherwise names sharing two Han characters
    (or one inside the other) are the same."""
    known = (demo_fixture() or {}).get("judge", [])
    verdicts = []
    for n, left, right in _PAIR.findall(user_text(req)):
        a, b = _side(left), _side(right)
        fixed = next((j for j in known if {a[0], b[0]} == set(j["names"])), None)
        if fixed is not None:
            verdicts.append({"pair": int(n), "same": fixed["same"], "reason": fixed["reason"]})
        else:
            same = _alike(a, b)
            verdicts.append({"pair": int(n), "same": same, "reason": "名字相近" if same else ""})
    return {"verdicts": verdicts}


def demo_payload(book: Book) -> dict[str, Any] | None:
    """The demo series' bible: the fixture's answer for the whole book, assembled exactly as
    a run assembles it (ids from the fixture). None without the fixture."""
    demo = demo_fixture()
    if demo is None:
        return None
    chunk = [Piece(c, book.paragraphs(c)) for c in book.chapters]
    numbers = {i + 1 for piece in chunk for i in piece.paras}
    answer = demo_answer(demo, numbers, {c.idx + 1 for c in book.chapters})
    found: list[ops.Found] = []
    summaries: dict[int, list[str]] = {}
    collect(chunk, ExtractOut.model_validate(answer), found, summaries)
    ids = [{k: e[k] for k in ("id", "kind", "name", "aliases")} for e in demo["entities"]]
    base = {"entities": ids}
    entities, distinct = ops.reconcile(ops.group(found), base, book.span)
    pairs = ops.candidates(entities, distinct)
    request = ModelRequest(
        kind="llm", messages=[{"role": "user", "content": judge_data(book, pairs)}]
    )
    verdicts = mock_judge(request)["verdicts"] if pairs else []
    merges = ops.suggestions(pairs, [(v["pair"], v["same"], v["reason"]) for v in verdicts])
    return payload_of(book, entities, summaries, merges, distinct)
