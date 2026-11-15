"""分镜检查 by rules (M5.5): what a plan can get wrong that run 17 showed, read straight off the
plan and the script, free and at once. Only a warning: confirming goes on (Kelvin 2026-11-10).

- ``undone``: a change made, undone and made again in one shot (1-08: 拉开门，又关上……再拉开);
- ``insert_event``: an insert (nobody in it) whose picture or action has something happen to the
  object (1-03: 雨水把字一点点泡开): a state is set, not acted;
- ``replay``: the shot looks like a replay of the last one with someone in it in the same scene,
  same framing, both static, an insert between them or a cut (1-06 → 1-08);
- ``inner_mouth``: an inner voice in a shot whose picture or action has the speaker talk;
- ``state_jump``: a continuous shot that starts unlike the shot it follows ends;
- ``cross_space``: someone starts or ends outside the place the shot is in (1-06 in 林晚出租屋
  starting 「站在门外」: the keyframe put the camera in the stairwell, she shut herself out);
- ``crowded``: going through a doorway and doing something else, or more than three actions
  (run 19's 1-06: 推门、进门、转身、关门、靠门 in six seconds, the door went through her);
- ``lines_dropped``: the script's action lines a shot films do either (``lines_fault``), so the
  shot is filmed from its picture alone and the rules read the picture (run 20's 1-10 / 1-11:
  「拉开门，又关上……再拉开」 against a plan that split the door into shots).

The plan check by a model (``pipeline/components/plancheck.py``) adds what rules cannot see.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from drama_series_agent.shots.contract import SpokenLine, effective

# Changes and their undoing, in the script's words.
OPPOSITES: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("拉开", "打开", "推开", "开门", "开了门"), ("关上", "关门", "合上", "带上门", "掩上")),
    (("拿起", "捡起", "提起", "拿走"), ("放下", "放回", "靠回", "搁下", "扔下")),
    (("开灯", "打开灯"), ("关灯", "熄灯")),
    (("坐下",), ("站起", "起身")),
)
# Something happening to an object (not set before the shot).
EVENTS = re.compile(
    r"泡开|晕开|流下|淌下|倒水|倒出|溅|掉落|掉下|炸开|破碎|碎了|燃起|融化|被风吹|吹走|飞走"
)
# Where a state puts someone, against the place the shot is in (``cross_space``): out of a
# room, or into one from a passage. Looking or heading there is not being there (1-08's
# 「望向门外地上」).
OUT_OF_ROOM = re.compile(r"(?<![向着朝往])(?:门外|窗外|屋外|楼道|走廊|街上)")
IN_ROOM = re.compile(r"(?<![向着朝往])(?:屋里|屋内|房间里|房里|进屋)")
PASSAGE = re.compile(r"楼道|走廊|门口|楼梯|街|院子|天台")
TALKING = re.compile(r"开口|说话|张嘴|嘴唇(?:在)?动|低声说|喃喃|念叨|自言自语")
# ``crowded``: going through a doorway, a door opened to go through, and what counts as one
# action in a clause (「靠在」「坐在」「握着」 is how someone is, not something done).
THROUGH = re.compile(
    r"进门|进屋|进了门|进了屋|走进|走出|跨进|跨出|迈进|迈出|跨过门槛|迈过门槛|推门而入|夺门而出"
    r"|出门|出了门|进来|出去"
)
DOOR_OPEN = re.compile(r"推开门|推门|拉开门|打开门|开门")
ACTS = re.compile(
    r"(?:推|拉开|拉上|打开|关上|关门|开门|合上|带上|掩上|走|跑|迈|跨|进|出门|出去|转身|回头|抬头"
    r"|低头|抬起|弯腰|蹲|坐|站起|起身|拿|捡|提起|放下|放回|搁|扔|靠|抵|倚|撕|摸|握|抓|捏|擦|掏"
    r"|递|接过|抱起|伸手|挥|按|敲|翻|拨|捂|扶|攥|脱|穿上|戴上|喝)(?![在着])"
)
CLAUSES = re.compile(r"[，,。；;！!？?、]")
MAX_ACTIONS = 3  # more than this in one shot is crowded even without a doorway


# A rule's finding in words, for a prompt (the page words it from ``checks.code.*``, zh-CN).
RULE_WORDS = {
    "undone": "同一个变化做了又撤销再做：{steps}。犹豫可以演成停住、吸气。",
    "insert_event": "插入镜头里东西发生了变化（「{words}」）：状态应该摆好，不在镜头里发生。",
    "replay": "和 {other} 同一场、同景别、都是固定机位，接起来像回放。",
    "inner_mouth": "内心独白的镜头写了「{words}」：内心独白时嘴闭着。",
    "state_jump": "开始时和 {other} 的结束时对不上（{subject}）。",
    "cross_space": (
        "开始或结束时写了「{words}」，可镜头在「{place}」里拍：要拍那一侧，就分成两个镜头或换场景。"
    ),
    "crowded": "一个镜头里动作太多：{actions}。进门 / 出门单独一个镜头，其余的拆到下一个镜头。",
    "lines_dropped": "剧本这几行动作拍不了（{words}），视频只按画面描述拍，不读这几行。",
}


def describe(issue: Mapping[str, Any]) -> str:
    """A finding (``Issue.as_json()``) in words: the model's as it said it, a rule's from
    ``RULE_WORDS``."""
    if issue.get("source") != "rule":
        return str(issue.get("text") or "")
    words = RULE_WORDS.get(str(issue.get("code")))
    params = issue.get("params") or {}
    try:
        return words.format(**params) if words else str(issue.get("code"))
    except KeyError:
        return str(issue.get("code"))


@dataclass(frozen=True)
class Issue:
    shot_id: str
    code: str
    params: dict[str, str]
    source: str = "rule"  # or the model's (``llm``)
    text: str = ""  # the model's own words (``llm``); rules are worded by the front end

    def as_json(self) -> dict[str, Any]:
        return {
            "shot_id": self.shot_id,
            "code": self.code,
            "params": dict(self.params),
            "source": self.source,
            "text": self.text,
        }


@dataclass(frozen=True)
class LineInfo:
    type: str
    text: str
    tone: str = ""


def labels(episode_idx: int, shots: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    """Shot id → 「1-04」."""
    return {str(s["id"]): f"{episode_idx}-{i:02d}" for i, s in enumerate(shots, 1)}


def script_lines(script: Mapping[str, Any]) -> dict[str, LineInfo]:
    """The adopted script's lines by id."""
    return {
        str(x["id"]): LineInfo(
            str(x.get("type") or "action"), str(x.get("text") or ""), str(x.get("tone") or "")
        )
        for scene in script.get("scenes") or []
        for x in scene.get("lines") or []
    }


