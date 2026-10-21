"""分集规划 as data (SPEC 4.1 ``episode`` / ``beat``; M2 plan step 8): pure functions.

A 分集规划 version holds the whole plan: the episodes in order, each with its beats. Ids are
fixed when a version is made (M2 plan 设计要点): a rerun gives episode n the id of the adopted
version's episode n, and a beat keeps its id when the rerun writes the same beat again (same
text anywhere in the plan, else a similar one in the episode with the same number), so the
episodes' products and spending stay with them. The user's edits (改集名、钩子、卡点; 改节拍,
拖到别的集) make a new payload from the one on screen.

Payload::

    {source_id, episodes: [{id, idx, title, hook, cliffhanger, target_seconds, scene_count,
     beats: [{id, idx, text, emotion, paras, source_spans}]}]}

``idx`` is 1-based (episodes across the series, beats within their episode); ``paras`` are
paragraph numbers across the book (0-based) and ``source_spans`` the same as spans
(SPEC 4.1). ``emotion`` runs from -1 (lowest) to 1 (highest) for the emotion curve.
"""

from __future__ import annotations

import copy
import uuid
from collections.abc import Callable, Mapping, Sequence
from difflib import SequenceMatcher
from typing import Any

# A rerun's beat keeps the id of an adopted one in the same episode this similar.
SIMILAR = 0.6
EPISODE_FIELDS = ("title", "hook", "cliffhanger", "target_seconds")


class EpisodeEditError(Exception):
    def __init__(self, code: str, **params: Any) -> None:
        super().__init__(code)
        self.code = code
        self.params = params


def new_episode_id() -> str:
    return f"ep-{uuid.uuid4().hex[:12]}"


def new_beat_id() -> str:
    return f"bt-{uuid.uuid4().hex[:12]}"


