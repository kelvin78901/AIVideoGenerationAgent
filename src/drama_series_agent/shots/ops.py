"""The shot plan's payload (分镜规划, M4): rules over the model's answer, ids across reruns, and
the user's edits (patch, split, merge). Plain functions over JSON; the service reads and writes.

A payload is ``{"episode_id": …, "shots": [shot, …]}`` in episode order. A shot:

- ``id``, ``scene_id``, ``line_ids`` (the script lines it films, in script order);
- ``shot_type`` continuous / same_scene_cut / scene_change, ``framing``, ``camera_move``;
- ``duration_s`` (the plan's seconds) and ``manual_s`` (the user's), see ``timing.shot_duration``;
- ``intent`` (the seed of the keyframe prompt), ``summary``, ``sound``;
- ``asset_ids`` (its references), ``tail_from`` (a continuous shot: the shot whose last frame it
  starts from), ``tail_note``, ``audio_mode``, ``blocking`` ([{id, kind, label, x, y}], 0–1),
  ``difficulty`` (1–6).

The rules (M4 plan):

- every spoken line (dialogue, voice-over) is in exactly one shot, every other line in at least
  one; a line the model left out gets its own shot, except a voice-over, which lies over the
  shot before it;
- the first shot of a scene is never continuous;
- a continuous shot follows the last shot before it in the scene that is not an insert (a
  close-up without anyone in it: the note, the phone), so 1-08 follows 1-06 over the insert 1-07;
- references are the episode's assets only; without any, the ones the asset analysis found on
  its lines and the scene's place;
- no blocking from the model: the characters and props of its references, the camera by framing.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

SHOT_TYPES = ("continuous", "same_scene_cut", "scene_change")
FRAMINGS = ("wide", "medium", "close", "closeup")
MOVES = ("static", "push", "follow", "pan")
AUDIO_MODES = ("native", "tts", "none")
BLOCKING_KINDS = ("character", "camera", "prop", "landmark")
SPEAKING = ("dialogue", "vo")
# Where the camera stands on the top view for each framing (x, y; the action is up the page).
CAMERA = {"wide": (0.5, 0.92), "medium": (0.5, 0.8), "close": (0.38, 0.7), "closeup": (0.55, 0.62)}
SHORTEST_S = 1.0  # the plan's seconds are kept within these
LONGEST_S = 15.0
REACTION_S = 2.0  # the second half of a split one-line shot (a reaction, no lines)
PATCHABLE = (
    "shot_type",
    "framing",
    "camera_move",
    "manual_s",
    "asset_ids",
    "audio_mode",
    "blocking",
)


class ShotEditError(Exception):
    """An edit that cannot be made; ``code`` is the API error code."""

    def __init__(self, code: str, **params: Any) -> None:
        super().__init__(code)
        self.code = code
        self.params = params


def new_shot_id() -> str:
    return uuid.uuid4().hex


@dataclass(frozen=True)
class PlanLine:
    """A script line as the plan sees it (numbered across the episode: ``L1`` …)."""

    n: int
    scene_id: str
    line_id: str
    type: str
    text: str


@dataclass
class PlanContext:
    """What the rules need besides the model's answer."""

    episode_id: str
    scene_ids: list[str]
    lines: list[PlanLine]
    # The episode's assets: id → kind (character / scene / prop / text / voice), id → name.
    asset_kinds: dict[str, str]
    asset_names: dict[str, str] = field(default_factory=dict)
    # The asset analysis: assets on each line, and those over a whole scene (its place).
    line_assets: dict[str, list[str]] = field(default_factory=dict)
    scene_assets: dict[str, list[str]] = field(default_factory=dict)

    @property
    def characters(self) -> set[str]:
        return {a for a, k in self.asset_kinds.items() if k == "character"}


