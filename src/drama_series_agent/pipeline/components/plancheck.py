"""分镜检查 by a model (M5.5, route ``plancheck``): what the rules (``shots/check.py``) cannot read
off the plan, such as a hesitation written as a repeated action, more actions than the shot's
budget, a start that does not follow from the shot before, or a state acted instead of set.

One product per episode (slot ``shot_check``), made when 「检查」 is asked
(``ShotService.run_checks``), depending on the whole adopted plan, so any edit to the plan marks
it stale. Its payload is ``{"issues": [Issue.as_json() …]}`` with ``source: "llm"``. Only a
warning: nothing waits on it (Kelvin 2026-11-10).

Mock mode: the demo's episode 1 gets the one issue the sketch shows (1-03); any other episode
none.
"""

from __future__ import annotations

from typing import Any, cast

from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from drama_series_agent.core.models_db import Episode, Product, ProductVersion
from drama_series_agent.episodes.service import script_product
from drama_series_agent.modelhub.adapters.base import ModelRequest
from drama_series_agent.modelhub.adapters.mock import Responder
from drama_series_agent.pipeline.component import Component, Inputs, RunContext
from drama_series_agent.pipeline.components.assets import is_demo_episode
from drama_series_agent.pipeline.components.chunks import user_text
from drama_series_agent.pipeline.components.plan import (
    episode_assets,
    plan_product,
    script_text,
)
from drama_series_agent.pipeline.errors import PipelineError
from drama_series_agent.prompts.compiler import Block
from drama_series_agent.shots import check, ops

SHOT_CHECK_SLOT = "shot_check"
CODES = (
    "undone",
    "repeat",
    "over_budget",
    "crowded",
    "insert_event",
    "replay",
    "inner_mouth",
    "state_jump",
    "other",
)
KIND_LABEL = {"performance": "表演", "action": "动作", "dialogue": "对白", "insert": "插入"}
HOW_LABEL = {"dialogue": "对白", "offscreen": "画外", "inner": "内心独白"}
MOCK_DEMO = {
    "issues": [
        {
            "shot": "1-03",
            "code": "insert_event",
            "text": "插入镜头写了「雨水把字一点点泡开」：状态变化应该摆好，不要在镜头里发生。",
        }
    ]
}


class FoundIssue(BaseModel):
    shot: str = ""  # its label (1-08)
    code: str = "other"
    text: str = ""


class CheckAnswer(BaseModel):
    issues: list[FoundIssue] = Field(default_factory=list)


async def gather(session: AsyncSession, product: Product, invalidation: Any) -> Inputs:
    """The episode's adopted plan (every shot with its contract) and script, and what the rules
    already found."""
    episode_id = product.owner_id
    episode = await session.get(Episode, episode_id)
    plan = await plan_product(session, episode_id)
    adopted = (
        await session.get(ProductVersion, plan.adopted_version_id)
        if plan is not None and plan.adopted_version_id
        else None
    )
    script = await script_product(session, episode_id)
    written = (
        await session.get(ProductVersion, script.adopted_version_id)
        if script is not None and script.adopted_version_id
        else None
    )
    if episode is None or plan is None or adopted is None or written is None:
        raise PipelineError(409, "upstream_not_ready", slot="shot_plan")
    from drama_series_agent.shots.service import pictured  # the service imports this module

    deps = [await invalidation.dependency(session, plan.id, "")]
    shots = await pictured(session, ops.shots_of(adopted.payload_json))
    labels = check.labels(episode.idx, shots)
    assets, _ = await episode_assets(session, episode_id)
    lines = check.script_lines(written.payload_json)
    contracts = check.contracts_of(shots, lines, {a.id: a.kind for a in assets.values()})
    found = check.check(shots, labels, lines, contracts)
    names = {a.id: a.name for a in assets.values()}
    blocks = [
        Block("剧本", script_text(written.payload_json)),
        Block("分镜", shots_text(shots, labels, contracts, names, lines)),
        Block(
            "规则已经发现",
            "\n".join(f"{labels.get(i.shot_id, '')} {i.code} {i.params}" for i in found)
            or "（没有）",
        ),
    ]
    return Inputs(
        blocks=blocks,
        deps=deps,
        episode_id=episode_id,
        context={"labels": labels},
    )


def shots_text(
    shots: list[dict[str, Any]],
    labels: dict[str, str],
    contracts: dict[str, dict[str, Any]],
    names: dict[str, str],
    lines: dict[str, check.LineInfo],
) -> str:
    """Each shot in the plan as the check reads it: its settings, picture and contract."""
    rows = []
    for s in shots:
        c = contracts.get(s["id"]) or {}
        said = "、".join(
            f"{lines[x].text[:12]}（{HOW_LABEL.get(how, how)}）"
            for x, how in (c.get("delivery") or {}).items()
            if x in lines
        )
        parts = [
            f"{labels.get(s['id'], '')} {s['shot_type']} {s['framing']} {s.get('camera_move')}",
            f"画面：{s.get('intent') or ''}",
            f"类型：{KIND_LABEL.get(str(c.get('kind')), c.get('kind'))}，"
            f"最多 {c.get('beats')} 个动作",
            "开始：" + "；".join(f"{x['subject']}{x['state']}" for x in c.get("start") or []),
            "结束：" + "；".join(f"{x['subject']}{x['state']}" for x in c.get("end") or []),
            "道具："
            + "；".join(
                f"{names.get(p['asset_id'], '')}{p['state']}" for p in c.get("props") or []
            ),
        ]
        if s.get("tail_from"):
            parts.append(f"接 {labels.get(str(s['tail_from']), '')}")
        if said:
            parts.append(f"台词：{said}")
        rows.append("\n  ".join(parts))
    return "\n".join(rows)


class PlanCheckComponent(Component):
    id = "plancheck"
    slot = SHOT_CHECK_SLOT
    owner_type = "episode"
    max_tokens = 2000
    cascade_rerun = False  # a check is asked for; 确认并同步 only marks it stale
    adopt_every_run = True  # the last check is the one shown (run 19: the second stayed unadopted)

    async def inputs(self, session: AsyncSession, product: Product) -> Inputs:
        return await gather(session, product, self.services.invalidation)

    def output_schema(self) -> type[BaseModel]:
        return CheckAnswer

    def mock_responders(self) -> dict[str, Responder]:
        return {"run": mock_check}

    async def build_payload(
        self, output: BaseModel, inputs: Inputs, ctx: RunContext
    ) -> dict[str, Any]:
        by_label = {label: sid for sid, label in inputs.context["labels"].items()}
        issues = []
        for x in cast(CheckAnswer, output).issues:
            sid = by_label.get(x.shot.strip())
            if sid is None or not x.text.strip():
                continue
            code = x.code if x.code in CODES else "other"
            issues.append(check.Issue(sid, code, {}, source="llm", text=x.text.strip()).as_json())
        return {"issues": issues}


def mock_check(req: ModelRequest) -> dict[str, Any]:
    return dict(MOCK_DEMO) if is_demo_episode(user_text(req)) else {"issues": []}
