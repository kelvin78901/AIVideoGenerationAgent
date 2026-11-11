"""镜头契约 (M5.5): what a shot promises, as data, so every step after the plan can be held to it.

Kelvin's run 17 showed what free text lets through (``reports/m5-quality-defects.md``): a door
opened, shut and opened again; a still insert that grew a stream of water; an inner voice that
sounded like speech. The contract carries:

- ``kind``: performance (someone acts), action (movement is the point), dialogue (someone
  speaks on screen), insert (nobody: the note, the phone). ``beats`` is its action budget: an
  insert gets 0 (only small motion: light, a drop, a slow drift; nothing happens), the others at
  most ``MAX_BEATS``;
- ``start`` / ``end``: what people and things look like when the shot begins and ends
  (``[{subject, state}]``). The keyframe draws ``start``; a continuous shot with no ``start`` of
  its own begins where the shot it follows ``end``\\s (``effective``);
- ``props``: ``[{asset_id, state}]``, the state each prop is *in* (the note has writing on it, its
  corner is wet); a state is set, not acted, unless the shot's action is that change. A prop the
  shot uses without a state keeps the last one the scene gave it (``props_inherited``); a prop of
  the scene that a state puts another one on or by (the note 「贴在伞柄上」) is in the shot too,
  in its last state (``props_linked``; run 19: 1-04 drew the note with no umbrella, and a black
  one from another reference);
- ``delivery``: each spoken line, ``dialogue`` (lips move), ``offscreen`` (the speaker is not in
  the picture) or ``inner`` (内心独白: the mouth stays shut). Neither of the last two is in the take
  (M5 step 15p); the edit lays them.

The plan writes it (``build`` over the model's answer, rules filling what it left out); the user
edits it (``patch``). Plain functions over JSON, like ``shots/ops.py``.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

KINDS = ("performance", "action", "dialogue", "insert")
DELIVERIES = ("dialogue", "offscreen", "inner")
MAX_BEATS = {"insert": 0, "performance": 2, "dialogue": 2, "action": 4}
MAX_STATES = 8  # rows of start / end / props kept
_INNER_TONES = ("OS", "内心", "心声", "独白")
# Where a state puts a prop: 「贴在伞柄上」, 「靠在门边墙上」 (the place, up to the punctuation).
_PLACE = re.compile(r"在([^，。；、,;：:]{1,12})")


class ContractError(Exception):
    """A contract edit that cannot be made; ``code`` is the API error code."""

    def __init__(self, code: str, **params: Any) -> None:
        super().__init__(code)
        self.code = code
        self.params = params


@dataclass(frozen=True)
class SpokenLine:
    """A line a shot films, as the contract sees it."""

    line_id: str
    n: int  # its number across the episode (``L3`` in the plan's prompt)
    type: str  # dialogue / vo (anything else is not spoken)
    tone: str = ""


def default_delivery(line_type: str, tone: str | None) -> str:
    """How a line is said when nobody chose: a voice-over marked OS (or 内心…) is an inner
    voice, any other voice-over is offscreen, dialogue is said on screen."""
    if line_type != "vo":
        return "dialogue"
    t = (tone or "").strip()
    if any(x in t.upper() if x == "OS" else x in t for x in _INNER_TONES):
        return "inner"
    return "offscreen"


def build(
    raw: Mapping[str, Any],
    lines: Sequence[SpokenLine],
    refs: Sequence[str],
    asset_kinds: Mapping[str, str],
    asset_names: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """The contract from the plan model's answer for one shot (missing or wrong fields by rule).

    ``lines``: the spoken lines the shot films; ``refs``: its references."""
    spoken = [x for x in lines if x.type in ("dialogue", "vo")]
    asked = _delivery_asked(raw.get("delivery"), spoken)
    delivery = {x.line_id: asked.get(x.line_id) or default_delivery(x.type, x.tone) for x in spoken}
    kind = _kind(raw.get("kind"), delivery, refs, asset_kinds)
    return {
        "kind": kind,
        "beats": _beats(raw.get("beats"), kind),
        "start": _states(raw.get("start")),
        "end": _states(raw.get("end")),
        "props": _props(raw.get("props"), refs, asset_kinds, asset_names or {}),
        "delivery": delivery,
    }


def default(
    lines: Sequence[SpokenLine], refs: Sequence[str], asset_kinds: Mapping[str, str]
) -> dict[str, Any]:
    """The contract of a shot planned before M5.5 (no ``contract`` in its payload)."""
    return build({}, lines, refs, asset_kinds)


def patch(
    old: Mapping[str, Any],
    changes: Mapping[str, Any],
    line_ids: Iterable[str],
    refs: Sequence[str],
    asset_kinds: Mapping[str, str],
) -> dict[str, Any]:
    """改镜头契约: any of ``kind``, ``beats``, ``start``, ``end``, ``props``, ``delivery``. Values
    are checked, not repaired (``ContractError``); ``beats`` follows a new ``kind`` down to its
    budget unless given."""
    out = dict(old)
    for key in changes:
        if key not in ("kind", "beats", "start", "end", "props", "delivery"):
            raise ContractError("invalid_field", field=f"contract.{key}")
    if "kind" in changes:
        if changes["kind"] not in KINDS:
            raise ContractError("invalid_value", field="contract.kind", value=changes["kind"])
        out["kind"] = changes["kind"]
        if "beats" not in changes:
            out["beats"] = min(int(out.get("beats") or 0), MAX_BEATS[out["kind"]])
            if out["kind"] != "insert" and out["beats"] == 0:
                out["beats"] = 1
    if "beats" in changes:
        beats = changes["beats"]
        top = MAX_BEATS[str(out.get("kind") or "performance")]
        if not isinstance(beats, int) or isinstance(beats, bool) or not 0 <= beats <= top:
            raise ContractError("invalid_value", field="contract.beats", value=beats)
        out["beats"] = beats
    for key in ("start", "end"):
        if key in changes:
            out[key] = _states(changes[key], strict=True)
    if "props" in changes:
        props = _props(changes["props"], refs, asset_kinds, {}, strict=True)
        out["props"] = props
    if "delivery" in changes:
        mine = set(line_ids)
        delivery = dict(out.get("delivery") or {})
        for line_id, how in dict(changes["delivery"] or {}).items():
            if line_id not in mine or line_id not in delivery:
                raise ContractError("invalid_value", field="contract.delivery", value=line_id)
            if how not in DELIVERIES:
                raise ContractError("invalid_value", field="contract.delivery", value=how)
            delivery[line_id] = how
        out["delivery"] = delivery
    return out


def effective(
    shot: Mapping[str, Any],
    lines: Sequence[SpokenLine],
    asset_kinds: Mapping[str, str],
    shots_by_id: Mapping[str, Mapping[str, Any]] | None = None,
    prop_names: Mapping[str, Sequence[str]] | None = None,
) -> dict[str, Any]:
    """The contract a shot is held to: its own, or the default for an old plan; spoken lines it
    no longer films dropped and new ones given their default; a continuous shot without a
    ``start`` begins at the ``end`` of the shot it follows (``start_inherited``).

    ``shots_by_id``: the episode's shots in plan order (the scene's earlier shots give the props
    their states, see the module's docstring); ``prop_names``: the series' props, id → name and
    aliases, to find a prop a state names (``props_linked``; without it, none are). The props
    that come from another shot say which one in ``props_from``."""
    refs = list(shot.get("asset_ids") or [])
    stored = shot.get("contract")
    out = dict(stored) if isinstance(stored, Mapping) else default(lines, refs, asset_kinds)
    given = dict(out.get("delivery") or {})
    out["delivery"] = {
        x.line_id: given.get(x.line_id) or default_delivery(x.type, x.tone)
        for x in lines
        if x.type in ("dialogue", "vo")
    }
    out["start_inherited"] = False
    source = (shots_by_id or {}).get(str(shot.get("tail_from") or ""))
    if not out.get("start") and shot.get("shot_type") == "continuous" and source is not None:
        before = source.get("contract") if isinstance(source.get("contract"), Mapping) else {}
        if before and before.get("end"):
            out["start"] = list(before["end"])
            out["start_inherited"] = True
    out["props"], out["props_inherited"], out["props_linked"], out["props_from"] = _scene_props(
        shot, list(out.get("props") or []), refs, asset_kinds, shots_by_id, prop_names
    )
    return out


def _scene_props(
    shot: Mapping[str, Any],
    props: list[dict[str, str]],
    refs: Sequence[str],
    asset_kinds: Mapping[str, str],
    shots_by_id: Mapping[str, Mapping[str, Any]] | None,
    prop_names: Mapping[str, Sequence[str]] | None,
) -> tuple[list[dict[str, str]], list[str], list[str], dict[str, str]]:
    """The shot's props with what its scene said before (``effective``)."""
    last: dict[str, tuple[str, str]] = {}  # prop → (its last state, the shot that said it)
    for s in shots_by_id.values() if shots_by_id else ():
        if s.get("id") == shot.get("id"):
            break
        if s.get("scene_id") != shot.get("scene_id"):
            continue
        stored = s.get("contract")
        c: Mapping[str, Any] = stored if isinstance(stored, Mapping) else {}
        for p in c.get("props") or []:
            if p.get("asset_id") and p.get("state"):
                last[str(p["asset_id"])] = (str(p["state"]), str(s["id"]))
    out = list(props)
    inherited: list[str] = []
    linked: list[str] = []
    origin: dict[str, str] = {}
    have = {p["asset_id"] for p in out}
    for a in refs:
        if asset_kinds.get(a) == "prop" and a not in have and a in last:
            out.append({"asset_id": a, "state": last[a][0]})
            inherited.append(a)
            origin[a] = last[a][1]
            have.add(a)
    for a, (state, source) in last.items():
        if a in have or a in refs or not prop_names:
            continue
        if any(names_in(p["state"], prop_names.get(a) or ()) for p in out):
            out.append({"asset_id": a, "state": state})
            linked.append(a)
            origin[a] = source
            have.add(a)
    return out, inherited, linked, origin


