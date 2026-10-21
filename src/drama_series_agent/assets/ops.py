"""Asset analysis without the database (M3 step 2): what an episode needs made, and where.

An episode's adopted script and the bible give most of the list by rule:
- every character on a line;
- a voice for every character who speaks (dialogue, voice-over);
- a scene for every (location, time of day);
- every bible prop named in a line.

These rules also give where each asset appears (the 出场矩阵), so the matrix never depends on a
model.

The model (``pipeline/components/assets.py``) adds what rules cannot:
- descriptions for the listed assets;
- props the bible does not have;
- on-screen text with its exact characters and lettering.

``merge`` folds its answer in. ``reconcile`` gives every asset an id: the same character, voice,
scene or prop keeps its id across reruns and across episodes (assets belong to the series),
matched by key (``character:<bible id>`` …) or else by kind and name.

The version payload::

    {"episode_id": …, "assets": [{"id", "key", "kind", "name", "bible_id", "description",
      "text": {"exact", "style", "method"} | None, "note", "uses": [{"scene_id", "line_ids"}]}]}
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

KINDS = ("character", "scene", "prop", "text", "voice")
SPEAKING = ("dialogue", "vo")
TIME_LABEL = {"day": "日", "night": "夜", "dawn": "清晨", "dusk": "黄昏"}
_BRACKETS = re.compile(r"[（(][^）)]*[）)]")


def component_of(kind: str) -> str:
    return "voice" if kind == "voice" else "text" if kind == "text" else "img"


def slot_of(kind: str) -> str:
    return "voice" if kind == "voice" else "text_image" if kind == "text" else "ref_image"


@dataclass
class Line:
    """A script line numbered across the episode (``L1`` … in the prompt)."""

    n: int
    scene_id: str
    line_id: str
    type: str
    character_id: str | None
    text: str


@dataclass
class Found:
    key: str
    kind: str
    name: str
    bible_id: str | None = None
    description: str = ""
    text: dict[str, Any] | None = None
    note: str | None = None
    # scene id → line ids ([] = the whole scene)
    uses: dict[str, list[str]] = field(default_factory=dict)

    def use(self, scene_id: str, line_id: str | None = None) -> None:
        ids = self.uses.setdefault(scene_id, [])
        if line_id is not None and line_id not in ids:
            ids.append(line_id)


def numbered_lines(script: Mapping[str, Any]) -> list[Line]:
    out: list[Line] = []
    for scene in script.get("scenes") or []:
        for line in scene.get("lines") or []:
            out.append(
                Line(
                    n=len(out) + 1,
                    scene_id=str(scene["id"]),
                    line_id=str(line["id"]),
                    type=str(line.get("type") or "action"),
                    character_id=line.get("character_id"),
                    text=str(line.get("text") or ""),
                )
            )
    return out


def entities_by_id(bible: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(e["id"]): dict(e) for e in bible.get("entities") or []}


def describe(entity: Mapping[str, Any] | None) -> str:
    """A default description from a bible entry (age, occupation, appearance …)."""
    if not entity:
        return ""
    data = entity.get("data") or {}
    parts = [str(v) for k, v in data.items() if k != "summary" and isinstance(v, str) and v]
    if isinstance(data.get("summary"), str) and data["summary"]:
        parts.append(str(data["summary"]))
    return "，".join(parts)


def scene_key(location_id: str | None, location_name: str, time: str | None) -> str:
    return f"scene:{location_id or location_name}:{time or ''}"


def scene_name(location_name: str, time: str | None) -> str:
    label = TIME_LABEL.get(time or "")
    return f"{location_name} · {label}" if label else location_name


def collect(script: Mapping[str, Any], bible: Mapping[str, Any]) -> list[Found]:
    """What the rules find in an episode's script, in order of first appearance."""
    entities = entities_by_id(bible)
    found: dict[str, Found] = {}

    def get(key: str, kind: str, name: str, bible_id: str | None) -> Found:
        if key not in found:
            found[key] = Found(
                key=key,
                kind=kind,
                name=name,
                bible_id=bible_id,
                description="" if kind == "voice" else describe(entities.get(bible_id or "")),
            )
        return found[key]

    props = [e for e in entities.values() if e.get("kind") == "prop"]
    for scene in script.get("scenes") or []:
        sid = str(scene["id"])
        location = entities.get(str(scene.get("location_id") or ""))
        if location is not None:
            time = scene.get("time_of_day")
            key = scene_key(location["id"], location["name"], time)
            get(key, "scene", scene_name(str(location["name"]), time), str(location["id"])).use(sid)
        for line in scene.get("lines") or []:
            lid, text = str(line["id"]), str(line.get("text") or "")
            who = entities.get(str(line.get("character_id") or ""))
            if who is not None:
                get(f"character:{who['id']}", "character", str(who["name"]), str(who["id"])).use(
                    sid, lid
                )
                if line.get("type") in SPEAKING:
                    get(f"voice:{who['id']}", "voice", str(who["name"]), str(who["id"])).use(
                        sid, lid
                    )
            # Props in the order the line mentions them.
            named: list[tuple[int, dict[str, Any]]] = []
            for prop in props:
                names = [str(prop["name"]), *(str(a) for a in prop.get("aliases") or [])]
                spots = [text.find(n) for n in names if n and n in text]
                if spots:
                    named.append((min(spots), prop))
            for _, prop in sorted(named, key=lambda x: x[0]):
                get(f"prop:{prop['id']}", "prop", str(prop["name"]), str(prop["id"])).use(sid, lid)
    return list(found.values())


