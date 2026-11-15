"""关键帧 (SPEC 5 ``kf``): a shot's first frame, the picture its video starts from. One product
per shot that is not continuous (owner ``shot``, slot ``keyframe``; a continuous shot starts
from another shot's last frame instead).

- A run makes ``candidates`` pictures (3) in one version, as 参考图 does (M3): nothing is
  adopted until the user confirms the shot, which locks the picked one (``lock_pick``).
- **Hybrid** (SPEC 7.7, M3 step 5): 「重跑」 is the local draft; 「用 API 出终版」 is one picture
  on the API model from the picked draft (``params.source_version_id / source_idx``).
- **References only come from locked assets**: the shot's characters, scene, props and
  on-screen text, in that order, as many as the model takes; what is not locked is said in the
  prompt and not sent.
- The prompt says the framing, the camera move, the top view in words (who is where, where the
  camera is), the scene, the script's action lines it films and the on-screen text.
- The size comes from the output spec (hard rule 10), and the aspect is written in the prompt.
- **No locked picture, no edit model**: Qwen-Image-Edit 2511 only edits from references, so a
  draft of a shot with none goes to the next local model of ``components.yaml`` that draws from
  words (Qwen-Image; ``model_for``).

The version depends on the shot's settings (the plan's ``shot:<id>`` slice: type, framing, move,
blocking, references and lines, not its length or sound), the action lines it films
(``line:<id>``) and the locked pictures it used. A version drawn for another aspect is stale too
(``stale_aspect``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from drama_series_agent.assets.refs import MORE_KINDS, PURPOSE_LABEL, PURPOSES, REF_MORE
from drama_series_agent.core.config import Resolved, get_config
from drama_series_agent.core.models_db import (
    Asset,
    OutputSpecRow,
    Product,
    ProductVersion,
    Shot,
)
from drama_series_agent.episodes.service import script_product
from drama_series_agent.modelhub.adapters.base import Estimate, ModelError
from drama_series_agent.modelhub.adapters.mock import Responder
from drama_series_agent.modelhub.registry import Registry
from drama_series_agent.modelhub.workflows import (
    Workflow,
    has_workflow,
    load_workflow,
    spec_workflows_dir,
)
from drama_series_agent.pipeline import kfcheck, redraw
from drama_series_agent.pipeline.component import ComponentError, Inputs, RunContext
from drama_series_agent.pipeline.components.img import prop_physical, prop_text
from drama_series_agent.pipeline.components.media import (
    MediaComponent,
    candidate_files,
    frame_size,
    locked_ref,
    output_frame,
    prompt_text,
    ref_file,
)
from drama_series_agent.pipeline.components.plan import plan_product, shot_slice
from drama_series_agent.pipeline.components.text import text_settings
from drama_series_agent.pipeline.drafts import DependencyDraft, VersionDraft
from drama_series_agent.pipeline.errors import PipelineError
from drama_series_agent.pipeline.invalidation import Invalidation
from drama_series_agent.pipeline.pictures import (
    SHOT_PURPOSE_LABEL,
    SHOT_REFS,
    STYLE_BOARD,
    sets_of,
)
from drama_series_agent.pipeline.runs import item_of
from drama_series_agent.prompts.compiler import Block
from drama_series_agent.qa import ocr
from drama_series_agent.script import ops as script_ops
from drama_series_agent.shots import contract as contracts
from drama_series_agent.shots import ops
from drama_series_agent.shots.service import KEYFRAME_SLOT, prop_names, scene_place

REF_ORDER = ops.REF_KINDS
REF_SLOTS = ("ref_image", "text_image")
KIND_LABEL = {"character": "角色", "scene": "场景", "prop": "道具", "text": "画面文字"}
FRAMING = {"wide": "远景", "medium": "中景", "close": "近景", "closeup": "特写"}
MOVE = {"static": "固定机位", "push": "缓推", "follow": "跟拍", "pan": "摇镜"}
# A shot whose references have no character: said outright, or the model adds a stranger
# (1-02, the umbrella at the door: 5 of 6 drafts had a woman in them; 1 of 6 with this).
NO_PEOPLE = "这个镜头里没有人物，不要画人。"
# The physical world (M5 step 15o, Kelvin 2026-11-10): what a real camera in a real place sees.
REAL_WORLD = (
    "按真实世界实拍：人物和道具按真实尺寸和比例（长柄伞立着到人的胯部，便利贴手掌大小）；"
    "材质真实、有使用痕迹，不是产品图或 CG 渲染；光线来自画面里的光源；手写的字是手写笔迹，"
    "被雨打湿的地方颜色变深、墨迹微晕；人体自然（每只手五根手指），物体不互相穿插、不悬空。"
)
# 镜头契约 (M5.5): the keyframe is the shot's first moment, not a summary of it.
START_NOTE = "首帧画的是镜头开始的这一刻（不是整个镜头的概括）："
# Run 19 1-04: a second note in her hand beside the one on the umbrella.
PROPS_NOTE = "道具的状态是摆好的（每样道具画面里只有一件）："
SIZE_NOTE = "道具按真实尺寸画，和人物的比例要对："
INNER_NOTE = "{who}在心里说话（内心独白），嘴闭着，不是在开口说话。"
# The light of the scene's time (run 19: 1-04 and 1-09 lit like day in a night scene; 「夜」 was
# only one character of the heading, and the references were lit by day).
LIGHT = {
    "night": "夜里：窗外和门外是黑的（最多有远处的路灯），没有天光；光只来自画面里的灯"
    "（声控灯、台灯、手机屏幕），暗部多、对比强。",
    "day": "白天：天光从窗外或门外进来，室内比室外暗。",
    "dawn": "清晨：天刚亮，冷蓝色的天光，光线很弱。",
    "dusk": "黄昏：低角度的暖橙色天光，影子长。",
}
# The camera's side (run 19: 1-06 in 林晚出租屋 started with her outside the door; the keyframe
# put the camera in the stairwell, and the take shut her out).
PLACE_NOTE = "镜头在「{place}」里拍：机位在这个地方里面；有人在门外、窗外时，是从这里看过去的。"
FINAL_NOTE = "以参考图 1 的草稿为准，画得更精细：构图、人物、光线和颜色都不要改。"
LOCAL_REFS = 3  # a local workflow that does not say
# How big a prop is next to a person, in words (M5.5 step 9e-1): the 比例参考 picture drew the
# umbrella to her head and the note as big as her chest, and every keyframe copied it. Lengths
# in cm, the person about 165 cm tall.
_LENGTH = re.compile(r"(\d+(?:\.\d+)?)\s*(cm|厘米|公分|mm|毫米|m|米)(?![a-z])")
_UNIT_CM = {"cm": 1.0, "厘米": 1.0, "公分": 1.0, "mm": 0.1, "毫米": 0.1, "m": 100.0, "米": 100.0}
# A close-up of part of someone (M5.5 step 9e-2; run 19 1-05: her whole figure from its
# reference stood behind and a second hand came in front; 1-07: the phone held up to the lens,
# its screen away from her). Her own reference is left out: it is a whole person.
PART_VIEW = (
    "这是{who}身上局部的特写：从{who}的肩后（过肩）或她自己的视角拍；画面里只有{who}的手和小臂，"
    "从画面下方或侧边伸进来，看不到她的脸，也没有别的人。"
)
PART_LOOK = "{who}的手和衣袖照她的穿着（只画手和小臂）：{desc}"
# What someone looks at, turned to them (run 19 1-07: the screen faced the camera).
FACING_NOTE = (
    "{who}看着的东西（{things}），屏幕或写字的一面朝着{who}；要让观众看见上面的字，镜头就在{who}"
    "的肩后或身侧看过去，不要让{who}把它举起来对着镜头。"
)
_LOOKS = ("看", "盯", "读", "望", "瞥")
# The other side of a door or window (M5.5 step 9e-3; run 19 1-09: the door opened onto a street
# and the room behind her looked like a restaurant): the scene there, from the scenes' ``adjoins``,
# its picture sent too, when the shot says it is seen.
ACROSS = re.compile(r"门外|门口|开门|拉开|推开|推门|出门|进门|进屋|屋里|屋内|窗外|门后|门内")
ACROSS_NOTE = "{via}那边是「{name}」，照参考图里的它画，不另编{note}"


@dataclass(frozen=True)
class Across:
    """A scene seen through one of the shot's doors or windows."""

    asset_id: str
    name: str
    via: str
    note: str

    @property
    def label(self) -> str:
        return f"{self.via}那边：{self.name}"

    def text(self) -> str:
        return ACROSS_NOTE.format(
            via=self.via, name=self.name, note=f"：{self.note}" if self.note else "。"
        )


