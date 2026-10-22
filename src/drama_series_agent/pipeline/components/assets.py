"""素材分析 (SPEC 5 ``assets``): what an episode needs made once and reused, and where it
appears. The output is the ``asset_list`` product, owned by the episode.

Rules over the adopted script and the bible give the characters, voices, scenes and bible props,
and where each one appears (``assets.ops.collect``). The model only writes descriptions and
finds props and on-screen text the rules miss (``assets.ops.merge``). Ids carry over across
reruns and across the series' episodes (``assets.ops.reconcile``).

The version depends on two things:
- the script's ``assets`` slice: scenes, cast, speakers and action lines, not dialogue text, so
  rewording a line does not make the list stale;
- the bible entries it used.

「重新分析剧本」 is the user asking for it, and the list only ever adds (what the user set on an
asset lives on the asset's product), so every run is adopted (``adopt_every_run``).

Mock mode: the demo's episode 1 is answered from ``tests/fixtures/demo/assets.json`` (the demo
seed is built from the same file). Any other script gets a plain description for each listed
asset, plus quoted text in action lines as on-screen text.
"""

from __future__ import annotations

import json
import re
from functools import cache
from typing import Any, cast

from pydantic import BaseModel, Field
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from drama_series_agent.assets import ops
from drama_series_agent.bible.service import bible_product
from drama_series_agent.core.models_db import Episode, Product, ProductVersion
from drama_series_agent.core.paths import REPO_ROOT
from drama_series_agent.episodes.service import script_product
from drama_series_agent.modelhub.adapters.base import ModelRequest
from drama_series_agent.modelhub.adapters.mock import Responder
from drama_series_agent.pipeline.component import Component, ComponentError, Inputs, RunContext
from drama_series_agent.pipeline.components.chunks import user_text
from drama_series_agent.pipeline.errors import PipelineError
from drama_series_agent.pipeline.invalidation import Invalidation
from drama_series_agent.prompts.compiler import Block

DEMO_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "demo" / "assets.json"
ASSET_LIST_SLOT = "asset_list"
SCRIPT_ASSETS_SLICE = "assets"


class TextSpec(BaseModel):
    exact: str
    style: str = "printed"
    method: str = "composite"


class FoundAsset(BaseModel):
    key: str | None = None
    kind: str | None = None
    name: str = ""
    description: str = ""
    lines: list[int] = Field(default_factory=list)
    text: TextSpec | None = None
    note: str | None = None


class AssetsAnswer(BaseModel):
    assets: list[FoundAsset] = Field(default_factory=list)


async def asset_list_product(session: AsyncSession, episode_id: str) -> Product | None:
    query = select(Product).where(
        Product.owner_type == "episode",
        Product.owner_id == episode_id,
        Product.slot == ASSET_LIST_SLOT,
    )
    return (await session.exec(query)).first()


async def known_assets(
    session: AsyncSession, series_id: str, episode_id: str
) -> list[dict[str, Any]]:
    """The assets of the series' adopted lists, this episode's first (ids carry over)."""
    rows = (
        await session.exec(
            select(Product).where(
                Product.series_id == series_id,
                Product.owner_type == "episode",
                Product.slot == ASSET_LIST_SLOT,
                col(Product.adopted_version_id).is_not(None),
            )
        )
    ).all()
    out: list[dict[str, Any]] = []
    for p in sorted(rows, key=lambda r: r.owner_id != episode_id):
        v = await session.get(ProductVersion, p.adopted_version_id)
        if v is not None:
            out.extend(ops.assets_of(v.payload_json))
    return out


def entities_text(entities: list[dict[str, Any]]) -> str:
    rows = []
    for e in entities:
        detail = ops.describe(e)
        rows.append(f"{e['name']}（{e.get('kind')}）{('：' + detail) if detail else ''}")
    return "\n".join(rows)


