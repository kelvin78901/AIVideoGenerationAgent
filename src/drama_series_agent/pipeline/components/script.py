"""剧本化 (SPEC 5 ``script``): one episode of the adopted plan → its scenes and lines (``script``
product, owned by the episode).

The prompt carries the episode (title, hook, cliffhanger, planned length and scenes), its beats,
the bible entries it uses and only the paragraphs its beats cite, each with its accepted
additions numbered (【补写1】) so a line can cite one (M2 plan 设计要点). The version depends on
exactly those slices: the episode (``episode:<id>``), the chapters the paragraphs are in
(``chapter:<idx>``), the additions on them (``adopted:<n,…>``) and the entries
(``entities:<id,…>``), so dragging a beat or accepting an addition makes only the scripts that
read it stale. ``script.ops.reconcile`` keeps the ids of the adopted script.

「重写这一段」 / 「换模型重写」 (``rewrite``) is one synchronous call priced first, like 小说补全's:
over the per-call cap or what is left of the episode's budget it needs the user's yes
(409 ``over_budget``, then ``confirm_budget``).

Mock mode: episode 1 of the demo novel is answered from ``tests/fixtures/demo/script.json`` (the
demo seed is built from the same file); anything else by simple deterministic rules.
"""

from __future__ import annotations

import json
import math
import random
import re
from collections.abc import Iterable, Mapping, Sequence
from functools import cache
from typing import Annotated, Any, Literal, cast

from pydantic import AliasChoices, BaseModel, BeforeValidator, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from drama_series_agent.bible import merge as bible_ops
from drama_series_agent.bible.service import bible_product
from drama_series_agent.core.models_db import Product, ProductVersion
from drama_series_agent.core.paths import REPO_ROOT
from drama_series_agent.episodes import ops as episode_ops
from drama_series_agent.episodes.service import split_product
from drama_series_agent.modelhub.adapters.base import ModelError, ModelRequest
from drama_series_agent.modelhub.adapters.mock import Responder
from drama_series_agent.modelhub.budget import EPSILON, Budget, cap_of
from drama_series_agent.modelhub.router import BudgetExceeded, Router
from drama_series_agent.novel.service import Book, NovelService
from drama_series_agent.pipeline.component import (
    Component,
    ComponentError,
    Inputs,
    RunContext,
    Services,
)
from drama_series_agent.pipeline.components.chunks import Piece, is_demo, user_text
from drama_series_agent.pipeline.components.split import Number, Text
from drama_series_agent.pipeline.errors import PipelineError
from drama_series_agent.pipeline.invalidation import Invalidation
from drama_series_agent.prompts.compiler import Block
from drama_series_agent.script import ops
from drama_series_agent.suggestions.service import adopted_additions, adopted_slice

DEMO_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "demo" / "script.json"
REWRITE_MAX_TOKENS = 400
LineType = Literal["action", "dialogue", "vo", "sfx"]

# --------------------------------------------------------------------------- model output

_TYPES = {
    "action": "action", "动作": "action", "画面": "action",
    "dialogue": "dialogue", "对白": "dialogue", "台词": "dialogue",
    "vo": "vo", "os": "vo", "旁白": "vo", "独白": "vo", "内心独白": "vo",
    "sfx": "sfx", "音效": "sfx",
}  # fmt: skip
_TIMES = {
    "day": "day", "日": "day", "白天": "day", "night": "night", "夜": "night", "晚上": "night",
    "dawn": "dawn", "晨": "dawn", "清晨": "dawn", "dusk": "dusk", "黄昏": "dusk", "傍晚": "dusk",
}  # fmt: skip
TIME_LABEL = {"day": "日", "night": "夜", "dawn": "晨", "dusk": "黄昏"}
LINE_LABEL = {"action": "动作", "dialogue": "对白", "vo": "旁白", "sfx": "音效"}


def _type(v: Any) -> Any:
    return _TYPES.get(str(v or "").strip().lower(), "action")


def _seconds(v: Any) -> Any:
    if isinstance(v, str) and (m := re.search(r"\d+(?:\.\d+)?", v)):
        v = float(m.group())
    if isinstance(v, int | float) and v > 0:
        return round(float(v), 1)
    return None


