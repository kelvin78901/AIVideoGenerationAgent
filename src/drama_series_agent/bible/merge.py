"""The story bible as data (SPEC 4.1 ``bible_entity``; M2 plan step 6): pure functions.

The extract component asks the model chunk by chunk; this module turns the answers into a
version payload:

1. ``group``: entries of the same kind that share a name or alias (normalized) are one entry;
2. ``reconcile`` with the adopted version: an entry that matches keeps its id (so downstream
   rows stay attached), a frozen one is kept exactly as it was, and pairs the user said are
   different stay apart;
3. ``candidates``: pairs that might still be the same (they share Han characters) go to the
   LLM; ``same`` verdicts become merge suggestions that the user confirms or rejects.

The user's edits (``patch``, ``merge``, ``distinct``, ``split``) also live here; each returns a
new payload, which the bible service appends as an ``edit`` version.

Payload::

    {source_id, entities: [{id, kind, name, aliases, data: {summary, …}, paras, source_spans,
     frozen}], chapters: [{idx, title, summary}], merge_suggestions: [{id, kind, ids, reason}],
     distinct: [[id, id], …]}
"""

from __future__ import annotations

import copy
import hashlib
import re
import unicodedata
import uuid
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

KINDS = ("character", "location", "prop", "event", "relation")
ID_PREFIX = {"character": "c", "location": "l", "prop": "p", "event": "e", "relation": "r"}
# Relations are named after the people in them, so they would always look alike.
JUDGED_KINDS = ("character", "location", "prop", "event")
MAX_PAIRS = 40

_PUNCT = re.compile(r"[\s·•\-—_()\[\]【】「」『』“”\"'、，,。.：:;；!！?？]+")
_HAN = re.compile(r"[㐀-鿿]")

SpanOf = Callable[[int], dict[str, Any] | None]
NewId = Callable[[str], str]


class BibleEditError(Exception):
    """An edit that does not apply; ``code`` + ``params`` reach the UI."""

    def __init__(self, code: str, **params: Any) -> None:
        super().__init__(code)
        self.code = code
        self.params = params


def new_entity_id(kind: str) -> str:
    return f"{ID_PREFIX.get(kind, 'x')}-{uuid.uuid4().hex[:12]}"


def normalize(name: str) -> str:
    """What two spellings of one name have in common: NFKC, no spaces or punctuation, lower."""
    return _PUNCT.sub("", unicodedata.normalize("NFKC", name)).lower()