def contracts_of(
    shots: Sequence[Mapping[str, Any]],
    lines: Mapping[str, LineInfo],
    asset_kinds: Mapping[str, str],
) -> dict[str, dict[str, Any]]:
    """Each shot's effective contract (``shots.contract.effective``)."""
    by_id = {str(s["id"]): s for s in shots}
    out: dict[str, dict[str, Any]] = {}
    for s in shots:
        spoken = [
            SpokenLine(x, n, lines[x].type, lines[x].tone)
            for n, x in enumerate(s.get("line_ids") or [], 1)
            if x in lines
        ]
        out[str(s["id"])] = effective(s, spoken, asset_kinds, by_id)
    return out


def check(
    shots: Sequence[Mapping[str, Any]],
    labels: Mapping[str, str],
    lines: Mapping[str, LineInfo],
    contracts: Mapping[str, Mapping[str, Any]],
    places: Mapping[str, str] | None = None,
) -> list[Issue]:
    """Every rule over the plan's shots in order; ``contracts``: each shot's effective contract
    (``shots.contract.effective``); ``places``: scene id → where it is (``scene_place``), for
    ``cross_space``."""
    out: list[Issue] = []
    by_id = {str(s["id"]): s for s in shots}
    for i, s in enumerate(shots):
        sid = str(s["id"])
        c = contracts.get(sid) or {}
        # A picture the user wrote says what is filmed; the video reads it alone (``vid``).
        action = (
            []
            if s.get("picture_edited")
            else [lines[x].text for x in s.get("line_ids") or [] if x in lines and _acted(lines[x])]
        )
        # So does the plan's picture when the script's lines undo themselves or crowd the shot
        # (Kelvin 2026-11-11, run 20): said once, then read no more.
        if (fault := lines_fault(action, c)) is not None:
            out.append(Issue(sid, "lines_dropped", {"words": fault}))
            action = []
        words = "；".join([str(s.get("intent") or ""), *action])
        # The picture and the script's lines tell the same actions: each is counted alone.
        for told in (str(s.get("intent") or ""), "；".join(action)):
            if (acts := crowded(told, c)) is not None:
                out.append(Issue(sid, "crowded", {"actions": "、".join(acts)}))
                break
        if (steps := undone(words)) is not None:
            out.append(Issue(sid, "undone", {"steps": " → ".join(steps)}))
        if c.get("kind") == "insert" and (m := EVENTS.search(words)):
            out.append(Issue(sid, "insert_event", {"words": m.group(0)}))
        inner = [x for x, how in (c.get("delivery") or {}).items() if how == "inner"]
        if inner and (m := TALKING.search(words)):
            out.append(Issue(sid, "inner_mouth", {"words": m.group(0)}))
        before = _last_with_people(shots[:i], s, contracts)
        if before is not None and _looks_the_same(before, s, shots[:i]):
            out.append(
                Issue(
                    sid,
                    "replay",
                    {"other": labels.get(str(before["id"]), ""), "framing": str(s["framing"])},
                )
            )
        place = (places or {}).get(str(s.get("scene_id") or ""))
        if place and (outside := cross_space(place, [*c.get("start", []), *c.get("end", [])])):
            out.append(Issue(sid, "cross_space", {"words": outside, "place": place}))
        source = by_id.get(str(s.get("tail_from") or ""))
        if source is not None and not c.get("start_inherited"):
            jump = state_jump((contracts.get(str(source["id"])) or {}).get("end"), c.get("start"))
            if jump is not None:
                out.append(
                    Issue(
                        sid,
                        "state_jump",
                        {"other": labels.get(str(source["id"]), ""), "subject": jump},
                    )
                )
    return out


