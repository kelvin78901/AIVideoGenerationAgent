"""Run 19 (M5.5 step 9): episode 1 again with the shot contract and the checks, on a copy of
run 17's data directory. ``local_video.py --only contract`` calls ``prepare``; the takes are then
made shot by shot with ``--only episode --from <shot> --to <shot>`` as in run 17.

What ``prepare`` does, in order (real: ComfyUI, DeepSeek for the plan and its check, Gemini for
the keyframe check; nothing else):

1. the data the run-17 directory predates M5.5 on: the props' real size, material and wear on
   their pictures' settings (``settings.physical``), the note's words on the note
   (``settings.text``), the separate 便利贴手写 retired (M5.5 step 5b: the words are the note's);
2. 红伞 and 黄色便利贴 drawn again on this machine (the new prop prompt: real photo, real size,
   the note with its handwriting; OCR read back), locked, which draws their 比例参考;
3. 分镜规划 again on DeepSeek (the contract), adopted; 分镜检查 on DeepSeek;
4. every keyframe drawn again (local draft) and checked (Gemini + OCR); each shot confirmed on
   the candidate with the most checks passed; 分镜确认.

``local_video.py --only revise`` calls ``revise`` (Kelvin 2026-11-10: the storyboard is fixed by
its check before any take, as a user would on the storyboard page): ``REVISIONS`` through
``PATCH /shots/{id}``, the check again, the changed shots' keyframes drawn and checked again,
分镜确认.

``local_video.py --only fresh`` calls ``fresh`` (M5.5 step 9e-6, run 20, on a new copy of run
17's directory): what ``prepare`` does with the 9e fixes and nothing edited by hand: the flat's
door written into its scene as 素材分析 now finds it (``ADJOINS``; no page edits it yet), the
props drawn again, 分镜规划 and its check, 分镜规划 again told what the check found, its check,
every keyframe drawn and checked (drawn again when every candidate fails). The takes follow
shot by shot with ``--only episode`` as before.

``local_video.py --only redo`` calls ``redo`` (M5.5 step 9d, Kelvin 2026-11-10: the pipeline
constrains the details, no shot is edited by hand): the props' scale references drawn again
(only the prop and the person), the storyboard check, then 1-04, 1-06 and 1-09's keyframes drawn
and checked again as the pipeline now asks for them (the scene's prop states and the props they
name, the light of the night, the camera inside the scene's place).
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from local_assets import Smoke
from local_storyboard import shots, unconfirm, unlock

PHYSICAL = {
    "umbrella": {
        "size": "全长约 90 cm，收拢时粗约 6 cm",
        "material": "尼龙伞面、木质弯柄、金属伞骨",
        "wear": "用了几年，伞面有点褪色，木柄磨得发亮",
    },
    "note": {
        "size": "约 7.6 cm 见方",
        "material": "黄色便利贴纸",
        "wear": "新撕下的一张，边角被雨打湿",
    },
    "band": {"size": "直径约 4 cm", "material": "黑色布面皮筋", "wear": "洗旧了，皮筋松了"},
    "phone": {
        "size": "约 15 cm × 7 cm",
        "material": "黑色手机壳、玻璃屏",
        "wear": "屏幕有一道细划痕",
    },
}
NOTE_TEXT = {"exact": "楼下便利店，等你到十二点。", "style": "handwritten", "method": "model"}
REDRAWN = ("umbrella", "note")
PLAN = "demo-p-plan-e1"
LINWAN = "林晚"
# What run 19's 分镜检查 found, fixed as its notes say (content; ``PATCH /shots/{id}``).
REVISIONS: dict[str, dict[str, Any]] = {
    # The model: walking up and to the door in two beats is a jump; stop at the stairs.
    "1-01": {
        "intent": "楼道全景，声控灯忽明忽暗，林晚抱着画板袋走上六楼，在楼梯口停步，"
        "抬头看见门边靠着一把红伞，愣住。",
        "contract": {
            "end": [{"subject": LINWAN, "state": "停在六楼楼梯口，抬头看见门边的伞，愣住"}]
        },
    },
    "1-02": {"contract": {"start": [{"subject": LINWAN, "state": "走到门口，停下看着伞"}]}},
    # The rule: 1-04 looked like a replay of 1-02 (same scene, camera and framing).
    "1-04": {"framing": "close"},
    # The model: she held no umbrella after 1-05, and 1-10 picks it up outside the door.
    "1-06": {
        "intent": "出租屋内，林晚空着手进门、反手关上门，后背抵着门，台灯暖光。",
        # With the umbrella's picture: without it the keyframe drew a black one by the door.
        "asset_ids": ["umbrella"],  # added to the shot's (``revise``)
        "contract": {
            "kind": "action",
            "beats": 2,
            "start": [{"subject": LINWAN, "state": "站在门外，伞仍靠在门边墙上"}],
            "end": [{"subject": LINWAN, "state": "在屋里，背靠着关上的门"}],
            "props": [{"asset_id": "umbrella", "state": "靠在门外墙边，没有拿进屋"}],
        },
    },
    # The rule: 拉开 → 关上 → 拉开 (undone and done again). The hesitation is acted, once.
    "1-09": {
        "intent": "林晚从门边站直，转身握住门把，停了两秒，拉开门。画面中景，她表情纠结。",
        "contract": {
            "beats": 2,
            "start": [{"subject": LINWAN, "state": "站在门后，手握着门把"}],
            "end": [
                {"subject": LINWAN, "state": "拉开门，站在门口"},
                {"subject": "家门", "state": "开着"},
            ],
        },
    },
    "1-10": {
        "intent": "门外，林晚站在门口，弯腰拿起靠在门外墙边的红色长柄伞，直起身，表情坚定。"
        "画面中景，光线从屋内照出。",
        "contract": {
            "start": [
                {"subject": LINWAN, "state": "站在门口"},
                {"subject": "红伞", "state": "靠在门外墙边"},
            ],
            "props": [{"asset_id": "umbrella", "state": "靠在门外墙边，被林晚拿起"}],
        },
    },
}
# What the flat's 素材分析 finds now (M5.5 9e-3; the demo's words), for a directory older than it.
ADJOINS = {
    "room": [
        {
            "via": "门",
            "to": "scene:l-stairs:night",
            "note": "门外是六楼楼道：水泥地，楼梯口在门的左边，声控灯昏黄；"
            "红伞靠在门外右手边的墙上",
        }
    ]
}
# Run 19's new problems (README): 1-04 two notes and a black umbrella, 1-06 shut out, 1-09 daylight.
# 1-03 and 1-05 use the note too: its new picture makes them stale.
REDO = ("1-03", "1-04", "1-05", "1-06", "1-09")


def _settings(smoke: Smoke) -> None:
    from sqlmodel import select

    from drama_series_agent.core.models_db import Asset, Product

    async def write() -> None:
        async with smoke.state.db.session() as s:
            for asset_id, physical in PHYSICAL.items():
                p = (
                    await s.exec(
                        select(Product).where(
                            Product.owner_type == "asset",
                            Product.owner_id == asset_id,
                            Product.slot == "ref_image",
                        )
                    )
                ).one()
                settings = dict(p.settings_json or {})
                settings["physical"] = physical
                if asset_id == "note":
                    settings["text"] = NOTE_TEXT
                p.settings_json = settings
                s.add(p)
            txt1 = await s.get(Asset, "txt1")
            if txt1 is not None:
                txt1.retired = True
                s.add(txt1)
            await s.commit()

    smoke.client.portal.call(write)
    smoke.say("== data: 道具尺寸材质新旧、便利贴上的字写进设置；便利贴手写（txt1）退场")


def _props(smoke: Smoke, which: tuple[str, ...] = REDRAWN) -> bool:
    def draw() -> list[str]:
        for a in which:
            try:
                unlock(smoke, a)
            except RuntimeError as exc:
                if "not_locked" not in str(exc):
                    raise
        return [smoke.run(f"demo-p-asset-{a}")["id"] for a in which]

    names = "、".join(which)
    if not smoke.step(
        "props", f"道具本机重画：{names}（实拍质感、真实尺寸、带字、只画道具）", draw
    ):
        return False
    for a in which:
        version = smoke.latest(f"demo-p-asset-{a}")
        smoke.keep_files(f"prop-{a}", version)
        cands = version["payload"].get("candidates") or []
        idx = next((i for i, c in enumerate(cands) if c.get("ocr_ok")), 0)
        smoke.post(f"/assets/{a}/lock", {"idx": idx})
        smoke.say(f"   {a}: locked candidate {idx}")
    # Locking no longer draws its 比例参考 (M5.5 9e-1): sizes are said against a person.
    return True


def _plan(smoke: Smoke) -> bool:
    for label in shots(smoke):
        unconfirm(smoke, label)

    def plan() -> list[str]:
        return [smoke.run(PLAN)["id"]]

    if not smoke.step("plan", "分镜规划重跑（DeepSeek，带镜头契约）", plan):
        return False
    latest = smoke.latest(PLAN)
    product = smoke.get(f"/products/{PLAN}")
    if product["adopted_version_id"] != latest["id"]:
        smoke.post(f"/versions/{latest['id']}/adopt")
    _say_shots(smoke)
    return _check(smoke)


def _say_shots(smoke: Smoke) -> None:
    for s in smoke.get("/episodes/demo-e1/shots"):
        c = s["contract"]
        start = "；".join(f"{x['subject']}{x['state']}" for x in c["start"])
        end = "；".join(f"{x['subject']}{x['state']}" for x in c["end"])
        props = "；".join(
            f"{x['asset_id']}:{x['state']}"
            + ("（沿用）" if x["asset_id"] in c.get("props_inherited", []) else "")
            + ("（带进来）" if x["asset_id"] in c.get("props_linked", []) else "")
            for x in c["props"]
        )
        smoke.say(
            f"   {s['label']} {s['shot_type']} {s['framing']} {c['kind']}/{c['beats']}"
            f"{' (接上一镜)' if c['start_inherited'] else ''} | 开始 {start or '—'} | "
            f"结束 {end or '—'} | 道具 {props or '—'} | 台词 {c['delivery'] or '—'}"
        )
        smoke.say(f"      画面：{s['intent']}")


def _check(smoke: Smoke) -> bool:
    def check() -> list[str]:
        return [smoke.post("/episodes/demo-e1/shot-checks")["id"]]

    smoke.step("plancheck", "分镜检查（规则 + DeepSeek）", check)
    found = smoke.get("/episodes/demo-e1/shot-checks")
    smoke.say(f"   模型检查 {found['llm_state']}，{len(found['issues'])} 处提示")
    for i in found["issues"]:
        said = i["text"] or i["params"]
        smoke.say(f"   {i['label']} {i['code']} [{i['source']}] {said}")
    return True


def _keyframes(smoke: Smoke, labels: set[str] | None = None, tag: str = "kf") -> bool:
    by_label = shots(smoke)
    drawn = [
        s
        for s in by_label.values()
        if s["keyframe_product_id"] and (labels is None or s["label"] in labels)
    ]

    def keyframes() -> list[str]:
        return [smoke.run(s["keyframe_product_id"])["id"] for s in drawn]

    which = "、".join(s["label"] for s in drawn)
    if not smoke.step("kf", f"关键帧重画（本地草稿）并检查（Gemini + OCR）：{which}", keyframes):
        return False
    for s in drawn:
        version = smoke.latest(s["keyframe_product_id"])
        smoke.keep_files(f"{tag}-{s['label']}", version)
        cands: list[dict[str, Any]] = version["payload"].get("candidates") or []
        scores = []
        for i, c in enumerate(cands):
            items = (c.get("check") or {}).get("items") or []
            passed = sum(1 for x in items if x["ok"])
            scores.append(passed)
            said = "，".join(f"{x['check']} {'✓' if x['ok'] else '✗ ' + x['note']}" for x in items)
            smoke.say(f"   {s['label']} #{i}: {said or '没有检查'}")
        best = max(range(len(scores)), key=lambda i: scores[i]) if scores else 0
        resp = smoke.client.patch(
            f"/api/v1/shots/{s['id']}", json={"keyframe_pick": best, "confirmed": True}
        )
        smoke.say(f"   {s['label']}: 确认第 {best + 1} 张（{resp.status_code}）")
    for s in by_label.values():
        if not s["keyframe_product_id"] or not s["confirmed"]:
            smoke.client.patch(f"/api/v1/shots/{s['id']}", json={"confirmed": True})
    try:
        smoke.post("/gates/storyboard/confirm", {"scope_id": "demo-e1"})
    except RuntimeError as exc:  # other shots went stale (a new prop picture): said, not fatal
        smoke.say(f"   分镜确认：{exc}")
    board = smoke.get("/episodes/demo-e1/progress")["steps"]["storyboard"]
    smoke.say(f"   分镜 {board['state']} {board['done']}/{board['total']}")
    return True


def prepare(smoke: Smoke) -> bool:
    _settings(smoke)
    return _props(smoke) and _plan(smoke) and _keyframes(smoke)


def _adjoins(smoke: Smoke) -> None:
    """``ADJOINS`` into the scenes' ``seed_json`` (where 素材分析 puts it), straight in the copy's
    database: no API edits it yet (DECISIONS 2026-11-11 第 9e 步)."""
    db = sqlite3.connect(Path(os.environ["DRAMA_HOME"]) / "studio.db")
    try:
        for asset_id, near in ADJOINS.items():
            row = db.execute("SELECT seed_json FROM asset WHERE id = ?", (asset_id,)).fetchone()
            seed = json.loads(row[0] or "{}") if row else {}
            seed["adjoins"] = near
            db.execute(
                "UPDATE asset SET seed_json = ? WHERE id = ?",
                (json.dumps(seed, ensure_ascii=False), asset_id),
            )
            smoke.say(f"   {asset_id}: adjoins {near[0]['via']} → {near[0]['to']}")
        db.commit()
    finally:
        db.close()


def fresh(smoke: Smoke) -> bool:
    """M5.5 step 9e-6 (run 20): see the module's docstring."""
    smoke.say("== fresh: 第十七轮副本整集重出，只靠流程（9e）")
    _settings(smoke)
    _adjoins(smoke)
    if not (_props(smoke) and _plan(smoke)):
        return False
    smoke.say("== 分镜规划再出一次：带着上一版的分镜检查")
    return _plan(smoke) and _keyframes(smoke)


