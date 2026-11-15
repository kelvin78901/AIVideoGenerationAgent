"""连续性账本 (M6 step 2): where each person is, what is in their hands, what they wear, what
state each prop is in and what time it is, when a shot begins.

Worked out on read like the contract (``contracts.effective``), not stored (Kelvin 2026-11-15:
an asset's description changes without a new plan version, so a stored ledger would go stale).
Plain functions over JSON; the callers gather the inputs (``ShotService.of_episode``, the
keyframe and video components, the QA's look at a take).

What comes from where:

- **position**: the scene's top view (``blocking``) as the camera sees it, the same rule the
  keyframe prompt uses (``screen_place``): left / center / right, near / far;
- **facing**, **holding**, **outfit**: the shot's ``start`` row for that person; a person the
  shot's start says nothing about keeps what their scene's last row said (an earlier shot's
  ``end``, else its ``start``), and ``*_from`` names that shot. Holding = the props named next to
  a hand verb (「右手握着伞柄」), or a prop whose state puts it in their hand (「在林晚手里」).
  Outfit = the clauses about clothes; without one, the clothes in the asset's description;
- **props**: the effective contract's props (their state, and the shot it came from);
- **time**: the scene's time of day; a clock read off the shot's on-screen text or a prop's
  state (1-07's 23:52), else the scene's last one.

Only people and props the shot films are listed (its references and the props its contract
links in).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from drama_series_agent.shots.contract import names_in

_HAND = re.compile(
    r"(?:左手|右手|双手|两手|手里|手中|手上)?(?:握|拿|拎|举|抱|攥|捏|撑|提|端|夹|捧|抓)着?"
)
_IN_HAND = re.compile(r"在([^，。；、,;：:]{1,8})(?:的)?(?:手里|手中|手上|怀里)")
_FACING = re.compile(r"((?:朝|面向|面朝|背对|看向|望向|盯着)[^，。；、,;：:]{1,10})")
_CLOTHES = (
    "穿",
    "外套",
    "衫",
    "裙",
    "裤",
    "衣",
    "西装",
    "校服",
    "制服",
    "毛衣",
    "T恤",
    "帽",
    "围巾",
    "鞋",
    "睡袍",
)
_CLAUSE = re.compile(r"[，。；,;]")
_CLOCK = re.compile(r"(?<!\d)([01]?\d|2[0-3])[:：]([0-5]\d)(?!\d)")


def screen_place(item: Mapping[str, Any], camera: Mapping[str, Any] | None) -> tuple[str, str]:
    """Where a top-view item is in the picture: (left / center / right, near / mid / far)."""
    cx, cy = (float(camera["x"]), float(camera["y"])) if camera else (0.5, 1.0)
    dx, depth = float(item["x"]) - cx, cy - float(item["y"])
    side = "left" if dx < -0.15 else "right" if dx > 0.15 else "center"
    far = "far" if depth > 0.55 else "near" if depth < 0.25 else "mid"
    return side, far


def clauses(text: str) -> list[str]:
    return [c.strip() for c in _CLAUSE.split(text) if c.strip()]


def holding_in(state: str, props: Mapping[str, Sequence[str]]) -> list[str]:
    """The props a person's state puts in their hands (by any of their names)."""
    out = []
    for clause in clauses(state):
        m = _HAND.search(clause)
        if m is None:
            continue
        rest = clause[m.start() :]
        for pid, names in props.items():
            if pid not in out and names_in(rest, names):
                out.append(pid)
    return out


def outfit_in(text: str) -> str | None:
    """The clauses of ``text`` about clothes, joined; None when it has none."""
    found = [c for c in clauses(text) if any(w in c for w in _CLOTHES)]
    return "，".join(found) or None


def facing_in(state: str) -> str | None:
    m = _FACING.search(state)
    return m.group(1) if m else None


def clock_in(text: str) -> str | None:
    m = _CLOCK.search(text)
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m else None


def _rows_of(contract: Mapping[str, Any] | None, key: str) -> list[Mapping[str, Any]]:
    rows = (contract or {}).get(key)
    return [r for r in rows if isinstance(r, Mapping)] if isinstance(rows, list) else []


def _about(rows: Iterable[Mapping[str, Any]], name: str) -> str | None:
    """What the rows say about a person (their own row, 「林晚」 or 「林晚的手」), joined."""
    said = []
    for r in rows:
        subject = str(r.get("subject") or "")
        if subject == name or subject.startswith(f"{name}的"):
            said.append(str(r.get("state") or ""))
    return "，".join(s for s in said if s) or None