def names_in(text: str, names: Iterable[str]) -> bool:
    """Whether ``text`` names a prop: one of its names, or its last character in the place a
    state puts something (「贴在伞柄上」 names 红色长柄伞 by 伞)."""
    full = [n for n in names if n]
    if any(n in text for n in full):
        return True
    heads = {n[-1] for n in full}
    return any(h in place for place in _PLACE.findall(text) for h in heads)


def speaks_on_screen(contract: Mapping[str, Any], line_id: str) -> bool:
    return (contract.get("delivery") or {}).get(line_id) == "dialogue"


# --------------------------------------------------------------------------- the rules


def _kind(
    value: Any, delivery: Mapping[str, str], refs: Sequence[str], asset_kinds: Mapping[str, str]
) -> str:
    people = any(asset_kinds.get(a) == "character" for a in refs)
    talks = any(v == "dialogue" for v in delivery.values())
    kind = value if value in KINDS else None
    if kind == "insert" and (people or talks):
        kind = None  # someone is in it: not an insert
    if kind is None:
        kind = "dialogue" if talks else ("performance" if people else "insert")
    return str(kind)


def _beats(value: Any, kind: str) -> int:
    top = MAX_BEATS[kind]
    try:
        n = int(value)
    except (TypeError, ValueError):
        return top
    return max(0 if kind == "insert" else 1, min(top, n))