def episodes_of(payload: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    return list((payload or {}).get("episodes") or [])


def find_episode(payload: Mapping[str, Any], episode_id: str) -> dict[str, Any] | None:
    return next((e for e in episodes_of(payload) if e["id"] == episode_id), None)


def find_beat(
    payload: Mapping[str, Any], beat_id: str
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """(episode, beat) of a beat id."""
    for e in episodes_of(payload):
        for b in e.get("beats") or []:
            if b["id"] == beat_id:
                return e, b
    return None


def renumber(episodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for n, e in enumerate(episodes, 1):
        e["idx"] = n
        for m, b in enumerate(e.get("beats") or [], 1):
            b["idx"] = m
    return episodes


def episode_slice(payload: Mapping[str, Any], episode_id: str) -> dict[str, Any] | None:
    """``episode:<id>``: what one episode's script is written from. Spans are left out (they
    follow from ``paras`` and change with every new import of the same text)."""
    e = find_episode(payload, episode_id)
    if e is None:
        return None
    return {
        **{k: e.get(k) for k in (*EPISODE_FIELDS, "scene_count")},
        "beats": [
            {"id": b["id"], "text": b["text"], "emotion": b["emotion"], "paras": b["paras"]}
            for b in e.get("beats") or []
        ],
    }


def scene_ranges(episodes: Sequence[Mapping[str, Any]]) -> dict[str, tuple[int, int] | None]:
    """场 from–to of each episode, scenes numbered across the series from the planned counts."""
    out: dict[str, tuple[int, int] | None] = {}
    last = 0
    for e in sorted(episodes, key=lambda e: int(e["idx"])):
        count = e.get("scene_count")
        if not count:
            out[str(e["id"])] = None
            continue
        out[str(e["id"])] = (last + 1, last + int(count))
        last += int(count)
    return out


def first_scene(episodes: Sequence[Mapping[str, Any]], episode_id: str) -> int:
    """The 场号 an episode's first scene takes: one after the scenes of the episodes before."""
    n = 1
    for e in sorted(episodes, key=lambda e: int(e["idx"])):
        if e["id"] == episode_id:
            break
        n += int(e.get("scene_count") or 0)
    return n


# --------------------------------------------------------------------------- reruns


def _norm(text: str) -> str:
    return "".join(str(text).split())


def reconcile(
    found: Sequence[Mapping[str, Any]],
    base: Mapping[str, Any] | None,
    new_episode: Callable[[], str] = new_episode_id,
    new_beat: Callable[[], str] = new_beat_id,
) -> list[dict[str, Any]]:
    """A run's episodes (in order, without ids) against the adopted version's (``base``)."""
    old = episodes_of(base)
    by_number = {int(e["idx"]): e for e in old}
    old_beats = [(e, b) for e in old for b in e.get("beats") or []]
    exact: dict[str, list[str]] = {}
    for _, b in old_beats:
        exact.setdefault(_norm(b["text"]), []).append(b["id"])
    taken: set[str] = set()
    out: list[dict[str, Any]] = []
    for n, f in enumerate(found, 1):
        before = by_number.get(n)
        episode = {k: v for k, v in f.items() if k != "beats"}
        episode["id"] = before["id"] if before is not None else new_episode()
        beats = [dict(b) for b in f.get("beats") or []]
        # Same text anywhere first, then a similar beat of the episode with this number.
        for b in beats:
            ids = [i for i in exact.get(_norm(b["text"]), []) if i not in taken]
            if ids:
                b["id"] = ids[0]
                taken.add(ids[0])
        if before is not None:
            for b in beats:
                if "id" in b:
                    continue
                best, score = None, SIMILAR
                for ob in before.get("beats") or []:
                    if ob["id"] in taken:
                        continue
                    ratio = SequenceMatcher(
                        None, _norm(b["text"]), _norm(ob["text"]), autojunk=False
                    ).ratio()
                    if ratio >= score:
                        best, score = ob["id"], ratio
                if best is not None:
                    b["id"] = best
                    taken.add(best)
        for b in beats:
            if "id" not in b:
                b["id"] = new_beat()
        episode["beats"] = beats
        out.append(episode)
    return renumber(out)


# --------------------------------------------------------------------------- edits


def patch_episode(payload: Mapping[str, Any], episode_id: str, **changes: Any) -> dict[str, Any]:
    """改集名、钩子、卡点、预计时长; blank hook / cliffhanger = none."""
    out = copy.deepcopy(dict(payload))
    e = find_episode(out, episode_id)
    if e is None:
        raise EpisodeEditError("episode_not_found", id=episode_id)
    for key, value in changes.items():
        if key not in EPISODE_FIELDS:
            continue
        if key == "title":
            value = str(value or "").strip()
            if not value:
                raise EpisodeEditError("title_required")
        elif key in ("hook", "cliffhanger"):
            value = str(value or "").strip() or None
        e[key] = value
    return out


def patch_beat(
    payload: Mapping[str, Any],
    beat_id: str,
    *,
    text: str | None = None,
    emotion: float | None = None,
    episode_id: str | None = None,
    position: int | None = None,
) -> dict[str, Any]:
    """改一个节拍的文字或情绪, or drag it: into ``episode_id`` (its own when None) at
    ``position`` (0-based among that episode's other beats; the end when None)."""
    out = copy.deepcopy(dict(payload))
    found = find_beat(out, beat_id)
    if found is None:
        raise EpisodeEditError("beat_not_found", id=beat_id)
    source, beat = found
    if text is not None:
        text = text.strip()
        if not text:
            raise EpisodeEditError("beat_empty")
        beat["text"] = text
    if emotion is not None:
        beat["emotion"] = round(max(-1.0, min(1.0, float(emotion))), 2)
    if episode_id is not None or position is not None:
        target = source if episode_id is None else find_episode(out, episode_id)
        if target is None:
            raise EpisodeEditError("episode_not_found", id=episode_id)
        source["beats"] = [b for b in source.get("beats") or [] if b["id"] != beat_id]
        beats = list(target.get("beats") or [])
        at = len(beats) if position is None else max(0, min(int(position), len(beats)))
        beats.insert(at, beat)
        target["beats"] = beats
    renumber(episodes_of(out))
    return out
