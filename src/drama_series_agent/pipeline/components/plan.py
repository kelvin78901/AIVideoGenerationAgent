"""分镜规划 (SPEC 5 ``plan``): an episode's script cut into shots. The output is the
``shot_plan`` product, owned by the episode; its adopted version is mirrored into ``shot``.

The model writes each shot: the lines it films, its type, framing, camera move, the first
frame's picture, its references, sound, a top view and a difficulty. Rules then make the answer
whole (``shots.ops.normalize``): every line filmed, spoken ones once, the first shot of a scene
never continuous, a continuous shot following the right shot, ids carried over from the adopted
plan.

The version depends on:
- the script's ``shots`` slice (as 素材分析's ``assets``): scenes, cast, speakers and action
  lines, not dialogue text, so rewording a line never makes the plan stale (Kelvin 2026-10-21);
- the asset list's ids, kinds and names (its references), once the episode was analysed.

确认并同步 never redoes it on its own (``cascade_rerun = False``): a new plan would overwrite
the user's framing, blocking and confirmed shots, so it is only marked 待更新 (Kelvin
2026-10-21).

Mock mode: the demo's episode 1 is answered from ``tests/fixtures/demo/plan.json`` (the demo
seed is built from the same file); any other script gets one shot per line by rules.
"""

from __future__ import annotations

import json
import re
from functools import cache
from typing import Any, cast

from pydantic import BaseModel, Field
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from drama_series_agent.assets import ops as asset_ops
from drama_series_agent.core.models_db import Asset, AssetUse, Episode, Product, ProductVersion
from drama_series_agent.core.paths import REPO_ROOT
from drama_series_agent.episodes.service import script_product
from drama_series_agent.modelhub.adapters.base import ModelRequest
from drama_series_agent.modelhub.adapters.mock import Responder
from drama_series_agent.pipeline.component import Component, ComponentError, Inputs, RunContext
from drama_series_agent.pipeline.components.assets import asset_list_product, is_demo_episode
from drama_series_agent.pipeline.components.chunks import user_text
from drama_series_agent.pipeline.components.media import output_frame
from drama_series_agent.pipeline.errors import PipelineError
from drama_series_agent.pipeline.invalidation import Invalidation
from drama_series_agent.prompts.compiler import Block
from drama_series_agent.shots import ops

DEMO_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "demo" / "plan.json"
SHOT_PLAN_SLOT = "shot_plan"
SCRIPT_SHOTS_SLICE = "shots"
ASSET_IDS_SLICE = "ids"
_VERTICAL = {"9:16": "竖屏", "3:4": "竖屏"}


class PlannedShot(BaseModel):
    scene: int | None = None
    lines: list[int] = Field(default_factory=list)
    type: str = ""
    framing: str = ""
    move: str = ""
    seconds: float | None = None
    picture: str = ""
    summary: str = ""
    refs: list[str] = Field(default_factory=list)
    audio: str = ""
    sound: str | None = None
    blocking: list[dict[str, Any]] = Field(default_factory=list)
    continues: int | None = None
    note: str | None = None
    difficulty: int | None = None


class PlanAnswer(BaseModel):
    shots: list[PlannedShot] = Field(default_factory=list)


async def asset_list_slicer(
    session: AsyncSession, product: Product, version: ProductVersion, name: str
) -> Any:
    """``ids`` (分镜规划's references): each asset's id, kind and name, not its description, so
    describing an asset again never makes the plan stale. Any other name is a key of the
    payload."""
    if name == ASSET_IDS_SLICE:
        return [
            {"id": a.get("id"), "kind": a.get("kind"), "name": a.get("name")}
            for a in asset_ops.assets_of(version.payload_json)
        ]
    return version.payload_json if name == "" else version.payload_json.get(name)


async def plan_product(session: AsyncSession, episode_id: str) -> Product | None:
    query = select(Product).where(
        Product.owner_type == "episode",
        Product.owner_id == episode_id,
        Product.slot == SHOT_PLAN_SLOT,
    )
    return (await session.exec(query)).first()