def revise(smoke: Smoke, only: str | None = None) -> bool:
    """The storyboard fixed by its check (``REVISIONS``; ``only`` one of them, ``--from``),
    checked again, the changed shots' keyframes drawn again; then 分镜确认."""
    smoke.say("== revise: 按分镜检查改分镜（PATCH /shots，和分镜页一样）")
    by_label = shots(smoke)
    todo = {k: v for k, v in REVISIONS.items() if only is None or k == only}
    for label, patch in todo.items():
        shot = by_label[label]
        unconfirm(smoke, label)
        body = dict(patch)
        if "asset_ids" in body:
            body["asset_ids"] = [
                *shot["asset_ids"],
                *(a for a in body["asset_ids"] if a not in shot["asset_ids"]),
            ]
        resp = smoke.client.patch(f"/api/v1/shots/{shot['id']}", json=body)
        smoke.say(f"   {label}: {', '.join(body)}（{resp.status_code}）")
        if resp.status_code != 200:
            smoke.say(f"      {resp.text}")
            smoke.ok = False
    # A shot that starts where the one before ended (1-08) follows 1-06's new end.
    _say_shots(smoke)
    if not _check(smoke):
        return False
    return _keyframes(smoke, set(todo))


def redo(smoke: Smoke, only: str | None = None) -> bool:
    """M5.5 step 9d: the pipeline's fixes only (see the module's docstring). ``only``: ``scale``
    for the scale references alone, or one shot's keyframe alone (each run under 10 minutes)."""
    smoke.say("== redo: 只靠流程（9d），不改分镜")

    def scales() -> list[str]:
        return [smoke.run(smoke.product_of(f"asset:{a}", "ref_scale"))["id"] for a in REDRAWN]

    if only == "props":  # the note's own picture drew a black umbrella (9d-1)
        return _props(smoke, ("note",))
    if only in (None, "scale"):
        if not smoke.step("scale", "比例参考重画（只画道具和人物，素净背景）", scales):
            return False
        for a in REDRAWN:
            pid = smoke.product_of(f"asset:{a}", "ref_scale")
            smoke.keep_files(f"scale-{a}", smoke.latest(pid))
        if only == "scale":
            return True
    labels = {only} if only else set(REDO)
    for label in sorted(labels):
        unconfirm(smoke, label)
    _say_shots(smoke)
    if not _check(smoke):
        return False
    return _keyframes(smoke, labels)


def recheck(smoke: Smoke) -> bool:
    """分镜检查 again on the storyboard as it is (``--only recheck``)."""
    _say_shots(smoke)
    return _check(smoke)