def cross_space(place: str, states: Sequence[Mapping[str, Any]]) -> str | None:
    """The words that put someone outside ``place`` (a room: 门外, 楼道…; a passage: 屋里…)."""
    outside = IN_ROOM if PASSAGE.search(place) else OUT_OF_ROOM
    for st in states:
        if m := outside.search(str(st.get("state") or "")):
            return m.group(0)
    return None


def lines_fault(lines: Sequence[str], contract: Mapping[str, Any] | None = None) -> str | None:
    """What is wrong with the script's action lines a shot films, when they cannot be filmed as
    they are (a change undone and made again, or too much for one shot: ``undone``,
    ``crowded``), else None. Then the shot is filmed from its picture alone (``vid.gather``)."""
    told = "；".join(x for x in lines if x)
    if not told:
        return None
    if (steps := undone(told)) is not None:
        return " → ".join(steps)
    if (acts := crowded(told, contract)) is not None:
        return "、".join(acts)
    return None


def crowded(text: str, contract: Mapping[str, Any] | None = None) -> list[str] | None:
    """The clauses of ``text`` that are actions when there are too many for one shot, else None:
    going through a doorway and doing anything else (run 19's 1-06: 推门、进门、转身、关门、靠门 in
    six seconds, the door went through her), or more than ``MAX_ACTIONS``. A door opened to go
    through is part of going through; ``contract``'s start on one side and end on the other is a
    doorway gone through as well."""
    acts = [x.strip() for x in CLAUSES.split(text) if ACTS.search(x)]
    through = any(THROUGH.search(x) for x in acts) or _crosses(contract or {})
    others = [x for x in acts if not THROUGH.search(x) and not DOOR_OPEN.search(x)]
    if (through and others) or len(acts) > MAX_ACTIONS:
        return acts
    return None


def _crosses(contract: Mapping[str, Any]) -> bool:
    """Someone starts outside a room and ends in it, or the other way round."""

    def said(key: str, where: re.Pattern[str]) -> bool:
        return any(where.search(str(x.get("state") or "")) for x in contract.get(key) or [])

    return (said("start", OUT_OF_ROOM) and said("end", IN_ROOM)) or (
        said("start", IN_ROOM) and said("end", OUT_OF_ROOM)
    )


def undone(text: str) -> list[str] | None:
    """The first change made, undone and made again in ``text`` (its three words), else None."""
    for made, unmade in OPPOSITES:
        hits = sorted(
            [(m.start(), w, 0) for w in made for m in re.finditer(re.escape(w), text)]
            + [(m.start(), w, 1) for w in unmade for m in re.finditer(re.escape(w), text)]
        )
        seq: list[tuple[str, int]] = []
        for _, w, side in hits:
            if not seq or seq[-1][1] != side:
                seq.append((w, side))
            if len(seq) >= 3:
                return [w for w, _ in seq[:3]]
    return None


def state_jump(
    end: Sequence[Mapping[str, str]] | None, start: Sequence[Mapping[str, str]] | None
) -> str | None:
    """A subject in both whose states differ (the first one), else None."""
    ended = {str(x["subject"]): str(x["state"]) for x in end or []}
    for x in start or []:
        was = ended.get(str(x["subject"]))
        if was is not None and was != str(x["state"]):
            return str(x["subject"])
    return None


def _acted(line: LineInfo) -> bool:
    return line.type not in ("dialogue", "vo")


def _last_with_people(
    earlier: Sequence[Mapping[str, Any]],
    shot: Mapping[str, Any],
    contracts: Mapping[str, Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    if (contracts.get(str(shot["id"])) or {}).get("kind") == "insert":
        return None
    for s in reversed(earlier):
        if s["scene_id"] != shot["scene_id"]:
            return None
        if (contracts.get(str(s["id"])) or {}).get("kind") != "insert":
            found: Mapping[str, Any] = s
            return found
    return None


def _looks_the_same(
    before: Mapping[str, Any], shot: Mapping[str, Any], earlier: Sequence[Mapping[str, Any]]
) -> bool:
    """Same framing, both static, and seen as a new shot: a cut, or an insert between them (a
    continuous shot right after the one it continues reads as one take)."""
    if before["framing"] != shot["framing"]:
        return False
    if before.get("camera_move") != "static" or shot.get("camera_move") != "static":
        return False
    between = earlier.index(before) < len(earlier) - 1
    return shot.get("shot_type") != "continuous" or between