async def shot_space(
    session: AsyncSession, series_id: str, ids: list[str], said: str
) -> tuple[str | None, list[Across]]:
    """The shot's place (its one scene reference, else None: the scene heading's) and, when the
    shot says the other side is seen (``ACROSS``), the scenes through its doors and windows, either
    way round (the stairwell's ``adjoins`` names the flat, or the flat's the stairwell)."""
    assets = await asset_rows(session, ids)
    scenes = [a for a in (assets.get(i) for i in ids) if a is not None and a.kind == "scene"]
    if len(scenes) != 1:
        return None, []
    here = scenes[0]
    place = here.name.partition(" · ")[0].strip() or here.name
    if not ACROSS.search(said):
        return place, []
    others = (
        await session.exec(
            select(Asset).where(
                Asset.series_id == series_id,
                Asset.kind == "scene",
                Asset.id != here.id,
                col(Asset.retired).is_(False),
            )
        )
    ).all()

    def known(a: Asset) -> set[str]:
        return {a.id, a.name, str((a.seed_json or {}).get("key") or "")} - {""}

    out: list[Across] = []
    for x in (here.seed_json or {}).get("adjoins") or []:
        other = next((o for o in others if str(x.get("to") or "") in known(o)), None)
        if other is not None and other.id not in {a.asset_id for a in out}:
            via, note = str(x.get("via") or "门"), str(x.get("note") or "")
            out.append(Across(other.id, other.name, via, note))
    for o in others:
        for x in (o.seed_json or {}).get("adjoins") or []:
            if str(x.get("to") or "") in known(here) and o.id not in {a.asset_id for a in out}:
                out.append(Across(o.id, o.name, str(x.get("via") or "门"), ""))
    return place, out


def said_of(shot: dict[str, Any], contract: dict[str, Any] | None, lines: list[Any]) -> str:
    """What the shot says happens: its picture, its states and the script's action lines."""
    c = contract or {}
    return " ".join(
        [str(shot.get("intent") or "")]
        + [str(x.get("state") or "") for x in [*c.get("start", []), *c.get("end", [])]]
        + [str(x.get("text") if isinstance(x, dict) else getattr(x, "text", "")) for x in lines]
    )