def _flag(v: Any) -> Any:
    if isinstance(v, str):
        return v.strip().lower() in ("true", "yes", "1", "是")
    return bool(v)


Flag = Annotated[bool, BeforeValidator(_flag)]


class WrittenLine(BaseModel):
    type: Annotated[LineType, BeforeValidator(_type)] = "action"
    character: Text = Field(default="", validation_alias=AliasChoices("character", "who"))
    tone: Text = ""
    text: Text = Field(default="", validation_alias=AliasChoices("text", "line", "content"))
    mood: Text = ""
    seconds: Annotated[float | None, BeforeValidator(_seconds)] = None
    paras: list[Number] = Field(default_factory=list)
    adds: list[Number] = Field(default_factory=list)
    added: Flag = Field(default=False, validation_alias=AliasChoices("added", "ai_added"))
    cliffhanger: Flag = False


class WrittenScene(BaseModel):
    heading: Text = ""
    time: Text = Field(default="", validation_alias=AliasChoices("time", "time_of_day"))
    location: Text = Field(default="", validation_alias=AliasChoices("location", "place"))
    paras: list[Number] = Field(default_factory=list)
    lines: list[WrittenLine] = Field(default_factory=list)


class ScriptAnswer(BaseModel):
    scenes: list[WrittenScene] = Field(default_factory=list)


class RewriteOut(BaseModel):
    text: Text


# --------------------------------------------------------------------------- inputs

# (kind, entity id, normalized name and aliases) of the bible's people and places.
Names = list[tuple[str, str, set[str]]]


def names_of(payload: Mapping[str, Any]) -> Names:
    out: Names = []
    for e in payload.get("entities") or []:
        if e["kind"] in ("character", "location"):
            keys = {bible_ops.normalize(n) for n in [e["name"], *(e.get("aliases") or [])]}
            out.append((e["kind"], e["id"], {k for k in keys if k}))
    return out


def resolve(names: Names, kind: str, text: str | None) -> str | None:
    """The bible entry a written name means: the same name or alias, else one inside it
    (「夜　内　林晚出租屋」 is 林晚出租屋, 「林晚（OS）」 is 林晚)."""
    key = bible_ops.normalize(text or "")
    if not key:
        return None
    of_kind = [(i, keys) for k, i, keys in names if k == kind]
    for entity_id, keys in of_kind:
        if key in keys:
            return entity_id
    best: tuple[int, str] | None = None
    for entity_id, keys in of_kind:
        for k in keys:
            if len(k) >= 2 and k in key and (best is None or len(k) > best[0]):
                best = (len(k), entity_id)
    return best[1] if best else None


def used_entities(
    payload: Mapping[str, Any], paras: Iterable[int], text: str
) -> list[dict[str, Any]]:
    """The entries an episode uses: found in its paragraphs, or a person, place or prop named
    in its text (paragraphs and additions)."""
    wanted = set(paras)
    plain = bible_ops.normalize(text)
    out = []
    for e in payload.get("entities") or []:
        named = e["kind"] in ("character", "location", "prop") and any(
            (k := bible_ops.normalize(n)) and k in plain
            for n in [e["name"], *(e.get("aliases") or [])]
        )
        if named or wanted & set(e.get("paras") or []):
            out.append(e)
    return out


def entities_text(entities: Sequence[Mapping[str, Any]]) -> str:
    lines = []
    for e in entities:
        kind = bible_ops.KIND_LABEL.get(e["kind"], e["kind"])
        aliases = e.get("aliases") or []
        also = f"（又名：{'、'.join(aliases)}）" if aliases else ""
        summary = str((e.get("data") or {}).get("summary") or "")
        lines.append(f"{kind}「{e['name']}」{also}{('：' + summary) if summary else ''}")
    return "\n".join(lines)


def episode_text(e: Mapping[str, Any]) -> str:
    lines = [f"第 {e['idx']} 集《{e.get('title') or ''}》"]
    if e.get("hook"):
        lines.append(f"开头钩子：{e['hook']}")
    if e.get("cliffhanger"):
        lines.append(f"结尾卡点：{e['cliffhanger']}")
    facts = []
    if e.get("target_seconds"):
        facts.append(f"预计时长：{e['target_seconds']} 秒")
    if e.get("scene_count"):
        facts.append(f"预计场数：{e['scene_count']}")
    if facts:
        lines.append("；".join(facts))
    return "\n".join(lines)