def _states(value: Any, strict: bool = False) -> list[dict[str, str]]:
    """``[{subject, state}]`` from a list of pairs or a ``{subject: state}`` map; empty rows
    dropped."""
    if isinstance(value, Mapping):
        value = [{"subject": k, "state": v} for k, v in value.items()]
    if value is None:
        return []
    if not isinstance(value, list):
        if strict:
            raise ContractError("invalid_value", field="contract.states", value=str(value))
        return []
    out: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, Mapping):
            if strict:
                raise ContractError("invalid_value", field="contract.states", value=str(item))
            continue
        subject = str(item.get("subject") or "").strip()
        state = str(item.get("state") or "").strip()
        if subject and state:
            out.append({"subject": subject, "state": state})
        elif strict and (subject or state):
            raise ContractError("invalid_value", field="contract.states", value=subject or state)
    return out[:MAX_STATES]


def _props(
    value: Any,
    refs: Sequence[str],
    asset_kinds: Mapping[str, str],
    asset_names: Mapping[str, str],
    strict: bool = False,
) -> list[dict[str, str]]:
    """``[{asset_id, state}]`` for the shot's prop and on-screen-text references only; the model
    may name a prop instead of giving its id."""
    allowed = [a for a in refs if asset_kinds.get(a) in ("prop", "text")]
    by_name = {asset_names.get(a, ""): a for a in allowed if asset_names.get(a)}
    if isinstance(value, Mapping):
        value = [{"asset_id": k, "state": v} for k, v in value.items()]
    if not isinstance(value, list):
        return []
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, Mapping):
            continue
        key = str(item.get("asset_id") or item.get("id") or item.get("name") or "").strip()
        asset = key if key in allowed else by_name.get(key)
        state = str(item.get("state") or "").strip()
        if asset is None:
            if strict:
                raise ContractError("invalid_value", field="contract.props", value=key)
            continue
        if asset in seen or not state:
            continue
        seen.add(asset)
        out.append({"asset_id": asset, "state": state})
    return out[:MAX_STATES]


def _delivery_asked(value: Any, spoken: Sequence[SpokenLine]) -> dict[str, str]:
    """The model's ``delivery``: ``{"L3": "inner"}`` (line numbers, as in its prompt) or line
    ids; anything else ignored."""
    if not isinstance(value, Mapping):
        return {}
    by_key = {f"L{x.n}": x.line_id for x in spoken} | {x.line_id: x.line_id for x in spoken}
    out: dict[str, str] = {}
    for k, v in value.items():
        line_id = by_key.get(str(k).strip())
        if line_id is not None and v in DELIVERIES:
            out[line_id] = str(v)
    return out