async def episode_assets(
    session: AsyncSession, episode_id: str
) -> tuple[dict[str, Asset], list[AssetUse]]:
    """The assets the episode's asset analysis found, and where (its 出场矩阵)."""
    uses = list(
        (await session.exec(select(AssetUse).where(AssetUse.episode_id == episode_id))).all()
    )
    ids = sorted({u.asset_id for u in uses})
    rows = await session.exec(
        select(Asset).where(col(Asset.id).in_(ids), col(Asset.retired).is_(False))
    )
    return {a.id: a for a in rows.all()}, uses


def plan_context(
    episode_id: str,
    script: dict[str, Any],
    assets: dict[str, Asset],
    uses: list[AssetUse],
) -> ops.PlanContext:
    lines = [
        ops.PlanLine(n=x.n, scene_id=x.scene_id, line_id=x.line_id, type=x.type, text=x.text)
        for x in asset_ops.numbered_lines(script)
    ]
    line_assets: dict[str, list[str]] = {}
    scene_assets: dict[str, list[str]] = {}
    for u in sorted(uses, key=lambda u: (u.scene_id, u.asset_id)):
        if u.asset_id not in assets:
            continue
        if u.line_ids_json:
            for x in u.line_ids_json:
                line_assets.setdefault(x, []).append(u.asset_id)
        elif assets[u.asset_id].kind == "scene":
            scene_assets.setdefault(u.scene_id, []).append(u.asset_id)
    return ops.PlanContext(
        episode_id=episode_id,
        scene_ids=[str(s["id"]) for s in script.get("scenes") or []],
        lines=lines,
        asset_kinds={a.id: a.kind for a in assets.values()},
        asset_names={a.id: a.name for a in assets.values()},
        line_assets=line_assets,
        scene_assets=scene_assets,
    )


def assets_text(ctx: ops.PlanContext) -> str:
    """[素材]: id, kind, name and the lines it is on."""
    numbers = {x.line_id: x.n for x in ctx.lines}
    on: dict[str, list[int]] = {}
    for line_id, ids in ctx.line_assets.items():
        for a in ids:
            on.setdefault(a, []).append(numbers.get(line_id, 0))
    rows = []
    for a, kind in ctx.asset_kinds.items():
        where = sorted(n for n in on.get(a, []) if n)
        at = "、".join(f"L{n}" for n in where) if where else "整场"
        rows.append(f"{a}　{kind}　{ctx.asset_names.get(a, '')}　出现在：{at}")
    return "\n".join(rows)


def script_text(script: dict[str, Any]) -> str:
    """[剧本] as the plan reads it: scene headings, numbered lines, a voice-over marked as one."""
    rows: list[str] = []
    n = 0
    for k, scene in enumerate(script.get("scenes") or [], 1):
        rows.append(f"[场 {k}] {scene.get('heading') or ''}")
        for line in scene.get("lines") or []:
            n += 1
            who = line.get("character_name") or ""
            tone = str(line.get("tone") or "")
            text = line.get("text") or ""
            if line.get("type") == "vo":
                extra = f"，{tone}" if tone and tone.upper() != "OS" else ""
                rows.append(f"L{n} {who}（画外音{extra}）：{text}")
            elif line.get("type") == "dialogue":
                rows.append(f"L{n} {who}{f'（{tone}）' if tone else ''}：{text}")
            else:
                rows.append(f"L{n} △ {text}")
    return "\n".join(rows)