_SMALL = ((3, "指尖大小"), (12, "手掌大小，比脸小"), (25, "和脸差不多大"), (45, "到前臂长"))
_TALL = (
    (60, "立着到人的膝盖"),
    (92, "立着到人的胯部"),
    (110, "立着到人的腰"),
    (130, "立着到人的胸口"),
)


def blocking_text(items: list[dict[str, Any]], in_shot: set[str] | None = None) -> str:
    """The top view in words, as the camera sees it: who is left or right, near or far.
    ``in_shot``: the ids and names of the shot's references. The top view is the whole scene's,
    so a character or prop the shot does not use is left out (named, a model draws someone
    else; M4 step 9); landmarks always stay."""
    camera = next((i for i in items if i.get("kind") == "camera"), None)
    cx, cy = (camera["x"], camera["y"]) if camera else (0.5, 1.0)
    rows = []
    for i in items:
        if i.get("kind") == "camera" or not i.get("label"):
            continue
        if (
            in_shot is not None
            and i.get("kind") in ("character", "prop")
            and not {i.get("id"), i.get("label")} & in_shot
        ):
            continue
        dx, depth = float(i["x"]) - cx, cy - float(i["y"])
        side = "画面左侧" if dx < -0.15 else "画面右侧" if dx > 0.15 else "画面中间"
        far = "，远处" if depth > 0.55 else "，近处" if depth < 0.25 else ""
        rows.append(f"{i['label']}在{side}{far}")
    if camera is not None:
        where = "偏左" if cx < 0.35 else "偏右" if cx > 0.65 else "正前方"
        rows.append(f"机位在{where}")
    return "；".join(rows)


def ref_limit(spec_caps_max: int | None, where: str, workflow: str | None) -> int | None:
    """How many reference pictures the model takes: a local workflow has as many as its
    ``ref_image`` slots (as the ComfyUI adapter sends); None = no limit known."""
    if spec_caps_max is not None:
        return spec_caps_max
    if where != "local":
        return None
    if workflow and has_workflow(workflow):
        return len(load_workflow(workflow).bindings("ref_image"))
    return LOCAL_REFS


def local_workflow(registry: Registry, model: str) -> Workflow | None:
    """A local model's ComfyUI workflow; None for an API model or one without a workflow."""
    try:
        spec = registry.spec(model)
    except ModelError:
        return None
    root = spec_workflows_dir(spec)
    if spec.where != "local" or not has_workflow(spec.workflow, root):
        return None
    return load_workflow(str(spec.workflow), root)


async def stale_aspect(session: AsyncSession, product: Product, version: ProductVersion) -> bool:
    """A keyframe drawn for another aspect than the spec's now (改画幅, SPEC 13.3). A picked
    candidate was drawn as its draft was."""
    row = await session.get(OutputSpecRow, product.series_id)
    drawn = (version.payload_json or {}).get("aspect")
    if drawn is None and version.origin == "pick" and version.parent_version_id:
        parent = await session.get(ProductVersion, version.parent_version_id)
        drawn = (parent.payload_json or {}).get("aspect") if parent is not None else None
    return row is not None and drawn is not None and drawn != row.aspect


