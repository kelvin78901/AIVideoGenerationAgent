"""小说补全 (SPEC 5 ``enrich``): the adopted novel → suggestions to fill what a camera cannot
shoot (``suggestions`` product), each anchored to the paragraph it follows.

The novel goes out in chunks like 设定提取 (``chunks``), with the bible's names and frozen
entries (the ``names`` slice only, so extraction running again leaves the suggestions fresh,
M2 plan 计划变更 5). ``suggestions.ops.reconcile`` keeps the accepted suggestions of the adopted
version and the ids of the ones proposed again, so the user's decisions carry over.
「按要求重写这一条」 (``rewrite``) is one synchronous call on the route's model, priced first: over
the per-call cap it needs the user's yes (409 ``over_budget``, then ``confirm_budget``).

Mock mode: the demo novel is answered from ``tests/fixtures/demo/enrich.json`` (the demo seed is
built from the same file); any other novel by simple deterministic rules.
"""

from __future__ import annotations

import json
import random
import re
from collections.abc import Mapping, Sequence
from functools import cache
from typing import Annotated, Any, Literal, cast

from pydantic import AliasChoices, BaseModel, BeforeValidator, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from drama_series_agent.bible import merge as bible_ops
from drama_series_agent.bible.service import bible_product
from drama_series_agent.core.models_db import Product, ProductVersion
from drama_series_agent.core.paths import REPO_ROOT
from drama_series_agent.modelhub.adapters.base import Estimate, ModelError, ModelRequest
from drama_series_agent.modelhub.adapters.mock import Responder
from drama_series_agent.modelhub.budget import EPSILON, cap_of
from drama_series_agent.modelhub.router import BudgetExceeded, Router
from drama_series_agent.novel.service import Book, NovelService
from drama_series_agent.pipeline.component import (
    CallResult,
    ComponentError,
    Inputs,
    RunContext,
    Services,
)
from drama_series_agent.pipeline.components.chunks import (
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
from drama_series_agent.suggestions import ops
from drama_series_agent.suggestions.service import decisions_of

REWRITE_MAX_TOKENS = 400
DEMO_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "demo" / "enrich.json"

# --------------------------------------------------------------------------- model output

_KINDS = {
    "外貌": "appearance", "穿着": "appearance", "外貌和穿着": "appearance",
    "光线": "lighting", "时间": "lighting", "光线和时间": "lighting",
    "心理外化": "inner_to_action", "动作": "inner_to_action", "卡点": "cliffhanger",
    "悬念": "cliffhanger", "动机": "motive", "时间线": "timeline", "一致性": "consistency",
    "前后一致": "consistency", "缺口": "gap", "空白": "gap",
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


Text = Annotated[str, BeforeValidator(_text)]


class EnrichedSuggestion(BaseModel):
    kind: Annotated[
        Literal[
            "appearance", "lighting", "inner_to_action", "cliffhanger", "motive", "timeline",
            "consistency", "gap",
        ],
        BeforeValidator(_kind),
    ] = Field(validation_alias=AliasChoices("kind", "type"))  # fmt: skip
    para: Annotated[int, BeforeValidator(_number)]
    reason: Text = ""
    text: Text = Field(default="", validation_alias=AliasChoices("text", "insert"))


class EnrichOut(BaseModel):
    suggestions: list[EnrichedSuggestion] = Field(default_factory=list)


class RewriteOut(BaseModel):
    text: str = Field(min_length=1)


# --------------------------------------------------------------------------- helpers


def names_text(names: Mapping[str, Any]) -> str:
    """The bible as 补全 reads it: names by kind, then the frozen entries."""

    def label(e: Mapping[str, Any]) -> str:
        aliases = e.get("aliases") or []
        return str(e["name"]) + (f"（又名：{'、'.join(aliases)}）" if aliases else "")

    lines = []
    for kind, title in bible_ops.KIND_LABEL.items():
        items = [label(e) for e in names.get("names") or [] if e["kind"] == kind]
        if items:
            lines.append(f"{title}：{'；'.join(items)}")
    fixed = names.get("fixed") or []
    if fixed:
        lines.append("冻结（不许改动）：")
        for e in fixed:
            summary = str((e.get("data") or {}).get("summary") or "")
            kind = bible_ops.KIND_LABEL.get(e["kind"], e["kind"])
            lines.append(f"- {kind}「{e['name']}」{('：' + summary) if summary else ''}")
    return "\n".join(lines)


def collect(book: Book, chunk: Sequence[Piece], out: EnrichOut) -> list[dict[str, Any]]:
    """One chunk's answer: paragraph numbers outside the chunk are dropped (0-based after)."""
    allowed = {i for piece in chunk for i in piece.paras}
    found = []
    for s in out.suggestions:
        idx, text = s.para - 1, s.text.strip()
        span = book.span(idx) if idx in allowed else None
        if span is None or not text:
            continue
        found.append(
            {
                "kind": s.kind,
                "para_idx": idx,
                "anchor_span": span,
                "reason": s.reason.strip(),
                "text": text,
            }
        )
    return found


def payload_of(book: Book, suggestions: list[dict[str, Any]]) -> dict[str, Any]:
    return {"source_id": book.source.id, "suggestions": suggestions}


# --------------------------------------------------------------------------- the component


class EnrichComponent(ChunkedComponent):
    id = "enrich"
    slot = "suggestions"
    owner_type = "series"
    max_tokens = 3000

    def __init__(self, services: Services, novel: NovelService) -> None:
        super().__init__(services)
        self.novel = novel

    async def inputs(self, session: AsyncSession, product: Product) -> Inputs:
        inv = self.services.invalidation
        book = await self.novel.book(session, product.series_id)
        if book is None or book.product_id is None:
            raise PipelineError(409, "upstream_not_ready", slot="novel")
        deps = [await inv.dependency(session, book.product_id, "chapters")]
        blocks = []
        bible = await bible_product(session, product.series_id)
        if bible is not None and bible.adopted_version_id is not None:
            adopted = await session.get(ProductVersion, bible.adopted_version_id)
            if adopted is not None:
                deps.append(await inv.dependency(session, bible.id, "names"))
                text = names_text(bible_ops.names_of(adopted.payload_json))
                if text:
                    blocks.append(Block("设定", text))
        base, decisions = await self._base(session, product, book)
        return Inputs(
            blocks=blocks,
            deps=deps,
            context={
                "book": book,
                "base": base,
                "decisions": decisions,
                "chain_context": await self.chain_context(),
            },
        )

    def output_schema(self) -> type[BaseModel]:
        return EnrichOut

    def mock_responders(self) -> dict[str, Responder]:
        return {"run": mock_enrich, "rewrite": mock_rewrite}

    # ------------------------------------------------------------------ run

    async def run(self, ctx: RunContext, inputs: Inputs) -> VersionDraft:
        book: Book = inputs.context["book"]
        sent: list[dict[str, Any]] = [{"role": "system", "content": ctx.compiled}]
        results: list[CallResult] = []
        found: list[dict[str, Any]] = []
        for chunk in chunk_book(book, self.chunk_limit(inputs, ctx.model_key)):
            messages = self._messages(ctx.compiled, inputs, book, chunk)
            result = await self.call_json(ctx, messages, EnrichOut)
            results.append(result)
            sent += messages[1:]
            found += collect(book, chunk, cast(EnrichOut, result.data))
        if not results:
            raise ComponentError("novel_empty")
        suggestions = ops.reconcile(found, inputs.context["base"], inputs.context["decisions"])
        return self.draft(ctx, inputs, payload_of(book, suggestions), results, sent)

    def estimate(self, inputs: Inputs, compiled: str, model: str) -> Estimate:
        book: Book = inputs.context["book"]
        adapter = self.services.registry.get(model)
        estimates = [
            adapter.estimate(self.request(self._messages(compiled, inputs, book, chunk), None))
            for chunk in chunk_book(book, self.chunk_limit(inputs, model))
        ]
        return Estimate(
            cost_usd=sum(e.cost_usd for e in estimates),
            seconds=sum(e.seconds for e in estimates),
            priced=all(e.priced for e in estimates),
        )

    # ------------------------------------------------------------------ rewrite

    async def rewrite(
        self,
        product: Product,
        suggestion: Mapping[str, Any],
        paragraph: str,
        instruction: str,
        *,
        confirm_budget: bool,
    ) -> tuple[str, str]:
        """「按要求重写这一条」: (new text, model key). Over the per-call cap without the user's
        yes → 409 ``over_budget``; a confirmed call may spend up to its estimate."""
        compiler = self.services.compiler
        settings = await self.services.router.settings(self.id)
        try:
            model = Router.primary_model(settings)
        except ModelError as exc:
            raise PipelineError(409, exc.code) from None
        intent = str((product.prompt_json or {}).get("intent") or "")
        intent = intent or compiler.default_intent(self.id)
        n = int(suggestion["para_idx"]) + 1
        messages = compiler.messages(
            compiler.render("enrich/rewrite.j2", intent=intent),
            [
                Block("原文", f"[P{n}] {paragraph}"),
                Block("补写", str(suggestion["text"])),
                Block("理由", str(suggestion.get("reason") or "")),
                Block("修改要求", instruction),
            ],
        )
        req = self.request(messages, None, "rewrite", REWRITE_MAX_TOKENS)
        cost = self.services.registry.get(model).estimate(req).cost_usd
        cap = cap_of(settings)
        over = cap is not None and cost > cap + EPSILON
        if over and not confirm_budget:
            raise PipelineError(
                409, "over_budget", estimate_usd=round(cost, 4), limit_usd=round(cap or 0.0, 4)
            )
        ctx = RunContext(
            product=product,
            mode="rewrite",
            model_key=model,
            seed=random.randrange(1, 2**31),
            intent=intent,
            compiled="",
            compiled_overridden=False,
            confirmed_usd=cost if over else None,
        )
        try:
            result = await self.call_json(
                ctx, messages, RewriteOut, task="rewrite", max_tokens=REWRITE_MAX_TOKENS
            )
        except BudgetExceeded as exc:
            raise PipelineError(
                409,
                "over_budget",
                estimate_usd=round(exc.estimate_usd, 4),
                limit_usd=round(exc.limit_usd, 4),
            ) from None
        except ModelError as exc:
            raise PipelineError(502, exc.code) from None
        except ComponentError as exc:
            raise PipelineError(502, exc.code, **exc.params) from None
        return cast(RewriteOut, result.data).text.strip(), result.model_key

    # ------------------------------------------------------------------ helpers

    def _messages(
        self, compiled: str, inputs: Inputs, book: Book, chunk: Sequence[Piece]
    ) -> list[dict[str, Any]]:
        blocks = [*inputs.blocks, Block("原文", render_chunk(book, chunk))]
        return self.services.compiler.messages(compiled, blocks)

    async def _base(
        self, session: AsyncSession, product: Product, book: Book
    ) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
        """The adopted version's suggestions, anchored in the current text, and decisions."""
        if product.adopted_version_id is None:
            return [], {}
        adopted = await session.get(ProductVersion, product.adopted_version_id)
        if adopted is None:
            return [], {}
        base = list(adopted.payload_json.get("suggestions") or [])
        decisions = await decisions_of(session, (s["id"] for s in base))
        old_id = str(adopted.payload_json.get("source_id"))
        if old_id != book.source.id:
            old = await self.novel.book_of(session, old_id)
            paragraphs = {i: book.paragraph(i) for i in book.offsets}
            base = ops.reanchor(base, old.paragraph if old else None, paragraphs, book.span)
        return base, decisions


# --------------------------------------------------------------------------- Mock mode

_CHAPTER = re.compile(r"^\[第 \d+ 章\](?!.*（续）$)", re.MULTILINE)
_BLOCK = re.compile(r"^\[([^\]\n]+)\]\n(.*?)(?=\n\n\[[^\]\n]+\]\n|\Z)", re.MULTILINE | re.DOTALL)


@cache
def demo_fixture() -> dict[str, Any] | None:
    if not DEMO_FIXTURE.is_file():
        return None
    data: dict[str, Any] = json.loads(DEMO_FIXTURE.read_text(encoding="utf-8"))
    return data


def demo_answer(demo: Mapping[str, Any], paras: set[int]) -> dict[str, Any]:
    """The fixture's suggestions on the paragraphs (1-based) a chunk holds."""
    return {
        "suggestions": [
            {k: v for k, v in s.items() if k != "id"}
            for s in demo["suggestions"]
            if s["para"] in paras
        ]
    }


def mock_enrich(req: ModelRequest) -> dict[str, Any]:
    text = user_text(req)
    paras = chunk_paragraphs(text)
    demo = demo_fixture()
    if demo and is_demo(paras):
        return demo_answer(demo, set(paras))
    return _rules(text, paras)


def _rules(text: str, paras: Mapping[int, str]) -> dict[str, Any]:
    """Any other novel: light and time at the start of each chapter, a cliffhanger at the
    chunk's last paragraph."""
    out = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if _CHAPTER.match(line):
            first = next((ln for ln in lines[i + 1 :] if ln.startswith("[P")), None)
            if first and (m := re.match(r"\[P(\d+)\]", first)):
                out.append(
                    {
                        "kind": "lighting",
                        "para": int(m.group(1)),
                        "reason": "这一章开头没有交代时间和光线，拍出来分不清是白天还是夜里。",
                        "text": "天色已经暗下来，屋里只亮着一盏灯。",
                    }
                )
    if paras:
        out.append(
            {
                "kind": "cliffhanger",
                "para": max(paras),
                "reason": "这里适合停住，留一个看得见的悬念。",
                "text": "画面停在这一刻，谁也没有再开口。",
            }
        )
    return {"suggestions": out}


def mock_rewrite(req: ModelRequest) -> dict[str, Any]:
    """The prototype's rewrite for a demo suggestion; otherwise the instruction in brackets."""
    blocks = {m.group(1): m.group(2).strip() for m in _BLOCK.finditer(user_text(req))}
    current = blocks.get("补写", "")
    demo = demo_fixture() or {}
    for s in demo.get("suggestions", []):
        if s["text"] == current and s["id"] in demo.get("rewrites", {}):
            return {"text": demo["rewrites"][s["id"]]}
    return {"text": f"{current}（{blocks.get('修改要求', '')}）"}


def demo_payload(book: Book) -> dict[str, Any] | None:
    """The demo series' suggestions: the fixture's answer for the whole book, assembled as a
    run assembles it (ids from the fixture). None without the fixture."""
    demo = demo_fixture()
    if demo is None:
        return None
    chunk = [Piece(c, book.paragraphs(c)) for c in book.chapters]
    numbers = {i + 1 for piece in chunk for i in piece.paras}
    found = collect(book, chunk, EnrichOut.model_validate(demo_answer(demo, numbers)))
    ids = iter(s["id"] for s in demo["suggestions"])
    return payload_of(book, ops.reconcile(found, [], {}, lambda: next(ids)))