def _cite(paras: Iterable[int]) -> str:
    return "、".join(f"P{p + 1}" for p in paras)


def beats_text(e: Mapping[str, Any]) -> str:
    return "\n".join(
        f"{n}. {b['text']}" + (f"（{_cite(b['paras'])}）" if b.get("paras") else "")
        for n, b in enumerate(e.get("beats") or [], 1)
    )


def number_additions(
    accepted: Iterable[Mapping[str, Any]], paras: Sequence[int]
) -> dict[int, dict[str, Any]]:
    """The accepted additions on these paragraphs, numbered 1… in reading order (【补写n】)."""
    order = {p: i for i, p in enumerate(paras)}
    picked = sorted(
        (a for a in accepted if int(a["para_idx"]) in order),
        key=lambda a: order[int(a["para_idx"])],
    )
    return {n: dict(a) for n, a in enumerate(picked, 1)}


def source_text(
    book: Book, paras: Sequence[int], additions: Mapping[int, Mapping[str, Any]]
) -> str:
    """The cited paragraphs by chapter, each with its numbered additions."""
    wanted = set(paras)
    parts = []
    for c in book.chapters:
        mine = [p for p in book.paragraphs(c) if p in wanted]
        if not mine:
            continue
        lines = [Piece(c, mine).heading()]
        for p in mine:
            extra = "".join(
                f"【补写{n}】{a['text']}" for n, a in additions.items() if int(a["para_idx"]) == p
            )
            lines.append(f"[P{p + 1}] {book.paragraph(p)}{extra}")
        parts.append("\n".join(lines))
    return "\n\n".join(parts)


async def gather(
    session: AsyncSession,
    invalidation: Invalidation,
    novel: NovelService,
    series_id: str,
    episode_id: str,
) -> Inputs:
    """What episode ``episode_id``'s script is written from, and the slices that were read
    (the component's ``inputs``; the demo seed builds its version from the same)."""
    split = await split_product(session, series_id)
    plan = (
        await session.get(ProductVersion, split.adopted_version_id)
        if split is not None and split.adopted_version_id
        else None
    )
    episode = episode_ops.find_episode(plan.payload_json, episode_id) if plan else None
    if split is None or episode is None:
        raise PipelineError(409, "upstream_not_ready", slot="episodes")
    book = await novel.book(session, series_id)
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

    cited = {p for b in episode.get("beats") or [] for p in b.get("paras") or []}
    paras = sorted(p for p in cited if p in book.offsets)
    deps = [await invalidation.dependency(session, split.id, f"episode:{episode_id}")]
    chapters = sorted({c.idx for c in book.chapters if set(book.paragraphs(c)) & cited})
    for idx in chapters:
        deps.append(await invalidation.dependency(session, book.product_id, f"chapter:{idx}"))
    additions: dict[int, dict[str, Any]] = {}
    enrich = await adopted_additions(session, series_id, novel, book)
    if enrich is not None:
        enrich_id, accepted = enrich
        deps.append(await invalidation.dependency(session, enrich_id, adopted_slice(paras)))
        additions = number_additions(accepted, paras)
    text = " ".join([*(book.paragraph(p) for p in paras), *(a["text"] for a in additions.values())])
    entities = used_entities(adopted.payload_json, paras, text)
    ids = ",".join(sorted(e["id"] for e in entities))
    deps.append(await invalidation.dependency(session, bible.id, f"entities:{ids}"))

    blocks = [Block("本集", episode_text(episode)), Block("节拍", beats_text(episode))]
    if entities:
        blocks.append(Block("设定", entities_text(entities)))
    blocks.append(Block("原文", source_text(book, paras, additions)))
    return Inputs(
        blocks=blocks,
        deps=deps,
        episode_id=episode_id,
        context={
            "book": book,
            "episode": episode,
            "paras": paras,
            "additions": additions,
            "names": names_of(adopted.payload_json),
        },
    )


# --------------------------------------------------------------------------- the answer