def _keys(kind: str, names: Iterable[str]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for n in names:
        key = (kind, normalize(n))
        if key[1] and key not in out:
            out.append(key)
    return out


def _unique(names: Iterable[str], exclude: str = "") -> list[str]:
    seen = {normalize(exclude)} if exclude else set()
    out = []
    for n in names:
        n = n.strip()
        if n and normalize(n) not in seen:
            seen.add(normalize(n))
            out.append(n)
    return out


@dataclass
class Found:
    """One entry as the model gave it for one chunk; ``paras`` are 0-based and checked."""

    kind: str
    name: str
    aliases: list[str] = field(default_factory=list)
    summary: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    paras: list[int] = field(default_factory=list)

    def names(self) -> list[str]:
        return [self.name, *self.aliases]


def _combine(items: Sequence[Found]) -> Found:
    first = items[0]
    details: dict[str, Any] = {}
    for f in items:
        for k, v in f.details.items():
            if v not in (None, "", [], {}) and k not in details:
                details[k] = v
    return Found(
        kind=first.kind,
        name=first.name.strip(),
        aliases=_unique((n for f in items for n in f.names()), exclude=first.name),
        summary=next((f.summary.strip() for f in items if f.summary.strip()), ""),
        details=details,
        paras=sorted({p for f in items for p in f.paras}),
    )


def group(found: Sequence[Found]) -> list[Found]:
    """Entries of one kind that share a name or alias are merged (in order of appearance)."""
    parent = list(range(len(found)))

    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    seen: dict[tuple[str, str], int] = {}
    for i, f in enumerate(found):
        for key in _keys(f.kind, f.names()):
            if key in seen:
                a, b = root(seen[key]), root(i)
                if a != b:
                    parent[max(a, b)] = min(a, b)
            else:
                seen[key] = i
    buckets: dict[int, list[Found]] = {}
    for i, f in enumerate(found):
        buckets.setdefault(root(i), []).append(f)
    return [_combine(items) for _, items in sorted(buckets.items())]


def spans(paras: Iterable[int], span_of: SpanOf) -> list[dict[str, Any]]:
    return [s for p in paras if (s := span_of(p)) is not None]


def _entity(f: Found, entity_id: str, span_of: SpanOf) -> dict[str, Any]:
    return {
        "id": entity_id,
        "kind": f.kind,
        "name": f.name,
        "aliases": list(f.aliases),
        "data": {**f.details, "summary": f.summary},
        "paras": list(f.paras),
        "source_spans": spans(f.paras, span_of),
        "frozen": False,
    }


def _named(f: Found, name: str) -> Found:
    """The same entry under ``name`` if it is one of its names (the others stay aliases)."""
    if normalize(name) not in {normalize(n) for n in f.names()} or f.name == name:
        return f
    return Found(f.kind, name, _unique(f.names(), exclude=name), f.summary, f.details, f.paras)


def _order(e: Mapping[str, Any]) -> tuple[int, int, str]:
    kind = KINDS.index(e["kind"]) if e["kind"] in KINDS else len(KINDS)
    paras = e.get("paras") or []
    return kind, min(paras) if paras else 1 << 30, str(e["name"])


def reconcile(
    groups: Sequence[Found],
    base: Mapping[str, Any] | None,
    span_of: SpanOf,
    new_id: NewId = new_entity_id,
) -> tuple[list[dict[str, Any]], list[list[str]]]:
    """Entities with ids, and the ``distinct`` pairs still in force.

    A group takes the id of the adopted entry its name (else one of its aliases) matches, and
    keeps that entry's name when it is among the group's names; groups that land on the same
    id were merged by the user and are merged again. Frozen entries are copied as they are
    and whatever matched them is dropped.
    """
    base_entities: list[dict[str, Any]] = list((base or {}).get("entities") or [])
    names = {e["id"]: str(e["name"]) for e in base_entities}
    index: dict[tuple[str, str], str] = {}
    for e in base_entities:
        for key in _keys(e["kind"], [e["name"], *e.get("aliases", [])]):
            index.setdefault(key, e["id"])
    frozen = [copy.deepcopy(e) for e in base_entities if e.get("frozen")]
    frozen_ids = {e["id"] for e in frozen}

    matched: dict[str, list[Found]] = {}
    fresh: list[Found] = []
    for g in groups:
        target = next((index[k] for k in _keys(g.kind, g.names()) if k in index), None)
        if target is None:
            fresh.append(g)
        else:
            matched.setdefault(target, []).append(g)

    entities = list(frozen)
    for entity_id, items in matched.items():
        if entity_id not in frozen_ids:
            entities.append(_entity(_named(_combine(items), names[entity_id]), entity_id, span_of))
    entities += [_entity(g, new_id(g.kind), span_of) for g in fresh]
    entities.sort(key=_order)

    ids = {e["id"] for e in entities}
    distinct = [
        list(pair)
        for pair in (base or {}).get("distinct") or []
        if len(pair) == 2 and pair[0] in ids and pair[1] in ids
    ]
    return entities, distinct


# --------------------------------------------------------------------------- possibly the same


def han(e: Mapping[str, Any]) -> set[str]:
    return set(_HAN.findall("".join([e["name"], *e.get("aliases", [])])))


def _pair_key(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a <= b else (b, a)


def candidates(
    entities: Sequence[Mapping[str, Any]], distinct: Iterable[Sequence[str]]
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Pairs of one kind whose names share a Han character, most shared first."""
    apart = {_pair_key(a, b) for a, b in distinct}
    found: list[tuple[int, int, dict[str, Any], dict[str, Any]]] = []
    for kind in JUDGED_KINDS:
        items = [e for e in entities if e["kind"] == kind]
        for i, a in enumerate(items):
            for b in items[i + 1 :]:
                if _pair_key(a["id"], b["id"]) in apart:
                    continue
                shared = len(han(a) & han(b))
                if shared:
                    found.append((-shared, len(found), dict(a), dict(b)))
    found.sort(key=lambda t: (t[0], t[1]))
    return [(a, b) for _, _, a, b in found[:MAX_PAIRS]]


def suggestion_id(ids: Sequence[str]) -> str:
    return "m-" + hashlib.sha256("|".join(sorted(ids)).encode("utf-8")).hexdigest()[:12]


def suggestions(
    pairs: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]],
    verdicts: Iterable[tuple[int, bool, str]],
) -> list[dict[str, Any]]:
    """``same`` verdicts (pair numbers are 1-based, as in the prompt) → merge suggestions."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for n, same, reason in verdicts:
        if not same or not 1 <= n <= len(pairs):
            continue
        a, b = pairs[n - 1]
        sid = suggestion_id([a["id"], b["id"]])
        if sid not in seen:
            seen.add(sid)
            out.append({"id": sid, "kind": a["kind"], "ids": [a["id"], b["id"]], "reason": reason})
    return out


# --------------------------------------------------------------------------- edits


def find(payload: Mapping[str, Any], entity_id: str) -> dict[str, Any] | None:
    return next((e for e in payload.get("entities") or [] if e["id"] == entity_id), None)


def _require(payload: Mapping[str, Any], entity_id: str) -> dict[str, Any]:
    e = find(payload, entity_id)
    if e is None:
        raise BibleEditError("entity_not_found", id=entity_id)
    return e


def patch(
    payload: Mapping[str, Any],
    entity_id: str,
    *,
    name: str | None = None,
    aliases: Sequence[str] | None = None,
    data: Mapping[str, Any] | None = None,
    frozen: bool | None = None,
) -> dict[str, Any]:
    """Change what was sent. A new name keeps the old one as an alias (unless ``aliases`` is
    sent too), so the next extraction still recognizes the entry."""
    out = copy.deepcopy(dict(payload))
    e = _require(out, entity_id)
    old = str(e["name"])
    if name is not None:
        if not name.strip():
            raise BibleEditError("name_required")
        e["name"] = name.strip()
    if aliases is not None:
        e["aliases"] = _unique(aliases, exclude=e["name"])
    elif name is not None:
        e["aliases"] = _unique([*e.get("aliases", []), old], exclude=e["name"])
    if data is not None:
        e["data"] = {**dict(data), "summary": str(data.get("summary") or "")}
    if frozen is not None:
        e["frozen"] = frozen
    return out


def _remap(pairs: Iterable[Sequence[str]], gone: set[str], keep: str) -> list[list[str]]:
    out: list[list[str]] = []
    seen: set[tuple[str, str]] = set()
    for pair in pairs:
        a, b = (keep if x in gone else x for x in pair)
        if a != b and _pair_key(a, b) not in seen:
            seen.add(_pair_key(a, b))
            out.append([a, b])
    return out


def merge(payload: Mapping[str, Any], ids: Sequence[str]) -> dict[str, Any]:
    """「确认合并」: the first id stays; the others' names become its aliases."""
    if len(ids) < 2 or len(set(ids)) != len(ids):
        raise BibleEditError("merge_needs_two")
    out = copy.deepcopy(dict(payload))
    keep = _require(out, ids[0])
    others = [_require(out, i) for i in ids[1:]]
    if any(o["kind"] != keep["kind"] for o in others):
        raise BibleEditError("merge_kinds_differ")
    names = [*keep.get("aliases", []), *(n for o in others for n in [o["name"], *o["aliases"]])]
    keep["aliases"] = _unique(names, exclude=keep["name"])
    data = dict(keep.get("data") or {})
    for o in others:
        for k, v in (o.get("data") or {}).items():
            if data.get(k) in (None, "", [], {}):
                data[k] = v
    keep["data"] = data
    keep["paras"] = sorted({p for e in [keep, *others] for p in e.get("paras", [])})
    span_keys: dict[tuple[Any, ...], dict[str, Any]] = {}
    for e in [keep, *others]:
        for s in e.get("source_spans", []):
            span_keys.setdefault((s["source_id"], s["start"], s["end"]), s)
    keep["source_spans"] = sorted(span_keys.values(), key=lambda s: (s["source_id"], s["start"]))
    keep["frozen"] = any(e.get("frozen") for e in [keep, *others])
    gone = set(ids[1:])
    out["entities"] = [e for e in out["entities"] if e["id"] not in gone]
    remapped: dict[str, dict[str, Any]] = {}
    for s in out.get("merge_suggestions") or []:
        for pair in _remap([s["ids"]], gone, keep["id"]):
            remapped.setdefault(suggestion_id(pair), {**s, "ids": pair, "id": suggestion_id(pair)})
    out["merge_suggestions"] = list(remapped.values())
    out["distinct"] = _remap(out.get("distinct") or [], gone, keep["id"])
    return out


def distinct(payload: Mapping[str, Any], ids: Sequence[str]) -> dict[str, Any]:
    """「不是同一个」: drop the suggestion; reruns will not suggest the pair again."""
    if len(ids) != 2 or ids[0] == ids[1]:
        raise BibleEditError("distinct_needs_two")
    out = copy.deepcopy(dict(payload))
    a, b = (_require(out, i)["id"] for i in ids)
    key = _pair_key(a, b)
    out["merge_suggestions"] = [
        s for s in out.get("merge_suggestions") or [] if _pair_key(*s["ids"]) != key
    ]
    pairs = out.get("distinct") or []
    if all(_pair_key(*p) != key for p in pairs):
        pairs = [*pairs, [a, b]]
    out["distinct"] = pairs
    return out


def split(
    payload: Mapping[str, Any],
    entity_id: str,
    alias: str,
    paragraph: Callable[[int], str],
    span_of: SpanOf,
    new_id: NewId = new_entity_id,
) -> tuple[dict[str, Any], str]:
    """「拆分」: an alias becomes an entry of its own, taking the paragraphs that name it.

    Paragraphs that also name the original (or its other aliases) stay with both. The two are
    marked distinct so a rerun does not merge them back. Returns the payload and the new id.
    """
    out = copy.deepcopy(dict(payload))
    e = _require(out, entity_id)
    hit = next((a for a in e.get("aliases", []) if normalize(a) == normalize(alias)), None)
    if hit is None:
        raise BibleEditError("alias_not_found", id=entity_id, alias=alias)
    e["aliases"] = [a for a in e["aliases"] if a != hit]
    names = [e["name"], *e["aliases"]]
    moved = [p for p in e.get("paras", []) if hit in paragraph(p)]
    stays = [
        p for p in e.get("paras", []) if p not in moved or any(n in paragraph(p) for n in names)
    ]
    e["paras"] = stays
    e["source_spans"] = spans(stays, span_of)
    fresh = _entity(Found(kind=e["kind"], name=hit, paras=moved), new_id(e["kind"]), span_of)
    out["entities"].insert(out["entities"].index(e) + 1, fresh)
    out["distinct"] = [*(out.get("distinct") or []), [e["id"], fresh["id"]]]
    return out, fresh["id"]