async def gather(
    session: AsyncSession, invalidation: Invalidation, series_id: str, episode_id: str
) -> Inputs:
    """What episode ``episode_id``'s asset list is made from, and the slices that were read."""
    script = await script_product(session, episode_id)
    adopted = (
        await session.get(ProductVersion, script.adopted_version_id)
        if script is not None and script.adopted_version_id
        else None
    )
    if script is None or adopted is None:
        raise PipelineError(409, "upstream_not_ready", slot="script")
    bible = await bible_product(session, series_id)
    bible_v = (
        await session.get(ProductVersion, bible.adopted_version_id)
        if bible is not None and bible.adopted_version_id
        else None
    )
    if bible is None or bible_v is None:
        raise PipelineError(409, "upstream_not_ready", slot="bible")
    payload, bible_payload = adopted.payload_json, bible_v.payload_json
    lines = ops.numbered_lines(payload)
    found = ops.collect(payload, bible_payload)
    entities = ops.entities_by_id(bible_payload)
    used = sorted({f.bible_id for f in found if f.bible_id})
    # Every main bible entry is shown, so the model can name what is coming up later.
    shown = [e for e in entities.values() if e.get("kind") in ("character", "location", "prop")]
    deps = [
        await invalidation.dependency(session, script.id, SCRIPT_ASSETS_SLICE),
        await invalidation.dependency(session, bible.id, f"entities:{','.join(used)}"),
    ]
    episode = await session.get(Episode, episode_id)
    title = f"第 {episode.idx} 集　{episode.title}" if episode is not None else episode_id
    blocks = [
        Block("本集", title),
        Block("已知素材", ops.known_text(found, lines) or "（无）"),
        Block("设定", entities_text(shown) or "（无）"),
        Block("剧本", ops.lines_text(payload, lines)),
    ]
    return Inputs(
        blocks=blocks,
        deps=deps,
        episode_id=episode_id,
        context={
            "episode_id": episode_id,
            "bible": bible_payload,
            "lines": lines,
            "found": found,
            "known": await known_assets(session, series_id, episode_id),
        },
    )


def build(answer: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """The version payload from the model's answer (the demo seed calls this too)."""
    merged = ops.merge(context["found"], answer, context["lines"], context["bible"])
    assets = ops.reconcile(merged, context["known"])
    return ops.payload_of(str(context["episode_id"]), assets)


class AssetsComponent(Component):
    id = "assets"
    slot = ASSET_LIST_SLOT
    owner_type = "episode"
    max_tokens = 4000
    adopt_every_run = True

    async def inputs(self, session: AsyncSession, product: Product) -> Inputs:
        return await gather(
            session, self.services.invalidation, product.series_id, product.owner_id
        )

    def output_schema(self) -> type[BaseModel]:
        return AssetsAnswer

    def mock_responders(self) -> dict[str, Responder]:
        return {"run": mock_assets}

    async def build_payload(
        self, output: BaseModel, inputs: Inputs, ctx: RunContext
    ) -> dict[str, Any]:
        answer = cast(AssetsAnswer, output).model_dump(mode="json")
        payload = build(answer, inputs.context)
        if not payload["assets"]:
            raise ComponentError("no_assets")
        return payload


# --------------------------------------------------------------------------- Mock mode

_KNOWN = re.compile(r"^(\S+:\S*)　(\S+)　(.+?)　出现在：", re.MULTILINE)
_ACTION = re.compile(r"^L(\d+) △ (.*)$", re.MULTILINE)
_QUOTED = re.compile(r"[“「]([^”」]{1,40})[”」]")


@cache
def demo_fixture() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(DEMO_FIXTURE.read_text(encoding="utf-8"))
    return data


def is_demo_episode(text: str) -> bool:
    return "楼下便利店，等你到十二点" in text and "……周屿？" in text


def mock_assets(req: ModelRequest) -> dict[str, Any]:
    """The demo's episode 1 from the fixture; any other script by rules."""
    text = user_text(req)
    if is_demo_episode(text):
        return dict(demo_fixture()["answer"])
    assets: list[dict[str, Any]] = [
        {"key": key, "description": f"{name}，按剧本里的样子。"}
        for key, _kind, name in _KNOWN.findall(text)
    ]
    for n, line in _ACTION.findall(text):
        for i, quoted in enumerate(_QUOTED.findall(line), 1):
            assets.append(
                {
                    "kind": "text",
                    "name": f"画面文字 L{n}" + (f"-{i}" if i > 1 else ""),
                    "description": "画面里看得清的字。",
                    "text": {"exact": quoted, "style": "printed", "method": "composite"},
                    "lines": [int(n)],
                }
            )
    return {"assets": assets}