async def gather(session: AsyncSession, invalidation: Invalidation, product: Product) -> Inputs:
    """What a shot's keyframe is drawn from (the adopted plan's shot, the adopted script's
    lines), and the slices that were read."""
    row = await session.get(Shot, product.owner_id)
    plan = await plan_product(session, row.episode_id) if row is not None else None
    adopted = (
        await session.get(ProductVersion, plan.adopted_version_id)
        if plan is not None and plan.adopted_version_id
        else None
    )
    shot = ops.find_shot(adopted.payload_json, product.owner_id) if adopted else None
    if row is None or plan is None or shot is None or product.retired:
        raise PipelineError(404, "shot_not_found", id=product.owner_id)
    if shot["shot_type"] == "continuous":
        raise PipelineError(409, "no_keyframe", id=row.id)
    episode_id = row.episode_id
    frame = await output_frame(session, product.series_id)
    deps = [await invalidation.dependency(session, plan.id, shot_slice(row.id))]
    script = await script_product(session, episode_id)
    written = (
        await session.get(ProductVersion, script.adopted_version_id)
        if script is not None and script.adopted_version_id
        else None
    )
    scene = script_ops.find_scene(written.payload_json, shot["scene_id"]) if written else None
    filmed = set(shot.get("line_ids") or [])
    action = [
        x
        for x in (scene or {}).get("lines") or []
        if x.get("id") in filmed and x.get("type") not in ops.SPEAKING
    ]
    if script is not None:
        for x in action:
            deps.append(await invalidation.dependency(session, script.id, f"line:{x['id']}"))
    filmed_lines = [x for x in (scene or {}).get("lines") or [] if x.get("id") in filmed]
    by_id = {str(s["id"]): s for s in ops.shots_of(adopted.payload_json if adopted else None)}
    c = (
        await shot_contract(session, product.series_id, shot, filmed_lines, by_id)
        if shot.get("contract")
        else None
    )
    # The props the scene puts in the picture (``props_linked``) are drawn from their pictures
    # too; the shots that gave a prop its state are read.
    ids = in_frame(shot, c)
    for source in sorted(set((c or {}).get("props_from", {}).values())):
        deps.append(await invalidation.dependency(session, plan.id, shot_slice(source)))
    here, across = await shot_space(session, product.series_id, ids, said_of(shot, c, action))
    refs, unlocked, texts = await _references(
        session, invalidation, ids + [a.asset_id for a in across if a.asset_id not in ids]
    )
    for a in across:  # labelled as the other side, not the shot's own place
        for r in refs:
            if r["kind"] == "scene" and r["name"] == a.name:
                r["name"] = a.label
    people = [str(r["name"]) for r in refs if r["kind"] == "character"]
    part = part_of(shot, c, people)
    part_desc = next((str(r["desc"]) for r in refs if part and r["name"] == part), "")
    if part:  # her reference is a whole person: the model drew her behind her own hand
        refs = [r for r in refs if not (r["kind"] == "character" and r["name"] == part)]
    refs += await extra_refs(session, invalidation, refs)
    refs += await set_refs(session, invalidation, row.id, product.series_id)
    seen = facing(shot, c, people, [t["name"] for t in texts])
    orientation = "竖屏" if _vertical(frame["aspect"]) else "横屏"
    framing = FRAMING.get(shot["framing"], shot["framing"])
    move = MOVE.get(shot["camera_move"], shot["camera_move"])
    blocks = [
        Block("画幅", f"{orientation} {frame['aspect']} 构图"),
        Block("景别", f"{framing}，这是首帧（之后{move}）"),
    ]
    if scene is not None and scene.get("heading"):
        blocks.append(Block("场景", str(scene["heading"])))
    if light := scene_light(scene):
        blocks.append(Block("光线", light))
    # Its own scene picture is where the camera is (run 19 1-10: the heading said the flat, the
    # shot was in the stairwell); else the heading's place.
    place = here or (scene_place(str(scene["heading"])) if scene and scene.get("heading") else None)
    if place:
        blocks.append(Block("机位", PLACE_NOTE.format(place=place)))
    if across:
        blocks.append(Block("另一边", "\n".join(a.text() for a in across)))
    if shot.get("blocking"):
        named = {r["name"] for r in refs} | set(unlocked) | {t["name"] for t in texts}
        in_shot = set(ids) | named
        blocks.append(Block("站位", blocking_text(list(shot["blocking"]), in_shot)))
    if part:
        blocks.append(Block("视角", PART_VIEW.format(who=part)))
        if part_desc:
            blocks.append(Block("手", PART_LOOK.format(who=part, desc=part_desc)))
    if seen:
        blocks.append(
            Block("朝向", FACING_NOTE.format(who=seen["who"], things="、".join(seen["things"])))
        )
    if action:
        blocks.append(Block("剧本", "\n".join(str(x.get("text") or "") for x in action)))
    for t in texts:
        if t["method"] == "model":
            blocks.append(Block("画面文字，必须逐字一致", f"「{t['exact']}」（{t['name']}）"))
        else:
            blocks.append(Block("画面文字", f"{t['name']}：留出位置，不要画字（后期贴字）"))
    # 关键帧检查 (M5.5 step 6): what each candidate is checked for.
    asks: dict[str, Any] = {
        "start": [],
        "scale": [],
        "texts": [t for t in texts if t["method"] == "model"],
        "inner": [],
        "no_people": False,
        "light": light,
        "place": place,
        "across": [f"{a.via}那边是{a.name}" for a in across],
        "part": part,
        "facing": seen,
    }
    if c is not None:
        blocks += await contract_blocks(session, c, ids, filmed_lines)
        asks["start"] = [f"{x['subject']}：{x['state']}" for x in c["start"]]
        asks["inner"] = inner_speakers(c, filmed_lines)
    if sizes := await prop_sizes(session, ids):
        blocks.append(Block("尺寸", SIZE_NOTE + sizes))
        asks["scale"] = sizes.split("；")
    if not await _has_character(session, shot.get("asset_ids") or []):
        blocks.append(Block("人物", NO_PEOPLE))
        asks["no_people"] = True
    blocks.append(Block("真实感", REAL_WORLD))
    return Inputs(
        blocks=blocks,
        deps=deps,
        episode_id=episode_id,
        context={
            "frame": frame,
            "refs": refs,
            "unlocked": unlocked,
            "texts": texts,
            "checks": asks,
        },
    )


def scene_light(scene: dict[str, Any] | None) -> str | None:
    """How the scene is lit, from its time of day in the script (``LIGHT``)."""
    return LIGHT.get(str((scene or {}).get("time_of_day") or ""))


async def asset_rows(session: AsyncSession, ids: list[str]) -> dict[str, Asset]:
    rows = await session.exec(
        select(Asset).where(col(Asset.id).in_(ids), col(Asset.retired).is_(False))
    )
    return {a.id: a for a in rows.all()}


def states_text(items: list[dict[str, str]]) -> str:
    return "；".join(f"{i['subject']}：{i['state']}" for i in items)


def props_text(props: list[dict[str, str]], assets: dict[str, Asset]) -> str:
    return "；".join(
        f"{assets[p['asset_id']].name}：{p['state']}" for p in props if p["asset_id"] in assets
    )


