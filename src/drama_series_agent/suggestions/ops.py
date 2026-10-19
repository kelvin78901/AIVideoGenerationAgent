"""Enrichment suggestions as data (SPEC 4.1 ``suggestion``; M2 plan step 7): pure functions.

A 小说补全 version holds what the model proposed; what the user decided (采纳 / 忽略 / 按要求重写)
is kept apart in ``suggestion_decision`` by suggestion id (plan 设计要点「建议的决定不进版本」),
so deciding never makes a version and a rerun carries decisions over through the ids it keeps:

- an accepted suggestion of the adopted version is kept exactly as it was (the user said yes
  to that text), and a new one of the same kind on the same paragraph is dropped as a repeat;
- any other suggestion keeps its id when the rerun proposes the same text for the same
  paragraph and kind (so 「忽略」 stays ignored); everything else gets a new id.

Only accepted suggestions reach downstream (``additions``): the ``adopted`` slice of the
product is their ids, paragraphs and final text, so pending or ignored ones never make the
bible or episodes stale.

Payload::

    {source_id, suggestions: [{id, kind, para_idx, anchor_span: {source_id, start, end},
     reason, text}]}

A decision (as read from ``suggestion_decision``)::

    {status: pending / accepted / rejected / rewritten, text: rewritten text or None,
     rewrite_instruction, rewritten_by}
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

KINDS = (
    "appearance", "lighting", "inner_to_action", "cliffhanger", "motive", "timeline",
    "consistency", "gap",
)  # fmt: skip
STATUSES = ("pending", "accepted", "rejected", "rewritten")

Decisions = Mapping[str, Mapping[str, Any]]
SpanOf = Callable[[int], dict[str, Any] | None]


def new_suggestion_id() -> str:
    return f"sug-{uuid.uuid4().hex[:12]}"


def find(payload: Mapping[str, Any], suggestion_id: str) -> dict[str, Any] | None:
    return next((s for s in payload.get("suggestions") or [] if s["id"] == suggestion_id), None)


def status_of(decision: Mapping[str, Any] | None) -> str:
    return str(decision["status"]) if decision else "pending"


def final_text(s: Mapping[str, Any], decision: Mapping[str, Any] | None) -> str:
    """The text that goes into the novel: the rewrite when there is one."""
    return str(decision["text"]) if decision and decision.get("text") else str(s["text"])


def additions(payload: Mapping[str, Any], decisions: Decisions) -> list[dict[str, Any]]:
    """The accepted suggestions as downstream reads them (the ``adopted`` slice)."""
    return [
        {
            "id": s["id"],
            "para_idx": s["para_idx"],
            "anchor_span": s["anchor_span"],
            "text": final_text(s, decisions.get(s["id"])),
        }
        for s in payload.get("suggestions") or []
        if status_of(decisions.get(s["id"])) == "accepted"
    ]


def by_paragraph(items: Iterable[Mapping[str, Any]]) -> dict[int, list[str]]:
    out: dict[int, list[str]] = {}
    for a in items:
        out.setdefault(int(a["para_idx"]), []).append(str(a["text"]))
    return out


def _norm(text: str) -> str:
    return "".join(text.split())


def reconcile(
    found: Sequence[Mapping[str, Any]],
    base: Sequence[Mapping[str, Any]],
    decisions: Decisions,
    new_id: Callable[[], str] = new_suggestion_id,
) -> list[dict[str, Any]]:
    """A rerun's suggestions (``found``: kind, para_idx, anchor_span, reason, text) against the
    adopted version's (``base``, already anchored in the current text)."""
    kept = [dict(s) for s in base if status_of(decisions.get(s["id"])) == "accepted"]
    taken = {(s["para_idx"], s["kind"]) for s in kept}
    known = {(s["para_idx"], s["kind"], _norm(str(s["text"]))): s["id"] for s in base}
    out = list(kept)
    used = {s["id"] for s in kept}
    seen: set[tuple[int, str, str]] = set()
    for f in found:
        key = (int(f["para_idx"]), str(f["kind"]), _norm(str(f["text"])))
        if (key[0], key[1]) in taken or key in seen:
            continue
        seen.add(key)
        sid = known.get(key)
        if sid is None or sid in used:
            sid = new_id()
        used.add(sid)
        fields = ("kind", "para_idx", "anchor_span", "reason", "text")
        out.append({"id": sid, **{k: f[k] for k in fields}})
    return sorted(out, key=lambda s: int(s["para_idx"]))  # stable: keeps the model's order


def reanchor(
    base: Sequence[Mapping[str, Any]],
    old_paragraph: Callable[[int], str] | None,
    new_paragraphs: Mapping[int, str],
    span_of: SpanOf,
) -> list[dict[str, Any]]:
    """The adopted version's suggestions moved onto a new text (the novel was edited or
    replaced): each follows its paragraph's text to the nearest paragraph that still says the
    same; one whose paragraph is gone is dropped."""
    if old_paragraph is None:
        return []
    where: dict[str, list[int]] = {}
    for idx, text in new_paragraphs.items():
        where.setdefault(text, []).append(idx)
    out = []
    for s in base:
        old = int(s["para_idx"])
        hits = where.get(old_paragraph(old), [])
        if not hits:
            continue
        idx = min(hits, key=lambda i: abs(i - old))
        span = span_of(idx)
        if span is not None:
            out.append({**s, "para_idx": idx, "anchor_span": span})
    return out