def build(
    shot: Mapping[str, Any],
    contract: Mapping[str, Any],
    shots: Sequence[Mapping[str, Any]],
    *,
    kinds: Mapping[str, str],
    names: Mapping[str, str],
    prop_names: Mapping[str, Sequence[str]],
    descriptions: Mapping[str, str],
    texts: Mapping[str, str],
    time_of_day: str | None,
) -> dict[str, Any]:
    """The ledger of ``shot`` (a plan shot) at its start.

    ``contract``: its effective contract; ``shots``: the episode's plan shots in order (earlier
    shots of the scene give what this one does not say); ``kinds`` / ``names``: asset id → kind /
    name; ``prop_names``: prop id → name and aliases; ``descriptions``: character id → how they
    look; ``texts``: on-screen text and text-bearing prop id → the literal text."""
    refs = list(shot.get("asset_ids") or [])
    earlier = _earlier(shot, shots)
    linked = [a for a in contract.get("props_linked") or [] if a not in refs]
    people = [a for a in refs if kinds.get(a) == "character"]
    blocking = [b for b in shot.get("blocking") or [] if isinstance(b, Mapping)]
    camera = next((b for b in blocking if b.get("kind") == "camera"), None)
    start = _rows_of(contract, "start")

    characters = []
    for a in people:
        name = names.get(a, "")
        own = _about(start, name) if name else None
        item = next(
            (b for b in blocking if b.get("id") == a or (name and b.get("label") == name)), None
        )
        side, depth = screen_place(item, camera) if item else (None, None)
        last, last_from = _last_said(earlier, name) if name else (None, None)
        holding = _holding(own, a, name, contract, prop_names)
        holding_from = None
        if own is None and last is not None:
            holding = holding_in(last, prop_names)
            holding_from = last_from if holding else None
        outfit, outfit_from = (outfit_in(own) if own else None), None
        if outfit is None and last is not None and (said := outfit_in(last)) is not None:
            outfit, outfit_from = said, last_from
        if outfit is None:
            desc = descriptions.get(a) or ""
            outfit = outfit_in(desc)
        characters.append(
            {
                "asset_id": a,
                "name": name,
                "position": side,
                "depth": depth,
                "facing": facing_in(own) if own else None,
                "holding": holding,
                "holding_names": [names.get(x, x) for x in holding],
                "holding_from": holding_from,
                "outfit": outfit,
                "outfit_from": outfit_from,
            }
        )

    origin = dict(contract.get("props_from") or {})
    props = [
        {
            "asset_id": str(p["asset_id"]),
            "name": names.get(str(p["asset_id"]), ""),
            "state": str(p.get("state") or ""),
            "from_shot": origin.get(str(p["asset_id"])),
        }
        for p in contract.get("props") or []
        if isinstance(p, Mapping) and p.get("asset_id")
    ]

    clock, clock_from = None, None
    for a in [*refs, *linked]:
        if (c := clock_in(texts.get(a, ""))) is not None:
            clock = c
            break
    if clock is None:
        clock = next((c for p in props if (c := clock_in(str(p["state"]))) is not None), None)
    if clock is None:
        clock, clock_from = _last_clock(earlier, texts, kinds)
    return {
        "characters": characters,
        "props": props,
        "time": {"time_of_day": time_of_day, "clock": clock, "clock_from": clock_from},
    }


def carried(ledger: Mapping[str, Any]) -> list[str]:
    """What the shot carries over from an earlier one and its own contract does not say (who
    still holds what, who still wears what), one line each for a prompt (``sources`` gives the
    shots it came from, for the dependencies)."""
    rows = []
    for c in ledger.get("characters") or []:
        if c.get("holding_from") and c.get("holding"):
            rows.append(f"{c['name']}手里还拿着：{'、'.join(c['holding_names'])}")
        if c.get("outfit_from") and c.get("outfit"):
            rows.append(f"{c['name']}的穿着：{c['outfit']}")
    return rows


def sources(ledger: Mapping[str, Any]) -> list[str]:
    """The earlier shots this ledger reads (for the keyframe's and video's dependencies)."""
    out = {
        str(c[k])
        for c in ledger.get("characters") or []
        for k in ("holding_from", "outfit_from")
        if c.get(k)
    }
    clock_from = (ledger.get("time") or {}).get("clock_from")
    if clock_from:
        out.add(str(clock_from))
    return sorted(out)


# --------------------------------------------------------------------------- the rules


def _earlier(
    shot: Mapping[str, Any], shots: Sequence[Mapping[str, Any]]
) -> list[Mapping[str, Any]]:
    """The shots of ``shot``'s scene before it, nearest first."""
    out = []
    for s in shots:
        if s.get("id") == shot.get("id"):
            break
        if s.get("scene_id") == shot.get("scene_id"):
            out.append(s)
    return out[::-1]


def _last_said(earlier: Sequence[Mapping[str, Any]], name: str) -> tuple[str | None, str | None]:
    """What the scene last said about a person: the nearest earlier shot's end, else its start."""
    for s in earlier:
        c = s.get("contract") if isinstance(s.get("contract"), Mapping) else None
        for key in ("end", "start"):
            said = _about(_rows_of(c, key), name)
            if said:
                return said, str(s["id"])
    return None, None


def _holding(
    own: str | None,
    person: str,
    name: str,
    contract: Mapping[str, Any],
    prop_names: Mapping[str, Sequence[str]],
) -> list[str]:
    out = holding_in(own, prop_names) if own else []
    for p in contract.get("props") or []:
        pid = str(p.get("asset_id") or "")
        for who in _IN_HAND.findall(str(p.get("state") or "")):
            if pid and pid not in out and who in (name, person):
                out.append(pid)
    return out


def _last_clock(
    earlier: Sequence[Mapping[str, Any]], texts: Mapping[str, str], kinds: Mapping[str, str]
) -> tuple[str | None, str | None]:
    for s in earlier:
        for a in s.get("asset_ids") or []:
            if kinds.get(a) in ("text", "prop") and (c := clock_in(texts.get(a, ""))) is not None:
                return c, str(s["id"])
    return None, None