def part_of(shot: dict[str, Any], contract: dict[str, Any] | None, people: list[str]) -> str | None:
    """Whose part a close-up films (``PART_VIEW``): a subject 「林晚的手」, or only things while
    she is in the shot (1-07: 手机 in her hand); None for a face, a wider shot or nobody."""
    if shot.get("framing") != "closeup" or not people:
        return None
    c = contract or {}
    subjects = [str(x.get("subject") or "") for x in [*c.get("start", []), *c.get("end", [])]]
    for who in people:
        if any(s.startswith(f"{who}的") for s in subjects):
            return who
    if subjects and not any(s in people for s in subjects):
        return people[0]
    return None


def facing(
    shot: dict[str, Any], contract: dict[str, Any] | None, people: list[str], texts: list[str]
) -> dict[str, Any] | None:
    """Who looks at what has words or a screen in the shot (``FACING_NOTE``), if anyone does."""
    if not people or not texts:
        return None
    c = contract or {}
    said = " ".join(
        [str(shot.get("intent") or "")]
        + [str(x.get("state") or "") for x in [*c.get("start", []), *c.get("end", [])]]
    )
    if part_of(shot, contract, people) is None and not any(w in said for w in _LOOKS):
        return None
    return {"who": people[0], "things": texts}


def size_words(size: str) -> str | None:
    """「全长约 90 cm」 → 「立着到人的胯部」: the first length the size names (its overall one;
    「伞面直径约 100 cm」 after it is the open canopy), against a person."""
    found = _LENGTH.search(size)
    if found is None:
        return None
    cm = float(found.group(1)) * _UNIT_CM[found.group(2)]
    for limit, words in _SMALL + _TALL:
        if cm <= limit:
            return words
    return "比人的肩还高"


async def prop_sizes(session: AsyncSession, ids: list[str]) -> str:
    """「红色长柄伞：全长约 90 cm（立着到人的胯部）；黄色便利贴：7.6 cm 见方（手掌大小，比脸小）」
    for the shot's props that say."""
    assets = await asset_rows(session, ids)
    products = {
        p.owner_id: p
        for p in (
            await session.exec(
                select(Product).where(
                    Product.owner_type == "asset",
                    col(Product.owner_id).in_(ids),
                    Product.slot == "ref_image",
                )
            )
        ).all()
    }
    rows = []
    for i in ids:
        a = assets.get(i)
        size = (prop_physical(a, products.get(i)) or {}).get("size") if a else None
        if a is not None and a.kind == "prop" and size:
            words = size_words(size)
            rows.append(f"{a.name}：{size}" + (f"（{words}）" if words else ""))
    return "；".join(rows)


def inner_speakers(c: dict[str, Any], lines: list[dict[str, Any]]) -> list[str]:
    """Who speaks only in their head in the lines a shot films (its contract's delivery)."""
    names = [
        str(x.get("character_name") or "")
        for x in lines
        if c["delivery"].get(str(x.get("id"))) == "inner"
    ]
    return list(dict.fromkeys(n for n in names if n))


def in_frame(shot: dict[str, Any], contract: dict[str, Any] | None) -> list[str]:
    """The shot's references and the props its scene puts in the picture (``props_linked``)."""
    ids = list(shot.get("asset_ids") or [])
    return ids + [a for a in (contract or {}).get("props_linked") or [] if a not in ids]


