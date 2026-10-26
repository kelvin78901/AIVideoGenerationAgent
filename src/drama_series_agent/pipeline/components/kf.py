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

from typing import Any

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from drama_series_agent.core.config import Resolved, get_config
from drama_series_agent.core.models_db import Asset, OutputSpecRow, Product, ProductVersion, Shot
from drama_series_agent.episodes.service import script_product
from drama_series_agent.modelhub.adapters.base import Estimate, ModelError
from drama_series_agent.modelhub.registry import Registry
from drama_series_agent.modelhub.workflows import Workflow, has_workflow, load_workflow
from drama_series_agent.pipeline.component import ComponentError, Inputs, RunContext
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
from drama_series_agent.prompts.compiler import Block
from drama_series_agent.script import ops as script_ops
from drama_series_agent.shots import ops
from drama_series_agent.shots.service import KEYFRAME_SLOT

REF_ORDER = ops.REF_KINDS
REF_SLOTS = ("ref_image", "text_image")
KIND_LABEL = {"character": "角色", "scene": "场景", "prop": "道具", "text": "画面文字"}
FRAMING = {"wide": "远景", "medium": "中景", "close": "近景", "closeup": "特写"}
MOVE = {"static": "固定机位", "push": "缓推", "follow": "跟拍", "pan": "摇镜"}
# A shot whose references have no character: said outright, or the model adds a stranger
# (1-02, the umbrella at the door: 5 of 6 drafts had a woman in them; 1 of 6 with this).
NO_PEOPLE = "这个镜头里没有人物，不要画人。"
FINAL_NOTE = "以参考图 1 的草稿为准，画得更精细：构图、人物、光线和颜色都不要改。"
LOCAL_REFS = 3  # a local workflow that does not say


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
    if spec.where != "local" or not has_workflow(spec.workflow):
        return None
    return load_workflow(str(spec.workflow))


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
    refs, unlocked, texts = await _references(session, invalidation, shot.get("asset_ids") or [])
    orientation = "竖屏" if _vertical(frame["aspect"]) else "横屏"
    framing = FRAMING.get(shot["framing"], shot["framing"])
    move = MOVE.get(shot["camera_move"], shot["camera_move"])
    blocks = [
        Block("画幅", f"{orientation} {frame['aspect']} 构图"),
        Block("景别", f"{framing}，这是首帧（之后{move}）"),
    ]
    if scene is not None and scene.get("heading"):
        blocks.append(Block("场景", str(scene["heading"])))
    if shot.get("blocking"):
        named = {r["name"] for r in refs} | set(unlocked) | {t["name"] for t in texts}
        in_shot = set(shot.get("asset_ids") or []) | named
        blocks.append(Block("站位", blocking_text(list(shot["blocking"]), in_shot)))
    if action:
        blocks.append(Block("剧本", "\n".join(str(x.get("text") or "") for x in action)))
    for t in texts:
        if t["method"] == "model":
            blocks.append(Block("画面文字，必须逐字一致", f"「{t['exact']}」（{t['name']}）"))
        else:
            blocks.append(Block("画面文字", f"{t['name']}：留出位置，不要画字（后期贴字）"))
    if not await _has_character(session, shot.get("asset_ids") or []):
        blocks.append(Block("人物", NO_PEOPLE))
    return Inputs(
        blocks=blocks,
        deps=deps,
        episode_id=episode_id,
        context={"frame": frame, "refs": refs, "unlocked": unlocked, "texts": texts},
    )


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
            texts.append({"name": a.name, "exact": t["exact"], "method": t["method"]})
        ref = await locked_ref(session, p) if p is not None else None
        if ref is None or p is None:
            unlocked.append(a.name)
            continue
        h = await invalidation.current_hash(session, p.id, "")
        refs.append(
            {
                "name": a.name,
                "kind": a.kind,
                "product_id": p.id,
                "sha256": ref["sha256"],
                "hash": h,
            }
        )
    return refs, unlocked, texts


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
    left_out = [r["name"] for r in locked[len(sent) :]]
    refs += sent
    deps = [DependencyDraft(r["product_id"], r["hash"], "") for r in sent if r.get("hash")]
    if refs:
        named = "；".join(
            f"参考图 {i}：{r['name']}"
            + (f"（{KIND_LABEL[r['kind']]}）" if r["kind"] in KIND_LABEL else "")
            for i, r in enumerate(refs, 1)
        )
        blocks.append(
            Block("参考图", named + "。人物的长相、发型和服装，场景和道具的样子都要和参考图一致。")
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
        first local model of the component that draws from words and this machine can run
        (Qwen-Image). An API final always sends the draft."""
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
        for other in local:
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
        prompt = prompt_text(ctx.compiled, blocks)
        req = self.image_request(
            prompt,
            n=1 if source else self.candidates(),
            size=frame_size(frame, where),
            aspect=frame["aspect"],
            seed=ctx.seed,
            task="final" if source else "keyframe",
            refs=[r["sha256"] for r in refs],
            extra=self._text_params(inputs),
        )
        call = await self.media_call(
            ctx, req, inputs.episode_id, model=ctx.model_key, fallback_reason=ctx.fallback_reason
        )
        if not call.files:
            raise ComponentError("no_images")
        files = candidate_files(call)
        payload: dict[str, Any] = {
            "candidates": [{} for _ in files],
            "aspect": frame["aspect"],
            "refs": [r["name"] for r in refs if r["name"] != "草稿"],
        }
        stage = "final" if source else "draft" if call.where == "local" else None
        draft = self.media_draft(ctx, inputs, payload, files, [call], prompt, stage=stage)
        draft.dependencies = [*draft.dependencies, *deps]
        if source:
            draft.params["source"] = {"version_id": source[0].id, "idx": source[1]}
        return draft

    def estimate(self, inputs: Inputs, compiled: str, model: str) -> Estimate:
        source = bool(inputs.params.get("source_version_id"))
        frame = inputs.context["frame"]
        req = self.image_request(
            compiled,
            n=1 if source else self.candidates(),
            size=frame_size(frame, self.where_of(model)),
            aspect=frame["aspect"],
            seed=None,
            task="final" if source else "keyframe",
            extra=self._text_params(inputs),
        )
        return self.services.registry.get(model).estimate(req)

    # ------------------------------------------------------------------ internals

    @staticmethod
    def _text_params(inputs: Inputs) -> dict[str, Any]:
        """The characters to draw (Mock writes them into the picture for OCR)."""
        drawn = [t["exact"] for t in inputs.context.get("texts") or [] if t["method"] == "model"]
        return {"text": "".join(drawn)} if drawn else {}


def _vertical(aspect: str) -> bool:
    w, h = (int(x) for x in aspect.split(":"))
    return h > w