def merge(
    found: Sequence[Found],
    answer: Mapping[str, Any],
    lines: Sequence[Line],
    bible: Mapping[str, Any],
) -> list[Found]:
    """Fold the model's answer into what the rules found.

    For a listed asset (by ``key``) the answer may give a description, a display name or a
    note. Anything else is an extra (a prop, on-screen text, or an asset coming up later);
    it joins a listed asset of the same kind and name, otherwise it is added with its lines.
    """
    out = [Found(**{**f.__dict__, "uses": {k: list(v) for k, v in f.uses.items()}}) for f in found]
    by_key = {f.key: f for f in out}
    by_line = {line.n: line for line in lines}
    bible_by_name = {
        (_kind_of_entity(str(e.get("kind"))), str(e["name"])): e
        for e in bible.get("entities") or []
    }
    for item in answer.get("assets") or []:
        kind = str(item.get("kind") or "")
        name = str(item.get("name") or "").strip()
        target = by_key.get(str(item.get("key") or ""))
        if target is None and kind in KINDS and name:
            target = next((f for f in out if f.kind == kind and _same_name(f.name, name)), None)
            if target is None:
                if kind == "text" and not (item.get("text") or {}).get("exact"):
                    continue
                base, _, label = name.partition(" · ")
                looked = "character" if kind == "voice" else kind  # a voice is its character's
                entity = bible_by_name.get((looked, name)) or bible_by_name.get((looked, base))
                bible_id = str(entity["id"]) if entity else None
                key = f"{kind}:{bible_id}" if bible_id else f"{kind}:name:{name}"
                if kind == "scene":
                    time = next((t for t, lab in TIME_LABEL.items() if lab == label), None)
                    key = scene_key(bible_id, base, time)
                if key in by_key:
                    target = by_key[key]
                else:
                    target = Found(key=key, kind=kind, name=name, bible_id=bible_id)
                    out.append(target)
                    by_key[key] = target
        if target is None:
            continue
        if item.get("description"):
            target.description = str(item["description"]).strip()
        if name and item.get("key"):
            target.name = name
        if item.get("note"):
            target.note = str(item["note"])
        text = item.get("text")
        if target.kind == "text" and isinstance(text, Mapping) and text.get("exact"):
            target.text = {
                "exact": str(text["exact"]),
                "style": text.get("style") if text.get("style") in _STYLES else "printed",
                "method": text.get("method") if text.get("method") in _METHODS else "composite",
            }
        for n in item.get("lines") or []:
            line = by_line.get(int(n)) if isinstance(n, int) else None
            if line is not None:
                target.use(line.scene_id, line.line_id)
    return out


_STYLES = ("handwritten", "printed", "screen")
_METHODS = ("model", "composite")


def _kind_of_entity(kind: str) -> str:
    return "scene" if kind == "location" else kind


def _same_name(a: str, b: str) -> bool:
    def norm(s: str) -> str:
        return _BRACKETS.sub("", s).replace(" ", "").replace("·", "")

    return norm(a) == norm(b)


def reconcile(found: Sequence[Found], known: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Give each asset an id: the id of a known asset (the series' other episodes and this
    episode's adopted list) with the same key, or the same kind and name; else a new one."""
    by_key: dict[str, str] = {}
    by_name: dict[tuple[str, str], str] = {}
    for k in known:
        by_key.setdefault(str(k["key"]), str(k["id"]))
        by_name.setdefault((str(k["kind"]), str(k["name"])), str(k["id"]))
    out: list[dict[str, Any]] = []
    taken: set[str] = set()
    for f in found:
        asset_id = by_key.get(f.key) or by_name.get((f.kind, f.name))
        if asset_id is None or asset_id in taken:
            asset_id = new_asset_id()
        taken.add(asset_id)
        out.append(
            {
                "id": asset_id,
                "key": f.key,
                "kind": f.kind,
                "name": f.name,
                "bible_id": f.bible_id,
                "description": f.description,
                "text": f.text,
                "note": f.note,
                "uses": [{"scene_id": s, "line_ids": ids} for s, ids in f.uses.items()],
            }
        )
    return out


def new_asset_id() -> str:
    return f"a-{uuid.uuid4().hex[:10]}"


def payload_of(episode_id: str, assets: list[dict[str, Any]]) -> dict[str, Any]:
    return {"episode_id": episode_id, "assets": assets}


def assets_of(payload: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    return list((payload or {}).get("assets") or [])


def lines_text(script: Mapping[str, Any], lines: Sequence[Line]) -> str:
    """The script as the prompt shows it: scene headings and numbered lines."""
    by_id = {line.line_id: line for line in lines}
    rows: list[str] = []
    for n, scene in enumerate(script.get("scenes") or [], 1):
        rows.append(f"[场 {n}] {scene.get('heading') or ''}")
        for line in scene.get("lines") or []:
            num = by_id[str(line["id"])].n
            who = line.get("character_name") or ""
            if line.get("type") in SPEAKING:
                tone = f"（{line['tone']}）" if line.get("tone") else ""
                rows.append(f"L{num} {who}{tone}：{line.get('text') or ''}")
            else:
                rows.append(f"L{num} △ {line.get('text') or ''}")
    return "\n".join(rows)


def known_text(found: Sequence[Found], lines: Sequence[Line]) -> str:
    """[已知素材]: key, kind, name and the lines it is in."""
    numbers = {line.line_id: line.n for line in lines}
    rows = []
    for f in found:
        where = sorted({numbers[i] for ids in f.uses.values() for i in ids if i in numbers})
        at = "、".join(f"L{n}" for n in where) if where else "整场"
        rows.append(f"{f.key}　{f.kind}　{f.name}　出现在：{at}")
    return "\n".join(rows)