async def shot_contract(
    session: AsyncSession,
    series_id: str,
    shot: dict[str, Any],
    lines: list[dict[str, Any]],
    shots_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """The shot's effective contract (``contracts.effective``) with its scene's props.
    ``lines``: the script lines it films (payload dicts)."""
    assets = await asset_rows(session, list(shot.get("asset_ids") or []))
    spoken = [
        contracts.SpokenLine(str(x["id"]), n, str(x.get("type") or ""), str(x.get("tone") or ""))
        for n, x in enumerate(lines, 1)
    ]
    names = await prop_names(session, series_id)
    kinds = {a.id: a.kind for a in assets.values()}
    return contracts.effective(shot, spoken, kinds, shots_by_id, names)


async def contract_blocks(
    session: AsyncSession, c: dict[str, Any], ids: list[str], lines: list[dict[str, Any]]
) -> list[Block]:
    """The keyframe's part of the shot's contract (M5.5): the start, the props' states, who
    speaks only in their head. ``ids``: what is in the picture (``in_frame``)."""
    assets = await asset_rows(session, ids)
    out: list[Block] = []
    if c["start"]:
        out.append(Block("开始时", START_NOTE + states_text(c["start"])))
    if c["props"] and props_text(c["props"], assets):
        out.append(Block("道具", PROPS_NOTE + props_text(c["props"], assets)))
    for who in inner_speakers(c, lines):
        out.append(Block("嘴", INNER_NOTE.format(who=who)))
    return out


async def _references(
    session: AsyncSession, invalidation: Invalidation, ids: list[str]
) -> tuple[list[dict[str, Any]], list[str], list[dict[str, str]]]:
    """The shot's locked pictures in order (characters, scene, props, text), the names of
    those not locked yet, and its on-screen text."""
    assets = {
        a.id: a
        for a in (
            await session.exec(
                select(Asset).where(col(Asset.id).in_(ids), col(Asset.retired).is_(False))
            )
        ).all()
    }
    products = {
        p.owner_id: p
        for p in (
            await session.exec(
                select(Product).where(
                    Product.owner_type == "asset",
                    col(Product.owner_id).in_(ids),
                    col(Product.slot).in_(REF_SLOTS),
                )
            )
        ).all()
    }
    refs: list[dict[str, Any]] = []
    unlocked: list[str] = []
    texts: list[dict[str, str]] = []
    ordered = sorted(
        (a for a in (assets.get(i) for i in ids) if a is not None and a.kind in REF_ORDER),
        key=lambda a: REF_ORDER.index(a.kind),
    )
    for a in ordered:
        p = products.get(a.id)
        if a.kind == "text":
            t = text_settings(a, p.settings_json if p else None)
            texts.append(
                {"name": a.name, "exact": t["exact"], "method": t["method"], "style": t["style"]}
            )
        elif (written := prop_text(a, p)) is not None:
            texts.append(
                {
                    "name": a.name,
                    "exact": written["exact"],
                    "method": "model",
                    "style": written["style"],
                }
            )
        ref = await locked_ref(session, p) if p is not None else None
        if ref is None or p is None:
            unlocked.append(a.name)
            continue
        h = await invalidation.current_hash(session, p.id, "")
        refs.append(
            {
                "name": a.name,
                "kind": a.kind,
                "asset_id": a.id,
                "product_id": p.id,
                "sha256": ref["sha256"],
                "hash": h,
                # How it looks in words (what the user wrote for its picture, else the analysis):
                # the H3 prompt rewrite cannot see the picture (vid, M5 step 14b).
                "desc": str(
                    (p.prompt_json or {}).get("intent") or a.seed_json.get("description") or ""
                ),
            }
        )
    return refs, unlocked, texts


async def extra_refs(
    session: AsyncSession, invalidation: Invalidation, refs: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """多参考图 (M5.5 step 11): the extra pictures of the assets whose main picture is sent,
    after all of them, by purpose (every 正脸 first), then in the assets' order."""
    mains = [r for r in refs if r["kind"] in MORE_KINDS and r.get("asset_id")]
    more = await sets_of(session, invalidation, REF_MORE, [str(r["asset_id"]) for r in mains])
    out: list[tuple[tuple[int, int, int], dict[str, Any]]] = []
    for order, r in enumerate(mains):
        m = more.get(str(r["asset_id"]))
        for f in (m or {}).get("files") or []:
            purpose = str(f.get("purpose") or "other")
            rank = PURPOSES.index(purpose) if purpose in PURPOSES else len(PURPOSES)
            item = {
                "name": r["name"],
                "kind": "more",
                "of": r["kind"],
                "purpose": purpose,
                "product_id": m["product_id"] if m else "",
                "sha256": f["sha256"],
                "hash": m["hash"] if m else None,
            }
            out.append(((rank, order, int(f.get("idx") or 0)), item))
    return [item for _, item in sorted(out, key=lambda x: x[0])]


async def set_refs(
    session: AsyncSession, invalidation: Invalidation, shot_id: str, series_id: str
) -> list[dict[str, Any]]:
    """镜头参考图 then 风格板 (M5.5 step 12), after the assets' pictures, each for its purpose."""
    out: list[dict[str, Any]] = []
    for kind, owner_id, name in (
        (SHOT_REFS, shot_id, "镜头参考"),
        (STYLE_BOARD, series_id, "风格板"),
    ):
        got = (await sets_of(session, invalidation, kind, [owner_id])).get(owner_id)
        for f in (got or {}).get("files") or []:
            out.append(
                {
                    "name": name,
                    "kind": "shot" if kind is SHOT_REFS else "style",
                    "purpose": str(f.get("purpose") or "style"),
                    "product_id": got["product_id"] if got else "",
                    "sha256": f["sha256"],
                    "hash": got["hash"] if got else None,
                }
            )
    return out


ONLY_REFS = ("more", "shot", "style")  # pictures that only add to the references


def ref_label(r: dict[str, Any]) -> str:
    """How a sent picture is named in the version's ``refs``: 「林晚·正脸」「镜头参考·构图」."""
    if r["kind"] == "more":
        return f"{r['name']}·{PURPOSE_LABEL.get(r['purpose'], r['purpose'])}"
    if r["kind"] == "shot":
        return f"{r['name']}·{SHOT_PURPOSE_LABEL.get(r['purpose'], r['purpose'])}"
    return str(r["name"])


def ref_title(i: int, r: dict[str, Any]) -> str:
    """「参考图 3：林晚（角色·正脸）」 in the prompt."""
    if r["kind"] in KIND_LABEL:
        return f"参考图 {i}：{r['name']}（{KIND_LABEL[r['kind']]}）"
    if r["kind"] == "more" and r["purpose"] in PURPOSE_LABEL:
        of = KIND_LABEL.get(r["of"], "")
        return f"参考图 {i}：{r['name']}（{of}·{PURPOSE_LABEL[r['purpose']]}）"
    if r["kind"] == "shot" and r["purpose"] in SHOT_PURPOSE_LABEL:
        return f"参考图 {i}：{r['name']}（{SHOT_PURPOSE_LABEL[r['purpose']]}）"
    return f"参考图 {i}：{r['name']}"


def more_note(refs: list[dict[str, Any]]) -> str:
    """What each added picture is only for: 「参考图 3 只参考林晚的服装」, 「参考图 5 只参考构图，
    里面的人和东西不照搬」."""
    notes = []
    for i, r in enumerate(refs, 1):
        if r["kind"] == "more":
            if r["purpose"] == "other":
                notes.append(f"参考图 {i} 是{r['name']}的另一张参考")
            else:
                notes.append(f"参考图 {i} 只参考{r['name']}的{PURPOSE_LABEL[r['purpose']]}")
        elif r["kind"] == "shot":
            what = SHOT_PURPOSE_LABEL.get(r["purpose"], r["purpose"])
            notes.append(f"参考图 {i} 只参考{what}，里面的人和东西不照搬")
        elif r["kind"] == "style":
            notes.append(f"参考图 {i} 只参考画面风格（色调、质感、光影），里面的人和东西不照搬")
    return "；".join(notes) + "。" if notes else ""


async def _has_character(session: AsyncSession, ids: list[str]) -> bool:
    """Whether one of the shot's references is a character (locked or not)."""
    rows = await session.exec(
        select(Asset.id).where(
            col(Asset.id).in_(ids), Asset.kind == "character", col(Asset.retired).is_(False)
        )
    )
    return rows.first() is not None


def pick_refs(
    inputs: Inputs, draft_sha: str | None, limit: int | None
) -> tuple[list[dict[str, Any]], list[DependencyDraft], list[Block]]:
    """The pictures sent (the draft first for a final, then the locked references as many as
    the model takes), what they make it depend on, and the blocks naming each one."""
    refs: list[dict[str, Any]] = []
    blocks = list(inputs.blocks)
    if draft_sha is not None:
        refs.append({"name": "草稿", "kind": "draft", "sha256": draft_sha})
    locked = list(inputs.context.get("refs") or [])
    room = None if limit is None else max(0, limit - len(refs))
    sent = locked if room is None else locked[:room]
    # A picture that only adds (多参考图, 镜头参考, 风格板) left out is not missing.
    left_out = [r["name"] for r in locked[len(sent) :] if r["kind"] not in ONLY_REFS]
    refs += sent
    deps: list[DependencyDraft] = []
    for r in sent:
        if r.get("hash") and all(d.upstream_product_id != r["product_id"] for d in deps):
            deps.append(DependencyDraft(r["product_id"], r["hash"], ""))
    if refs:
        named = "；".join(ref_title(i, r) for i, r in enumerate(refs, 1))
        blocks.append(
            Block(
                "参考图",
                named
                + "。人物的长相、发型和服装，场景和道具的样子都要和参考图一致。"
                + more_note(refs),
            )
        )
    if draft_sha is not None:
        blocks.append(Block("草稿", FINAL_NOTE))
    missing = [*inputs.context.get("unlocked", []), *left_out]
    if missing:
        blocks.append(
            Block(
                "没传的参考",
                "、".join(missing) + "（未锁定，或超过模型能收的张数），按[画面]的描述画。",
            )
        )
    return refs, deps, blocks


def draft_file(source: tuple[ProductVersion, int] | None) -> str | None:
    """The sha256 of the draft an API final starts from."""
    if source is None:
        return None
    v, idx = source
    f = next(
        (x for x in v.files_json if x.get("role") == "candidate" and x.get("idx") == idx), None
    ) or ref_file(v)
    return str(f["sha256"]) if f is not None else None


class KfComponent(MediaComponent):
    id = "kf"
    slot = KEYFRAME_SLOT
    owner_type = "shot"
    auto_adopt = False

    async def default_intent(self, session: AsyncSession, product: Product, lang: str) -> str:
        """The plan's picture description (the seed; the user's edits are the prompt)."""
        shot = await session.get(Shot, product.owner_id)
        return shot.intent if shot is not None else ""

    async def inputs(self, session: AsyncSession, product: Product) -> Inputs:
        return await gather(session, self.services.invalidation, product)

    def model_for(self, inputs: Inputs, model: str, settings: Resolved) -> str:
        """A draft with no locked reference picture cannot go to an edit-only model: take the
        next local model of the component after it (wrapping round) that draws from words and
        this machine can run, so each edit model is followed by its own family's (Qwen-Image
        after Qwen-Image-Edit, FLUX 3 Klein's text-to-image after FLUX 3 Klein). An API final
        always sends the draft."""
        registry = self.services.registry
        if inputs.params.get("source_version_id") or inputs.context.get("refs"):
            return model
        wf = local_workflow(registry, model)
        if wf is None or not wf.needs_refs():
            return model
        try:
            local = get_config().components.component(self.id).local
        except KeyError:
            local = []
        i = local.index(model) if model in local else -1
        for other in local[i + 1 :] + local[: i + 1]:
            alt = local_workflow(registry, other)
            if other not in settings.unavailable and alt is not None and not alt.needs_refs():
                return other
        return model  # nothing to take: it fails as 「ref_missing」 and falls back as usual

    # ------------------------------------------------------------------ run

    async def run(self, ctx: RunContext, inputs: Inputs) -> VersionDraft:
        source = await self.source_candidate(ctx.product, inputs.params)
        spec = self.services.registry.spec(ctx.model_key)
        limit = ref_limit(spec.caps.max_refs, spec.where, spec.workflow)
        refs, deps, blocks = pick_refs(inputs, draft_file(source), limit)
        frame = inputs.context["frame"]
        where = self.where_of(ctx.model_key)
        # 检查没过自动重画 (9e-5, ``pipeline/redraw.py``): every candidate failed its check.
        redraws = redraw.tries(self.id) if where == "local" else 0
        calls: list[Any] = []
        best: tuple[int, int, str, list[dict[str, Any]], list[dict[str, Any]]] | None = None
        fixes: list[Block] = []
        for attempt in range(1 + redraws):
            prompt = prompt_text(ctx.compiled, [*blocks, *fixes])
            seed = ctx.seed + 100 * attempt if ctx.seed is not None and attempt else ctx.seed
            req = self.image_request(
                prompt,
                n=1 if source else self.candidates(),
                size=frame_size(frame, where),
                aspect=frame["aspect"],
                seed=seed,
                task="final" if source else "keyframe",
                refs=[r["sha256"] for r in refs],
                extra=self._text_params(inputs),
            )
            call = await self.media_call(
                ctx,
                req,
                inputs.episode_id,
                model=ctx.model_key,
                fallback_reason=ctx.fallback_reason,
            )
            calls.append(call)
            if not call.files:
                raise ComponentError("no_images")
            files = candidate_files(call)
            checked = await self._check(ctx, inputs, files, [{} for _ in files])
            top = max(checked, key=lambda c: redraw.score(c.get("check")))
            mark = redraw.score(top.get("check"))
            done = not all(redraw.failed(c.get("check")) for c in checked)
            if best is None or mark > best[0] or done:
                best = (mark, attempt, prompt, files, checked)
            if done:  # one passed, or one went unchecked (nothing to go by)
                break
            fixes = [Block(redraw.FIX_TITLE, redraw.failed_text(top["check"], kfcheck.LABELS))]
        assert best is not None
        _, kept, prompt, files, checked = best
        payload: dict[str, Any] = {
            "candidates": checked,
            "aspect": frame["aspect"],
            "refs": [ref_label(r) for r in refs if r["kind"] != "draft"],
        }
        if len(calls) > 1:
            payload["redraws"] = len(calls) - 1  # tries after the first; ``kept``: the one shown
        stage = "final" if source else "draft" if calls[kept].where == "local" else None
        draft = self.media_draft(ctx, inputs, payload, files, calls, prompt, stage=stage)
        draft.dependencies = [*draft.dependencies, *deps]
        if kept:
            draft.seed = ctx.seed + 100 * kept if ctx.seed is not None else None
        if source:
            draft.params["source"] = {"version_id": source[0].id, "idx": source[1]}
        return draft

    def estimate(self, inputs: Inputs, compiled: str, model: str) -> Estimate:
        source = bool(inputs.params.get("source_version_id"))
        frame = inputs.context["frame"]
        n = 1 if source else self.candidates()
        req = self.image_request(
            compiled,
            n=n,
            size=frame_size(frame, self.where_of(model)),
            aspect=frame["aspect"],
            seed=None,
            task="final" if source else "keyframe",
            extra=self._text_params(inputs),
        )
        parts = [self.services.registry.get(model).estimate(req)]
        asks: dict[str, Any] = inputs.context.get("checks") or {}
        look = kfcheck.estimate(self.services, route_model(self.services, kfcheck.KFCHECK), asks)
        if kfcheck.has_asks(asks) and look is not None:  # 关键帧检查: one look a candidate
            # … and as many again for each redraw it may take (on this machine only: 9e-5)
            tries = 1 + (redraw.tries(self.id) if self.where_of(model) == "local" else 0)
            parts += [look] * n * tries
        return Estimate(
            cost_usd=sum(e.cost_usd for e in parts),
            seconds=sum(e.seconds for e in parts),
            priced=all(e.priced for e in parts),
        )

    def mock_responders(self) -> dict[str, Responder]:
        return {kfcheck.TASK: kfcheck.mock_check}

    async def _check(
        self,
        ctx: RunContext,
        inputs: Inputs,
        files: list[dict[str, Any]],
        candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """关键帧检查 (M5.5): each candidate looked at against its shot and its drawn words
        read back by OCR, into ``candidates[i].check``."""
        asks = inputs.context.get("checks") or {}
        if not kfcheck.has_asks(asks):
            return candidates
        call_ctx = self._call_ctx(ctx, inputs.episode_id)
        item = item_of(ctx.product)
        candidates = list(candidates)
        for f in files:
            i = int(f.get("idx") or 0)
            if f.get("role") != "candidate" or i >= len(candidates):
                continue
            items: list[dict[str, Any]] = []
            model = None
            seen = await kfcheck.look(self.services, f["sha256"], asks, item, call_ctx)
            if seen is not None:
                items, model = seen
            if asks.get("texts"):
                read = await ocr.read(
                    self.services.router, self.services.store, f["sha256"], call_ctx
                )
                for t in asks["texts"]:
                    if read is not None:
                        items.append(
                            {
                                "check": "ocr",
                                "ok": ocr.contains(read, t["exact"]),
                                "note": read[:60],
                            }
                        )
            if items or model:
                candidates[i] = {
                    **candidates[i],
                    "check": {"items": items, "ok": all(x["ok"] for x in items), "model": model},
                }
        return candidates

    # ------------------------------------------------------------------ internals

    @staticmethod
    def _text_params(inputs: Inputs) -> dict[str, Any]:
        """The characters to draw (Mock writes them into the picture for OCR)."""
        drawn = [t["exact"] for t in inputs.context.get("texts") or [] if t["method"] == "model"]
        return {"text": "".join(drawn)} if drawn else {}


def route_model(services: Any, route_id: str) -> str | None:
    """A route's default model, for estimates (which cannot read the series' own route)."""
    try:
        route = get_config().components.component(route_id).balanced
    except KeyError:
        return None
    key = route.local if route.mode == "local" else route.api
    known = {s.key for s in services.registry.specs()}
    return key if key in known else None


def _vertical(aspect: str) -> bool:
    w, h = (int(x) for x in aspect.split(":"))
    return h > w