def time_of(text: str) -> str | None:
    return _TIMES.get(text.strip().lower()) if text else None


def _spans(book: Book, paras: Iterable[int]) -> list[dict[str, Any]]:
    return [s for p in paras if (s := book.span(p)) is not None]


def addition_span(a: Mapping[str, Any]) -> dict[str, Any]:
    return {"source_id": f"{ops.ADDITION_SOURCE}{a['id']}", "start": 0, "end": len(a["text"])}


def collect(answer: ScriptAnswer, context: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The answer's scenes (without ids): paragraph numbers outside the episode are dropped
    (0-based after), a line's additions become ``sug:`` spans, names become bible ids. Lines
    without text and scenes without lines are dropped; exactly one line is the 卡点 (the last
    the model marked, else the last line)."""
    book: Book = context["book"]
    allowed = set(context["paras"])
    additions: Mapping[int, Mapping[str, Any]] = context["additions"]
    names: Names = context["names"]
    scenes: list[dict[str, Any]] = []
    for s in answer.scenes:
        lines: list[dict[str, Any]] = []
        for w in s.lines:
            text = w.text.strip()
            if not text:
                continue
            picked = [additions[n] for n in dict.fromkeys(w.adds) if n in additions]
            paras = sorted(
                {p - 1 for p in w.paras if p - 1 in allowed} | {int(a["para_idx"]) for a in picked}
            )
            name = w.character.strip() or None
            lines.append(
                {
                    "type": w.type,
                    "character_id": resolve(names, "character", name),
                    "character_name": name,
                    "tone": w.tone.strip() or None,
                    "text": text,
                    "mood": w.mood.strip() or None,
                    "duration_s": w.seconds,
                    "overlay_shot": None,
                    "paras": paras,
                    "source_spans": _spans(book, paras) + [addition_span(a) for a in picked],
                    "ai_added": w.added,
                    "cliffhanger": w.cliffhanger,
                }
            )
        if not lines:
            continue
        paras = sorted({p - 1 for p in s.paras if p - 1 in allowed}) or sorted(
            {p for line in lines for p in line["paras"]}
        )
        time = time_of(s.time)
        place = s.location.strip()
        heading = ops.plain_heading(s.heading) or "　".join(
            x for x in (TIME_LABEL.get(time or ""), place) if x
        )
        scenes.append(
            {
                "heading": heading or "场景",
                "time_of_day": time,
                "location_id": resolve(names, "location", place or heading),
                "paras": paras,
                "source_spans": _spans(book, paras),
                "lines": lines,
            }
        )
    flagged = [line for s in scenes for line in s["lines"] if line["cliffhanger"]]
    for line in flagged[:-1]:
        line["cliffhanger"] = False
    if not flagged and scenes:
        scenes[-1]["lines"][-1]["cliffhanger"] = True
    return scenes


def payload_of(book: Book, episode_id: str, scenes: list[dict[str, Any]]) -> dict[str, Any]:
    return {"source_id": book.source.id, "episode_id": episode_id, "scenes": scenes}


# --------------------------------------------------------------------------- rewrites


def line_label(line: Mapping[str, Any]) -> str:
    """A line as the rewrite prompt shows it."""
    who = line.get("character_name") or ""
    tone = f"（{line['tone']}）" if line.get("tone") else ""
    rows = [f"类型：{LINE_LABEL.get(line['type'], line['type'])}"]
    if who or tone:
        rows.append(f"人物：{who}{tone}")
    rows.append(f"内容：{line['text']}")
    return "\n".join(rows)


def scene_text(scene: Mapping[str, Any]) -> str:
    rows = [str(scene["heading"])]
    for line in scene.get("lines") or []:
        if line["type"] in ("dialogue", "vo"):
            tone = f"（{line['tone']}）" if line.get("tone") else ""
            rows.append(f"{line.get('character_name') or ''}{tone}：{line['text']}")
        elif line["type"] == "sfx":
            rows.append(f"【音效】{line['text']}")
        else:
            rows.append(f"△ {line['text']}")
    return "\n".join(rows)


# --------------------------------------------------------------------------- the component


class ScriptComponent(Component):
    id = "script"
    slot = "script"
    owner_type = "episode"
    max_tokens = 6000

    def __init__(
        self, services: Services, novel: NovelService, budget: Budget | None = None
    ) -> None:
        super().__init__(services)
        self.novel = novel
        self.budget = budget

    async def inputs(self, session: AsyncSession, product: Product) -> Inputs:
        inputs = await gather(
            session, self.services.invalidation, self.novel, product.series_id, product.owner_id
        )
        base = None
        if product.adopted_version_id:
            v = await session.get(ProductVersion, product.adopted_version_id)
            base = v.payload_json if v is not None else None
        inputs.context["base"] = base
        return inputs

    def output_schema(self) -> type[BaseModel]:
        return ScriptAnswer

    def mock_responders(self) -> dict[str, Responder]:
        return {
            "run": mock_script,
            "rewrite_line": mock_rewrite_line,
            "rewrite_scene": mock_rewrite_scene,
        }

    async def build_payload(
        self, output: BaseModel, inputs: Inputs, ctx: RunContext
    ) -> dict[str, Any]:
        scenes = collect(cast(ScriptAnswer, output), inputs.context)
        if not scenes:
            raise ComponentError("no_scenes")
        book: Book = inputs.context["book"]
        episode_id = str(inputs.context["episode"]["id"])
        return payload_of(book, episode_id, ops.reconcile(scenes, inputs.context["base"]))

    # ------------------------------------------------------------------ rewrite

    async def rewrite(
        self,
        product: Product,
        payload: Mapping[str, Any],
        block_id: str,
        *,
        model: str | None,
        instruction: str | None,
        confirm_budget: bool,
    ) -> tuple[str, str]:
        """「重写这一段」 (the route's model) / 「换模型重写」 (``model``) of a line or a scene
        heading: (proposed text, model key); nothing is saved. Over the per-call cap or the
        episode's budget without the user's yes → 409 ``over_budget``."""
        compiler = self.services.compiler
        registry = self.services.registry
        settings = await self.services.router.settings(self.id)
        if model is None:
            try:
                model = Router.primary_model(settings)
            except ModelError as exc:
                raise PipelineError(409, exc.code) from None
        try:
            registry.spec(model)
        except ModelError:
            raise PipelineError(422, "unknown_model", key=model) from None
        scene = ops.find_scene(payload, block_id)
        found = ops.find_line(payload, block_id)
        if scene is None and found is None:
            raise PipelineError(404, "line_not_found", id=block_id)
        async with self.services.db.session() as session:
            book = await self.novel.book_of(session, str(payload.get("source_id")))
        if found is not None:
            scene, line = found
            task, paras = "rewrite_line", line.get("paras") or scene.get("paras") or []
            target = Block("这一行", line_label(line))
        else:
            assert scene is not None
            task, paras = "rewrite_scene", scene.get("paras") or []
            target = Block("场景标题", str(scene["heading"]))
        blocks = [Block("本场", scene_text(scene)), target]
        if book is not None and paras:
            blocks.append(
                Block("原文", "\n".join(f"[P{p + 1}] {book.paragraph(p)}" for p in paras))
            )
        if instruction and instruction.strip():
            blocks.append(Block("修改要求", instruction.strip()))
        intent = str((product.prompt_json or {}).get("intent") or "")
        intent = intent or compiler.default_intent(self.id)
        messages = compiler.messages(compiler.render(f"script/{task}.j2", intent=intent), blocks)
        req = self.request(messages, None, task, REWRITE_MAX_TOKENS)
        estimate = registry.get(model).estimate(req)
        cost = estimate.cost_usd
        await self._check_budget(
            cost, settings, product.owner_id, confirm_budget, priced=estimate.priced
        )
        ctx = RunContext(
            product=product,
            mode="rewrite",
            model_key=model,
            seed=random.randrange(1, 2**31),
            intent=intent,
            compiled="",
            compiled_overridden=False,
            confirmed_usd=cost if confirm_budget else None,
        )
        try:
            result = await self.call_json(
                ctx,
                messages,
                RewriteOut,
                product.owner_id,
                task=task,
                max_tokens=REWRITE_MAX_TOKENS,
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
        text = cast(RewriteOut, result.data).text.strip()
        if task == "rewrite_scene":
            text = ops.plain_heading(text)
        if not text:
            raise PipelineError(502, "invalid_output", errors="empty")
        return text, result.model_key

    async def _check_budget(
        self, cost: float, settings: Any, episode_id: str, confirmed: bool, *, priced: bool
    ) -> None:
        if confirmed:
            return
        cap = cap_of(settings)
        if self.budget is not None:
            verdict = await self.budget.before_enqueue(
                cost, cap=cap, episode_id=episode_id, priced=priced
            )
            if not verdict.ok:
                raise PipelineError(409, "over_budget", **verdict.params())
        elif not priced:
            raise PipelineError(
                409, "over_budget", reason="unpriced", estimate_usd=0.0, limit_usd=None
            )
        elif cap is not None and cost > cap + EPSILON:
            raise PipelineError(
                409, "over_budget", reason="per_call", estimate_usd=round(cost, 4), limit_usd=cap
            )


# --------------------------------------------------------------------------- Mock mode

_PARA = re.compile(r"^\[P(\d+)\] (.*)$")
_ADDITION = re.compile(r"【补写(\d+)】")
_BEAT = re.compile(r"^(\d+)\. (.*?)(?:（((?:P\d+、?)+)）)?$")
_SCENES = re.compile(r"预计场数：(\d+)")
_QUOTE = re.compile(r"“(.+?)”")
_SECTION = re.compile(r"^\[(.+)\]$")


@cache
def demo_fixture() -> dict[str, Any] | None:
    if not DEMO_FIXTURE.is_file():
        return None
    data: dict[str, Any] = json.loads(DEMO_FIXTURE.read_text(encoding="utf-8"))
    return data


def _sections(text: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in text.splitlines():
        if (m := _SECTION.match(line)) and not _PARA.match(line) and not line.startswith("[第 "):
            current = out.setdefault(m.group(1), [])
        elif current is not None and line.strip():
            current.append(line)
    return out


def _paragraphs(lines: Iterable[str]) -> dict[int, tuple[str, list[tuple[int, str]]]]:
    """[P n] → (paragraph, [(addition number, text)])."""
    out: dict[int, tuple[str, list[tuple[int, str]]]] = {}
    for line in lines:
        if not (m := _PARA.match(line)):
            continue
        parts = _ADDITION.split(m.group(2))
        adds = [(int(parts[i]), parts[i + 1]) for i in range(1, len(parts) - 1, 2)]
        out[int(m.group(1))] = (parts[0], adds)
    return out


def _strip_ids(scene: Mapping[str, Any]) -> dict[str, Any]:
    lines = [
        {k: v for k, v in x.items() if k not in ("id", "overlay_shot")} for x in scene["lines"]
    ]
    return {**{k: v for k, v in scene.items() if k != "id"}, "lines": lines}


def demo_entry(paras: Iterable[int]) -> dict[str, Any] | None:
    """The fixture's episode whose beats cite exactly these paragraphs (1-based)."""
    demo = demo_fixture()
    wanted = set(paras)
    return next((e for e in (demo or {}).get("episodes", []) if set(e["paras"]) == wanted), None)


def mock_script(req: ModelRequest) -> dict[str, Any]:
    sections = _sections(user_text(req))
    paras = _paragraphs(sections.get("原文", []))
    if is_demo({n: t for n, (t, _) in paras.items()}) and (entry := demo_entry(paras)):
        return {"scenes": [_strip_ids(s) for s in entry["scenes"]]}
    return _rules(sections, paras)


def _rules(
    sections: Mapping[str, list[str]], paras: Mapping[int, tuple[str, list[tuple[int, str]]]]
) -> dict[str, Any]:
    """Any other episode: its beats in ``预计场数`` scenes (one per three beats without it); each
    cited paragraph an action line, its quotes dialogue lines of the first person it names, each
    addition a line of its own; the last line the cliffhanger."""
    beats = []
    for line in sections.get("节拍", []):
        if m := _BEAT.match(line):
            cited = [int(n) for n in re.findall(r"\d+", m.group(3) or "")]
            beats.append((m.group(2), [p for p in cited if p in paras]))
    if not beats:
        return {"scenes": []}
    people = [m.group(1) for x in sections.get("设定", []) if (m := re.match(r"^人物「(.+?)」", x))]
    places = [m.group(1) for x in sections.get("设定", []) if (m := re.match(r"^地点「(.+?)」", x))]
    planned = next(
        (int(m.group(1)) for x in sections.get("本集", []) if (m := _SCENES.search(x))), 0
    )
    count = max(1, min(planned or math.ceil(len(beats) / 3), len(beats)))
    size = math.ceil(len(beats) / count)
    scenes: list[dict[str, Any]] = []
    for group in (beats[i : i + size] for i in range(0, len(beats), size)):
        cited = list(dict.fromkeys(p for _, ps in group for p in ps))
        text = "".join(paras[p][0] for p in cited)
        place = next((x for x in places if x in text), "")
        lines: list[dict[str, Any]] = []
        for p in cited:
            body, adds = paras[p]
            who = next((x for x in people if x in body), "")
            action = _QUOTE.sub("", body).strip("，。：: ")
            if action:
                lines.append({"type": "action", "text": action[:60], "seconds": 3, "paras": [p]})
            for q in _QUOTE.findall(body):
                lines.append(
                    {"type": "dialogue", "character": who, "text": q, "seconds": 3, "paras": [p]}
                )
            for n, extra in adds:
                lines.append(
                    {"type": "action", "text": extra, "seconds": 2, "paras": [p], "adds": [n]}
                )
        if not lines:  # beats that cite nothing
            lines = [{"type": "action", "text": t, "seconds": 3, "added": True} for t, _ in group]
        scenes.append(
            {
                "heading": f"日　内　{place or '场景'}",
                "time": "day",
                "location": place,
                "paras": cited,
                "lines": lines,
            }
        )
    scenes[-1]["lines"][-1]["cliffhanger"] = True
    return {"scenes": scenes}


def _content(sections: Mapping[str, list[str]], title: str, prefix: str = "") -> str:
    for line in sections.get(title, []):
        if line.startswith(prefix):
            return line[len(prefix) :]
    return ""


def _demo_rewrite(text: str) -> str | None:
    demo = demo_fixture() or {}
    for e in demo.get("episodes", []):
        for s in e["scenes"]:
            if s["heading"] == text:
                return str(demo.get("rewrites", {}).get(s["id"]) or "") or None
            for line in s["lines"]:
                if line["text"] == text:
                    return str(demo.get("rewrites", {}).get(line["id"]) or "") or None
    return None


def mock_rewrite_line(req: ModelRequest) -> dict[str, Any]:
    text = _content(_sections(user_text(req)), "这一行", "内容：")
    return {"text": _demo_rewrite(text) or f"{text.rstrip('。')}——换个说法。"}


def mock_rewrite_scene(req: ModelRequest) -> dict[str, Any]:
    heading = _content(_sections(user_text(req)), "场景标题")
    return {"text": _demo_rewrite(heading) or f"{heading} · 另一角"}


def demo_payload(inputs: Inputs) -> dict[str, Any] | None:
    """A demo episode's script as a run makes it from ``inputs`` (``gather``), with the
    fixture's ids and its 叠在镜头上的旁白 (``overlay_shot``, a display field). None when the
    fixture has no script for the episode."""
    context = inputs.context
    entry = demo_entry(p + 1 for p in context["paras"])
    if entry is None:
        return None
    answer = ScriptAnswer.model_validate({"scenes": [_strip_ids(s) for s in entry["scenes"]]})
    scenes = collect(answer, context)
    base = {
        "scenes": [
            {"id": s["id"], "lines": [{"id": x["id"], "text": x["text"]} for x in s["lines"]]}
            for s in entry["scenes"]
        ]
    }
    scenes = ops.reconcile(scenes, base)
    overlays = {
        x["id"]: x["overlay_shot"]
        for s in entry["scenes"]
        for x in s["lines"]
        if x.get("overlay_shot")
    }
    for s in scenes:
        for line in s["lines"]:
            line["overlay_shot"] = overlays.get(line["id"])
    book: Book = context["book"]
    return payload_of(book, str(context["episode"]["id"]), scenes)
