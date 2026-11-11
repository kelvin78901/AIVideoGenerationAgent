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
"""

from __future__ import annotations

import time
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
        "asset_ids": None,  # without the umbrella: it stays outside (filled in by ``revise``)
        "contract": {
            "kind": "action",
            "beats": 2,
            "start": [{"subject": LINWAN, "state": "站在门外，伞仍靠在门边墙上"}],
            "end": [{"subject": LINWAN, "state": "在屋里，背靠着关上的门"}],
            "props": [],
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
SCALE_WAIT_S = 900


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


def _props(smoke: Smoke) -> bool:
    def draw() -> list[str]:
        for a in REDRAWN:
            try:
                unlock(smoke, a)
            except RuntimeError as exc:
                if "not_locked" not in str(exc):
                    raise
        return [smoke.run(f"demo-p-asset-{a}")["id"] for a in REDRAWN]

    if not smoke.step("props", "红伞、便利贴本机重画（实拍质感、真实尺寸、便利贴带字）", draw):
        return False
    for a in REDRAWN:
        version = smoke.latest(f"demo-p-asset-{a}")
        smoke.keep_files(f"prop-{a}", version)
        cands = version["payload"].get("candidates") or []
        idx = next((i for i, c in enumerate(cands) if c.get("ocr_ok")), 0)
        smoke.post(f"/assets/{a}/lock", {"idx": idx})
        smoke.say(f"   {a}: locked candidate {idx}")
    # Locking a prop draws its 比例参考 (``scale``) on its own.
    deadline = time.monotonic() + SCALE_WAIT_S
    for a in REDRAWN:
        pid = smoke.product_of(f"asset:{a}", "ref_scale")
        while True:
            p = smoke.get(f"/products/{pid}")
            if p["adopted_version_id"] or p["status"] == "failed":
                break
            if time.monotonic() > deadline:
                smoke.say(f"   {a}: no scale reference after {SCALE_WAIT_S} s")
                smoke.ok = False
                break
            time.sleep(2)
        if p["adopted_version_id"]:
            version = next(v for v in p["versions"] if v["id"] == p["adopted_version_id"])
            smoke.keep_files(f"scale-{a}", version)
            smoke.say(f"   {a}: scale reference with {version['payload'].get('character')}")
        else:
            smoke.say(f"   {a}: scale reference {p['status']}")
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
        props = "；".join(f"{x['asset_id']}:{x['state']}" for x in c["props"])
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


def _keyframes(smoke: Smoke, labels: set[str] | None = None) -> bool:
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
        smoke.keep_files(f"kf-{s['label']}", version)
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
    smoke.post("/gates/storyboard/confirm", {"scope_id": "demo-e1"})
    board = smoke.get("/episodes/demo-e1/progress")["steps"]["storyboard"]
    smoke.say(f"   分镜 {board['state']} {board['done']}/{board['total']}")
    return True


def prepare(smoke: Smoke) -> bool:
    _settings(smoke)
    return _props(smoke) and _plan(smoke) and _keyframes(smoke)


def revise(smoke: Smoke) -> bool:
    """The storyboard fixed by its check (``REVISIONS``), checked again, the changed shots'
    keyframes drawn again; then 分镜确认."""
    smoke.say("== revise: 按分镜检查改分镜（PATCH /shots，和分镜页一样）")
    by_label = shots(smoke)
    for label, patch in REVISIONS.items():
        shot = by_label[label]
        unconfirm(smoke, label)
        body = dict(patch)
        if "asset_ids" in body:
            body["asset_ids"] = [a for a in shot["asset_ids"] if a != "umbrella"]
        resp = smoke.client.patch(f"/api/v1/shots/{shot['id']}", json=body)
        smoke.say(f"   {label}: {', '.join(body)}（{resp.status_code}）")
        if resp.status_code != 200:
            smoke.say(f"      {resp.text}")
            smoke.ok = False
    # A shot that starts where the one before ended (1-08) follows 1-06's new end.
    _say_shots(smoke)
    if not _check(smoke):
        return False
    return _keyframes(smoke, set(REVISIONS))


def recheck(smoke: Smoke) -> bool:
    """分镜检查 again on the storyboard as it is (``--only recheck``)."""
    _say_shots(smoke)
    return _check(smoke)
