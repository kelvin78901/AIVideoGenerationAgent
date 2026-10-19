"""An episode's script as data (SPEC 4.1 ``scene`` / ``script_line``; M2 plan step 9): pure
functions.

A 剧本化 version holds one episode's script: its scenes in order, each with its lines. Ids are
fixed when a version is made (M2 plan 设计要点): a rerun gives scene n the id of the adopted
version's scene n, and a line keeps its id when the rerun writes the same text again anywhere
in the episode, else when it is similar to a line of the scene with the same number, so the
shots and voices later hung on a line stay with it. The user's edits (改一行、改场景标题) make a
new payload from the one on screen and mark what they changed ``edited`` (「已修改」).

Payload::

    {source_id, episode_id, scenes: [{id, heading, time_of_day, location_id, paras,
     source_spans, edited, lines: [{id, type, character_id, character_name, tone, text, mood,
     duration_s, overlay_shot, paras, source_spans, ai_added, cliffhanger, edited}]}]}

Nothing is numbered in the payload: scenes are numbered across the series when read (场号 is
the scenes of the episodes before plus the place in this one), so a change in one episode never
changes another episode's hash. ``heading`` is written without the number (「夜　内　林晚出租屋」).
``paras`` are paragraph numbers across the book (0-based); a line from an accepted addition
also has the span ``{source_id: "sug:<id>", start: 0, end: len}``.
"""

from __future__ import annotations

import copy
import re
import uuid
from collections.abc import Callable, Mapping, Sequence
from difflib import SequenceMatcher
from typing import Any

LINE_TYPES = ("action", "dialogue", "vo", "sfx")
# A rerun's line keeps the id of an adopted one in the same scene this similar.
SIMILAR = 0.6
ADDITION_SOURCE = "sug:"

_NUMBER = re.compile(r"^\s*场\s*\d+\s*[　\s·:：.、-]*")


class ScriptEditError(Exception):
    def __init__(self, code: str, **params: Any) -> None:
        super().__init__(code)
        self.code = code
        self.params = params


def new_scene_id() -> str:
    return f"sc-{uuid.uuid4().hex[:12]}"


def new_line_id() -> str:
    return f"ln-{uuid.uuid4().hex[:12]}"


def plain_heading(text: str) -> str:
    """A heading without the 场号 a model or the user may have written in front."""
    return _NUMBER.sub("", str(text)).strip()


def scenes_of(payload: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    return list((payload or {}).get("scenes") or [])


def find_scene(payload: Mapping[str, Any], scene_id: str) -> dict[str, Any] | None:
    return next((s for s in scenes_of(payload) if s["id"] == scene_id), None)


def find_line(
    payload: Mapping[str, Any], line_id: str
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """(scene, line) of a line id."""
    for s in scenes_of(payload):
        for line in s.get("lines") or []:
            if line["id"] == line_id:
                return s, line
    return None


def has_block(payload: Mapping[str, Any], block_id: str) -> bool:
    return find_scene(payload, block_id) is not None or find_line(payload, block_id) is not None


def scene_count(payload: Mapping[str, Any] | None) -> int:
    return len(scenes_of(payload))


# --------------------------------------------------------------------------- reading


def view(
    payload: Mapping[str, Any], first_scene: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(scenes, lines) as the page reads them: scenes numbered from ``first_scene`` (the
    series-wide 场号), lines numbered in reading order with the scene headings counted (the
    first heading is 0)."""
    scenes: list[dict[str, Any]] = []
    lines: list[dict[str, Any]] = []
    order = -1
    for n, s in enumerate(scenes_of(payload)):
        order += 1
        scenes.append(
            {
                **{k: v for k, v in s.items() if k != "lines"},
                "idx": first_scene + n,
                "edited": bool(s.get("edited")),
            }
        )
        for line in s.get("lines") or []:
            order += 1
            lines.append(
                {**line, "scene_id": s["id"], "idx": order, "edited": bool(line.get("edited"))}
            )
    return scenes, lines


# --------------------------------------------------------------------------- reruns


def _norm(text: str) -> str:
    return "".join(str(text).split())


def reconcile(
    found: Sequence[Mapping[str, Any]],
    base: Mapping[str, Any] | None,
    new_scene: Callable[[], str] = new_scene_id,
    new_line: Callable[[], str] = new_line_id,
) -> list[dict[str, Any]]:
    """A run's scenes (in order, without ids) against the adopted version's (``base``)."""
    old = scenes_of(base)
    exact: dict[str, list[str]] = {}
    for s in old:
        for line in s.get("lines") or []:
            exact.setdefault(_norm(line["text"]), []).append(line["id"])
    taken: set[str] = set()
    out: list[dict[str, Any]] = []
    for n, f in enumerate(found):
        before = old[n] if n < len(old) else None
        scene = {k: v for k, v in f.items() if k != "lines"}
        scene["id"] = before["id"] if before is not None else new_scene()
        lines = [dict(line) for line in f.get("lines") or []]
        # Same text anywhere first, then a similar line of the scene with this number.
        for line in lines:
            ids = [i for i in exact.get(_norm(line["text"]), []) if i not in taken]
            if ids:
                line["id"] = ids[0]
                taken.add(ids[0])
        if before is not None:
            for line in lines:
                if "id" in line:
                    continue
                best, score = None, SIMILAR
                for ol in before.get("lines") or []:
                    if ol["id"] in taken:
                        continue
                    ratio = SequenceMatcher(
                        None, _norm(line["text"]), _norm(ol["text"]), autojunk=False
                    ).ratio()
                    if ratio >= score:
                        best, score = ol["id"], ratio
                if best is not None:
                    line["id"] = best
                    taken.add(best)
        for line in lines:
            if "id" not in line:
                line["id"] = new_line()
        scene["lines"] = lines
        out.append(scene)
    return out


# --------------------------------------------------------------------------- edits


def patch_line(payload: Mapping[str, Any], line_id: str, *, text: str) -> dict[str, Any]:
    """改一行的文字 (「已修改」)."""
    out = copy.deepcopy(dict(payload))
    found = find_line(out, line_id)
    if found is None:
        raise ScriptEditError("line_not_found", id=line_id)
    text = str(text).strip()
    if not text:
        raise ScriptEditError("line_empty")
    _, line = found
    if line["text"] != text:
        line["text"] = text
        line["edited"] = True
    return out


def patch_scene(payload: Mapping[str, Any], scene_id: str, *, heading: str) -> dict[str, Any]:
    """改场景标题 (without the 场号, which is counted)."""
    out = copy.deepcopy(dict(payload))
    scene = find_scene(out, scene_id)
    if scene is None:
        raise ScriptEditError("scene_not_found", id=scene_id)
    heading = plain_heading(heading)
    if not heading:
        raise ScriptEditError("heading_empty")
    if scene["heading"] != heading:
        scene["heading"] = heading
        scene["edited"] = True
    return out