def shots_of(payload: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    return list((payload or {}).get("shots") or [])


def find_shot(payload: Mapping[str, Any], shot_id: str) -> dict[str, Any] | None:
    return next((s for s in shots_of(payload) if s.get("id") == shot_id), None)


def payload_of(episode_id: str, shots: list[dict[str, Any]]) -> dict[str, Any]:
    return {"episode_id": episode_id, "shots": shots}


# --------------------------------------------------------------------------- the model's answer


def normalize(
    answer: Mapping[str, Any], ctx: PlanContext, base: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """The version payload from the model's answer: lines mapped, the rules applied, ids carried
    over from ``base`` (the adopted plan)."""
    by_n = {line.n: line for line in ctx.lines}
    order = {line.line_id: line.n for line in ctx.lines}
    scene_of = {line.line_id: line.scene_id for line in ctx.lines}
    scene_rank = {sid: i for i, sid in enumerate(ctx.scene_ids)}
    drafts: list[dict[str, Any]] = []
    for i, raw in enumerate(answer.get("shots") or []):
        ids = [by_n[n].line_id for n in _ints(raw.get("lines")) if n in by_n]
        scene_id = scene_of[ids[0]] if ids else _scene_by_number(raw.get("scene"), ctx, drafts)
        if scene_id is None:
            continue
        drafts.append(
            {
                "no": i + 1,  # the model's numbering, for ``continues``
                "scene_id": scene_id,
                "line_ids": [x for x in ids if scene_of[x] == scene_id],
                "raw": raw,
            }
        )
    # Spoken lines once: the first shot that has one keeps it.
    seen: set[str] = set()
    types = {line.line_id: line.type for line in ctx.lines}
    for d in drafts:
        kept = []
        for x in d["line_ids"]:
            if types[x] in SPEAKING:
                if x in seen:
                    continue
                seen.add(x)
            if x not in kept:
                kept.append(x)
        d["line_ids"] = sorted(kept, key=order.__getitem__)
    drafts.sort(key=lambda d: scene_rank.get(d["scene_id"], len(scene_rank)))
    _cover(drafts, ctx)
    shots = [_shot(d, ctx) for d in drafts]
    for i, s in enumerate(shots):
        s["id"] = f"draft-{i}"  # until ``reconcile`` gives the real ones
    numbered = {d["no"]: s for d, s in zip(drafts, shots, strict=True) if d.get("no")}
    for d, s in zip(drafts, shots, strict=True):
        wanted = _int(d["raw"].get("continues"))
        target = numbered.get(wanted) if wanted is not None else None
        s["tail_from"] = target["id"] if target is not None and target is not s else None
    fix_types(shots, ctx.characters)
    for s in shots:
        if s["shot_type"] != "continuous":
            s["tail_note"] = None
    return payload_of(ctx.episode_id, reconcile(shots, base))


def _scene_by_number(
    value: Any, ctx: PlanContext, drafts: Sequence[Mapping[str, Any]]
) -> str | None:
    n = _int(value)
    if n is not None and 1 <= n <= len(ctx.scene_ids):
        return ctx.scene_ids[n - 1]
    if drafts:
        return str(drafts[-1]["scene_id"])
    return ctx.scene_ids[0] if ctx.scene_ids else None


def _cover(drafts: list[dict[str, Any]], ctx: PlanContext) -> None:
    """Lines no shot films: a voice-over lies over the shot before it; anything else gets a
    shot of its own, right after the shot of the line before."""
    covered = {x for d in drafts for x in d["line_ids"]}
    for line in ctx.lines:
        if line.line_id in covered:
            continue
        in_scene = [i for i, d in enumerate(drafts) if d["scene_id"] == line.scene_id]
        before = [i for i in in_scene if any(_n(ctx, x) < line.n for x in drafts[i]["line_ids"])]
        if line.type == "vo" and before:
            host = drafts[before[-1]]
            host["line_ids"] = sorted([*host["line_ids"], line.line_id], key=lambda x: _n(ctx, x))
        else:
            at = (
                before[-1] + 1
                if before
                else (in_scene[0] if in_scene else _scene_end(drafts, line.scene_id, ctx))
            )
            framing = "close" if line.type == "dialogue" else "medium"
            drafts.insert(
                at,
                {
                    "no": None,
                    "scene_id": line.scene_id,
                    "line_ids": [line.line_id],
                    "raw": {"framing": framing, "picture": line.text},
                },
            )
        covered.add(line.line_id)


def _scene_end(drafts: Sequence[Mapping[str, Any]], scene_id: str, ctx: PlanContext) -> int:
    """Where a scene with no shots yet goes: before the first shot of a later scene."""
    rank = {sid: i for i, sid in enumerate(ctx.scene_ids)}
    mine = rank.get(scene_id, len(rank))
    for i, d in enumerate(drafts):
        if rank.get(d["scene_id"], len(rank)) > mine:
            return i
    return len(drafts)


def _n(ctx: PlanContext, line_id: str) -> int:
    return next((x.n for x in ctx.lines if x.line_id == line_id), 0)


def _shot(d: Mapping[str, Any], ctx: PlanContext) -> dict[str, Any]:
    raw: Mapping[str, Any] = d["raw"]
    lines = {x.line_id: x for x in ctx.lines}
    texts = [lines[x].text for x in d["line_ids"] if lines[x].type not in SPEAKING]
    intent = _text(raw.get("picture")) or "".join(texts)
    framing = _pick(raw.get("framing"), FRAMINGS, "medium")
    refs = [a for a in _strs(raw.get("refs")) if a in ctx.asset_kinds]
    if not refs:
        refs = _rule_refs(d["scene_id"], d["line_ids"], ctx)
    has_vo = any(lines[x].type == "vo" for x in d["line_ids"])
    has_dialogue = any(lines[x].type == "dialogue" for x in d["line_ids"])
    audio_default = "tts" if has_vo and not has_dialogue else "native"
    return {
        "id": "",
        "scene_id": d["scene_id"],
        "line_ids": list(d["line_ids"]),
        "shot_type": _pick(raw.get("type"), SHOT_TYPES, "same_scene_cut"),
        "framing": framing,
        "camera_move": _pick(raw.get("move"), MOVES, "static"),
        "duration_s": _seconds(raw.get("seconds")),
        "manual_s": None,
        "intent": intent,
        "summary": _text(raw.get("summary")) or intent[:16],
        "sound": _text(raw.get("sound")) or None,
        "asset_ids": refs,
        "tail_from": None,
        "tail_note": _text(raw.get("note")) or None,
        "audio_mode": _pick(raw.get("audio"), AUDIO_MODES, audio_default),
        "blocking": blocking_of(
            raw.get("blocking"), refs, ctx.asset_kinds, framing, ctx.asset_names
        ),
        "difficulty": min(6, max(1, _int(raw.get("difficulty")) or 1)),
    }


def _rule_refs(scene_id: str, line_ids: Sequence[str], ctx: PlanContext) -> list[str]:
    refs: list[str] = []
    for a in [
        *ctx.scene_assets.get(scene_id, []),
        *(a for x in line_ids for a in ctx.line_assets.get(x, [])),
    ]:
        if a in ctx.asset_kinds and a not in refs:
            refs.append(a)
    return refs


def blocking_of(
    value: Any,
    refs: Sequence[str],
    kinds: Mapping[str, str],
    framing: str,
    names: Mapping[str, str],
) -> list[dict[str, Any]]:
    """The model's top view, cleaned; without one, the references by rule. One camera, placed
    by framing when the model left it out."""
    items: list[dict[str, Any]] = []
    for i, raw in enumerate(value if isinstance(value, list) else []):
        if not isinstance(raw, Mapping):
            continue
        kind = _pick(raw.get("kind"), BLOCKING_KINDS, "landmark")
        x, y = _unit(raw.get("x")), _unit(raw.get("y"))
        if x is None or y is None:
            continue
        label = _text(raw.get("label"))
        if kind == "camera":
            if any(it["kind"] == "camera" for it in items):
                continue
            items.append({"id": "camera", "kind": kind, "label": "", "x": x, "y": y})
            continue
        ident = _text(raw.get("id")) or f"{kind}-{i + 1}"
        items.append({"id": ident, "kind": kind, "label": label, "x": x, "y": y})
    if not any(it["kind"] != "camera" for it in items):
        people = [a for a in refs if kinds.get(a) == "character"]
        props = [a for a in refs if kinds.get(a) == "prop"]
        for row, (ids, y) in enumerate(((people, 0.4), (props, 0.55))):
            for j, a in enumerate(ids):
                items.append(
                    {
                        "id": a,
                        "kind": "character" if row == 0 else "prop",
                        "label": names.get(a, ""),
                        "x": round((j + 1) / (len(ids) + 1), 3),
                        "y": y,
                    }
                )
    if not any(it["kind"] == "camera" for it in items):
        cx, cy = CAMERA.get(framing, CAMERA["medium"])
        items.append({"id": "camera", "kind": "camera", "label": "", "x": cx, "y": cy})
    return items


def fix_types(shots: list[dict[str, Any]], characters: Iterable[str]) -> None:
    """The first shot of a scene is never continuous; a continuous shot follows an earlier shot
    of its scene (the one asked for, else the last that is not an insert); with none, it is a
    cut."""
    people = set(characters)
    for i, s in enumerate(shots):
        earlier = [t for t in shots[:i] if t["scene_id"] == s["scene_id"]]
        if not earlier:
            if s["shot_type"] == "continuous":
                s["shot_type"] = "scene_change"
            s["tail_from"] = None
            continue
        if s["shot_type"] != "continuous":
            s["tail_from"] = None
            continue
        if any(t["id"] == s.get("tail_from") for t in earlier):
            continue
        source = next((t for t in reversed(earlier) if not is_insert(t, people)), None)
        if source is None:
            s["shot_type"] = "same_scene_cut"
            s["tail_from"] = None
        else:
            s["tail_from"] = source["id"]


def is_insert(shot: Mapping[str, Any], characters: set[str]) -> bool:
    """A close-up with nobody in it (the note, the phone): a continuous shot skips over it."""
    return shot.get("framing") == "closeup" and not any(
        a in characters for a in shot.get("asset_ids") or []
    )


def reconcile(shots: list[dict[str, Any]], base: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """Ids from the adopted plan: a shot of the same scene filming most of the same lines, then
    shots without lines in order; the rest are new. ``tail_from`` follows the ids."""
    old = shots_of(base)
    taken: set[str] = set()
    ids: dict[int, str] = {}
    for i, s in enumerate(shots):
        mine = set(s["line_ids"])
        best, score = None, 0
        for o in old:
            if o["id"] in taken or o.get("scene_id") != s["scene_id"]:
                continue
            shared = len(mine & set(o.get("line_ids") or []))
            if shared > score:
                best, score = o["id"], shared
        if best is not None:
            ids[i] = best
            taken.add(best)
    for i, s in enumerate(shots):
        if i in ids or s["line_ids"]:
            continue
        spare = next(
            (
                o["id"]
                for o in old
                if o["id"] not in taken
                and o.get("scene_id") == s["scene_id"]
                and not o.get("line_ids")
            ),
            None,
        )
        if spare is not None:
            ids[i] = spare
            taken.add(spare)
    renamed: dict[str, str] = {}
    for i, s in enumerate(shots):
        new = ids.get(i) or new_shot_id()
        if s["id"]:
            renamed[s["id"]] = new
        s["id"] = new
    for s in shots:
        if s.get("tail_from") in renamed:
            s["tail_from"] = renamed[s["tail_from"]]
    return shots


# --------------------------------------------------------------------------- edits


def patch(
    payload: Mapping[str, Any],
    shot_id: str,
    changes: Mapping[str, Any],
    characters: Iterable[str] = (),
) -> dict[str, Any]:
    """改镜头设定: the fields in ``PATCHABLE`` (``manual_s`` None = back to automatic)."""
    shots = [dict(s) for s in shots_of(payload)]
    shot = next((s for s in shots if s["id"] == shot_id), None)
    if shot is None:
        raise ShotEditError("shot_not_found", id=shot_id)
    for key, value in changes.items():
        if key not in PATCHABLE:
            raise ShotEditError("invalid_field", field=key)
        if key == "shot_type":
            shot[key] = _must(value, SHOT_TYPES, key)
        elif key == "framing":
            shot[key] = _must(value, FRAMINGS, key)
        elif key == "camera_move":
            shot[key] = _must(value, MOVES, key)
        elif key == "audio_mode":
            shot[key] = _must(value, AUDIO_MODES, key)
        else:
            shot[key] = value
    if shot["shot_type"] == "continuous" and changes.get("shot_type") == "continuous":
        earlier = [s for s in shots[: shots.index(shot)] if s["scene_id"] == shot["scene_id"]]
        if not earlier:
            raise ShotEditError("no_shot_to_continue", id=shot_id)
        shot["tail_from"] = None
    fix_types(shots, characters)
    return payload_of(str(payload.get("episode_id") or ""), shots)


def split(
    payload: Mapping[str, Any],
    shot_id: str,
    line_types: Mapping[str, str],
    after_line_id: str | None = None,
    new_id: str | None = None,
) -> tuple[dict[str, Any], str]:
    """拆分: the shot's lines cut after ``after_line_id`` (default: the middle). One line: an
    action line is filmed by both, a spoken one stays in the first and the second is a reaction
    shot. The second shot copies the first's settings; what continued the shot now continues
    the second half. Returns the payload and the new shot's id."""
    shots = [dict(s) for s in shots_of(payload)]
    i = next((k for k, s in enumerate(shots) if s["id"] == shot_id), None)
    if i is None:
        raise ShotEditError("shot_not_found", id=shot_id)
    first = shots[i]
    lines = list(first.get("line_ids") or [])
    if after_line_id is not None:
        if after_line_id not in lines[:-1]:
            raise ShotEditError("split_point_invalid", id=after_line_id)
        cut = lines.index(after_line_id) + 1
        head, tail = lines[:cut], lines[cut:]
    elif len(lines) >= 2:
        cut = (len(lines) + 1) // 2
        head, tail = lines[:cut], lines[cut:]
    elif lines and line_types.get(lines[0]) not in SPEAKING:
        head, tail = lines, list(lines)
    else:
        head, tail = lines, []
    second = dict(first)
    second["id"] = new_id or new_shot_id()
    second["line_ids"] = tail
    second["shot_type"] = "same_scene_cut"
    second["tail_from"] = None
    second["tail_note"] = None
    second["blocking"] = [dict(b) for b in first.get("blocking") or []]
    first["line_ids"] = head
    planned = first.get("duration_s") or None
    if tail:
        half = max(SHORTEST_S, round((planned or 2 * REACTION_S) / 2, 1))
        first["duration_s"] = second["duration_s"] = half
    else:
        second["duration_s"] = REACTION_S
    first["manual_s"] = second["manual_s"] = None
    for s in shots:
        if s.get("tail_from") == shot_id and s is not first:
            s["tail_from"] = second["id"]
    shots.insert(i + 1, second)
    return payload_of(str(payload.get("episode_id") or ""), shots), second["id"]


def merge(
    payload: Mapping[str, Any], shot_id: str, order: Mapping[str, int]
) -> tuple[dict[str, Any], str]:
    """和下一个合并: the next shot of the same scene folds into this one (lines, references and
    the plan's seconds added up). Returns the payload and the id that went."""
    shots = [dict(s) for s in shots_of(payload)]
    i = next((k for k, s in enumerate(shots) if s["id"] == shot_id), None)
    if i is None:
        raise ShotEditError("shot_not_found", id=shot_id)
    if i + 1 >= len(shots) or shots[i + 1]["scene_id"] != shots[i]["scene_id"]:
        raise ShotEditError("no_next_shot", id=shot_id)
    first, gone = shots[i], shots[i + 1]
    lines = dict.fromkeys([*(first.get("line_ids") or []), *(gone.get("line_ids") or [])])
    first["line_ids"] = sorted(lines, key=lambda x: order.get(x, 0))
    first["asset_ids"] = list(
        dict.fromkeys([*(first.get("asset_ids") or []), *(gone.get("asset_ids") or [])])
    )
    a, b = first.get("duration_s"), gone.get("duration_s")
    first["duration_s"] = round(a + b, 3) if a and b else (a or b)
    first["manual_s"] = None
    sounds = [x for x in (first.get("sound"), gone.get("sound")) if x]
    first["sound"] = "；".join(dict.fromkeys(sounds)) or None
    del shots[i + 1]
    for s in shots:
        if s.get("tail_from") == gone["id"]:
            s["tail_from"] = first["id"]
    return payload_of(str(payload.get("episode_id") or ""), shots), gone["id"]


# --------------------------------------------------------------------------- helpers


def _must(value: Any, choices: Sequence[str], key: str) -> str:
    if value not in choices:
        raise ShotEditError("invalid_value", field=key, value=str(value))
    return str(value)


def _pick(value: Any, choices: Sequence[str], default: str) -> str:
    return str(value) if value in choices else default


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _ints(value: Any) -> list[int]:
    return [n for v in (value if isinstance(value, list) else []) if (n := _int(v)) is not None]


def _strs(value: Any) -> list[str]:
    return [str(v) for v in (value if isinstance(value, list) else []) if isinstance(v, str)]


def _seconds(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return round(min(LONGEST_S, max(SHORTEST_S, float(value))), 1)


def _unit(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return round(min(1.0, max(0.0, float(value))), 3)