async def gather(
    session: AsyncSession, invalidation: Invalidation, series_id: str, episode_id: str
) -> Inputs:
    """What episode ``episode_id``'s shot plan is made from, and the slices that were read."""
    script = await script_product(session, episode_id)
    adopted = (
        await session.get(ProductVersion, script.adopted_version_id)
        if script is not None and script.adopted_version_id
        else None
    )
    if script is None or adopted is None:
        raise PipelineError(409, "upstream_not_ready", slot="script")
    deps = [await invalidation.dependency(session, script.id, SCRIPT_SHOTS_SLICE)]
    listed = await asset_list_product(session, episode_id)
    if listed is not None and listed.adopted_version_id:
        deps.append(await invalidation.dependency(session, listed.id, ASSET_IDS_SLICE))
    assets, uses = await episode_assets(session, episode_id)
    ctx = plan_context(episode_id, adopted.payload_json, assets, uses)
    mine = await plan_product(session, episode_id)
    base = (
        await session.get(ProductVersion, mine.adopted_version_id)
        if mine is not None and mine.adopted_version_id
        else None
    )
    episode = await session.get(Episode, episode_id)
    frame = await output_frame(session, series_id)
    aspect = frame["aspect"]
    title = f"第 {episode.idx} 集　{episode.title}" if episode is not None else episode_id
    blocks = [
        Block("本集", title),
        Block("画幅", f"{_VERTICAL.get(aspect, '横屏')} {aspect}"),
        Block("素材", assets_text(ctx) or "（还没做素材分析）"),
        Block("剧本", script_text(adopted.payload_json)),
    ]
    return Inputs(
        blocks=blocks,
        deps=deps,
        episode_id=episode_id,
        context={"plan": ctx, "base": base.payload_json if base is not None else None},
    )


def build(answer: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """The version payload from the model's answer (the demo seed calls this too)."""
    return ops.normalize(answer, context["plan"], context.get("base"))


class PlanComponent(Component):
    id = "plan"
    slot = SHOT_PLAN_SLOT
    owner_type = "episode"
    max_tokens = 6000
    cascade_rerun = False

    async def inputs(self, session: AsyncSession, product: Product) -> Inputs:
        return await gather(
            session, self.services.invalidation, product.series_id, product.owner_id
        )

    def output_schema(self) -> type[BaseModel]:
        return PlanAnswer

    def mock_responders(self) -> dict[str, Responder]:
        return {"run": mock_plan}

    async def build_payload(
        self, output: BaseModel, inputs: Inputs, ctx: RunContext
    ) -> dict[str, Any]:
        answer = cast(PlanAnswer, output).model_dump(mode="json")
        payload = build(answer, inputs.context)
        if not payload["shots"]:
            raise ComponentError("no_shots")
        return payload


# --------------------------------------------------------------------------- Mock mode

_SCENE = re.compile(r"^\[场 (\d+)\]", re.MULTILINE)
_LINE = re.compile(r"^L(\d+) (△ )?(.*)$", re.MULTILINE)


@cache
def demo_fixture() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(DEMO_FIXTURE.read_text(encoding="utf-8"))
    return data


def mock_plan(req: ModelRequest) -> dict[str, Any]:
    """The demo's episode 1 from the fixture; any other script one shot per line (a voice-over
    is left to the rules, which lay it over the shot before)."""
    text = user_text(req)
    if is_demo_episode(text):
        return dict(demo_fixture()["answer"])
    script = text.split("[剧本]", 1)[-1]
    shots: list[dict[str, Any]] = []
    scene = 0
    first = True
    for row in script.splitlines():
        if m := _SCENE.match(row):
            scene, first = int(m.group(1)), True
            continue
        m = _LINE.match(row)
        if m is None:
            continue
        n, action, rest = int(m.group(1)), bool(m.group(2)), m.group(3)
        if not action and "（画外音" in rest:
            continue
        shots.append(
            {
                "scene": scene,
                "lines": [n],
                "type": "scene_change" if first else "same_scene_cut",
                "framing": "wide" if first else "medium" if action else "close",
                "move": "static",
                "seconds": 3,
                "picture": rest if action else "",
                "summary": rest[:16],
            }
        )
        first = False
    return {"shots": shots}
