"""分镜检查 by rules (M5.5): what a plan can get wrong that run 17 showed, read straight off the
plan and the script, free and at once. Only a warning: confirming goes on (Kelvin 2026-11-10).

- ``undone``: a change made, undone and made again in one shot (1-08: 拉开门，又关上……再拉开);
- ``insert_event``: an insert (nobody in it) whose picture or action has something happen to the
  object (1-03: 雨水把字一点点泡开): a state is set, not acted;
- ``replay``: the shot looks like a replay of the last one with someone in it in the same scene,
  same framing, both static, an insert between them or a cut (1-06 → 1-08);
- ``inner_mouth``: an inner voice in a shot whose picture or action has the speaker talk;
- ``state_jump``: a continuous shot that starts unlike the shot it follows ends.

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
TALKING = re.compile(r"开口|说话|张嘴|嘴唇(?:在)?动|低声说|喃喃|念叨|自言自语")


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
) -> list[Issue]:
    """Every rule over the plan's shots in order; ``contracts``: each shot's effective contract
    (``shots.contract.effective``)."""
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
        words = "；".join([str(s.get("intent") or ""), *action])
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
