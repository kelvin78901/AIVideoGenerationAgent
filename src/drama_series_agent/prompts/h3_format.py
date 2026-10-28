"""MiniMax H3 prompts in the official layout (M5 step 14b, Kelvin 2026-10-27: 务必符合官方模板).

The rules are MiniMax's ``h3-prompt-writing`` skill (GitHub ``MiniMax-AI/MiniMax-H3``,
``.claude/skills/h3-prompt-writing``, commit b731d8846cf7, read 2026-10-27): ``base-en.txt`` for
image-to-video (I2VA) and ``ref-en.txt`` for reference-to-video (Ref2VA). The local check that
found them: ``docs/studio/reports/m5-local-smoke/run4-1-04-cut/``.

- ``Facts``: what the rewriter is told about a take (mode, length, pictures, voices, lines).
- ``check(prompt, facts)``: what in a prompt does not follow the guide, as English sentences the
  rewriter is shown when it is asked again; empty when it conforms.
- ``mock_prompt(facts)``: a conforming prompt built from the facts alone (Mock mode, tests).
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Mode = Literal["i2va", "ref2va"]

I2VA_INSTRUCTION = (
    "For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) "
    "is fully referenced."
)
BASE_SECTIONS = ("integrated_multimodal_description", "overall_soundscape", "non_diegetic_music")
REF_SECTIONS = (
    "subject_definitions",
    "summary",
    "retention_analysis",
    "detailed_description",
    "overall_soundscape",
    "non_diegetic_music",
)
TASK_TYPES = {
    "keyframe completion",
    "reference generation",
    "video editing",
    "video continuation",
    "audio reuse",
    "audio reference",
}
VISUAL_MARKERS = {"fully_preserved", "partially_preserved", "attribute_transfer", "weak_reference"}
AUDIO_MARKERS = {"fully_copy", "partially_copy", "reference", "weak_reference"}
# Word counts of the main description. The ref guide asks 350-500 English words for generation
# tasks; the base guide gives no number (its cases are short), so a floor that keeps a five-
# second take from running out of things to show.
WORDS = {"i2va": (120, 650), "ref2va": (300, 650)}

_CJK = re.compile(r"[　-〿㐀-䶿一-鿿＀-￯]")
_DIALOGUE = re.compile(r"<d>.*?</d>", re.S)
_QUOTED = re.compile(r"\"[^\"\n]*\"|“[^”\n]*”")
_LABEL = re.compile(r"<(Picture|Audio|Subject|Video) (\d+)>")


@dataclass
class Picture:
    role: Literal["first_frame", "reference"]
    name: str = ""
    kind: str = ""  # character / scene / prop / text
    description: str = ""


@dataclass
class Audio:
    role: Literal["voice", "dialogue_track"]
    speaker: str = ""  # S1 …
    who: str = ""


@dataclass
class Line:
    speaker: str  # S1 …
    who: str
    text: str
    language: str
    voiceover: bool = False
    audio: int | None = None  # the <Audio N> whose timbre it uses


@dataclass
class Facts:
    mode: Mode
    duration_s: float
    aspect: str
    draft: str  # the studio's layout (Chinese description in H3's fields)
    pictures: list[Picture] = field(default_factory=list)
    audios: list[Audio] = field(default_factory=list)
    dialogue: list[Line] = field(default_factory=list)
    sound: str = ""

    def as_json(self) -> dict[str, Any]:
        out = asdict(self)
        for i, p in enumerate(out["pictures"], 1):
            p["label"] = f"<Picture {i}>"
        for i, a in enumerate(out["audios"], 1):
            a["label"] = f"<Audio {i}>"
        for d in out["dialogue"]:
            d["audio"] = f"<Audio {d['audio']}>" if d["audio"] else None
        return out

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Facts:
        def num(label: str | None) -> int | None:
            m = re.search(r"\d+", label or "")
            return int(m.group()) if m else None

        return cls(
            mode=data["mode"],
            duration_s=float(data["duration_s"]),
            aspect=str(data["aspect"]),
            draft=str(data.get("draft") or ""),
            pictures=[
                Picture(p["role"], p.get("name", ""), p.get("kind", ""), p.get("description", ""))
                for p in data.get("pictures") or []
            ],
            audios=[
                Audio(a["role"], a.get("speaker", ""), a.get("who", ""))
                for a in data.get("audios") or []
            ],
            dialogue=[
                Line(
                    d["speaker"],
                    d.get("who", ""),
                    d["text"],
                    d["language"],
                    bool(d.get("voiceover")),
                    num(d.get("audio")),
                )
                for d in data.get("dialogue") or []
            ],
            sound=str(data.get("sound") or ""),
        )


# ---------------------------------------------------------------------------------- check


def sections(prompt: str) -> list[tuple[str, str]]:
    """``name: body`` sections in order (a section starts at the beginning of a line)."""
    names = "|".join(sorted({*BASE_SECTIONS, *REF_SECTIONS}, key=len, reverse=True))
    found = list(re.finditer(rf"(?m)^({names}):[ \t]*", prompt))
    out = []
    for i, m in enumerate(found):
        end = found[i + 1].start() if i + 1 < len(found) else len(prompt)
        out.append((m.group(1), prompt[m.end() : end].strip()))
    return out


def words(text: str) -> int:
    return len(re.findall(r"[A-Za-z][A-Za-z'’-]*", _DIALOGUE.sub(" ", text)))


def check(prompt: str, facts: Facts) -> list[str]:
    """What does not follow the official layout (empty when it conforms)."""
    problems: list[str] = []
    text = prompt.strip()
    parts = sections(text)
    names = [n for n, _ in parts]
    body = dict(parts)
    want = BASE_SECTIONS if facts.mode == "i2va" else REF_SECTIONS
    if tuple(names) != want:
        problems.append(
            "The prompt must have exactly these sections in this order, each starting a line "
            f"with its name and a colon: {', '.join(want)}. Found: {', '.join(names) or 'none'}."
        )
    if facts.mode == "i2va":
        first, _, rest = text.partition("\n")
        if first.strip() != I2VA_INSTRUCTION:
            problems.append(f"The first line must be exactly: {I2VA_INSTRUCTION}")
        elif not rest.startswith("\n"):
            problems.append("Leave one blank line after the first-line instruction.")
    elif text.split("\n", 1)[0].strip() != "subject_definitions:":
        problems.append("The prompt must begin with the line `subject_definitions:`.")

    main = body.get(
        "integrated_multimodal_description" if facts.mode == "i2va" else "detailed_description",
        "",
    )
    problems += _english(text)
    problems += _labels(text, facts)
    problems += _dialogue(text, facts)
    problems += _shots(main, facts)
    lo, hi = WORDS[facts.mode]
    n = words(main)
    if main and not lo <= n <= hi:
        field_ = next(n for n in want if n.endswith("description"))
        problems.append(
            f"`{field_}` has {n} English words; write {lo}-{hi}, beat by beat over the "
            f"{facts.duration_s:g} seconds: composition, subject appearance and position, "
            "environment and lighting, actions, camera movement and sound."
        )
    music = body.get("non_diegetic_music")
    if music is not None and music.strip().rstrip(".") != "N/A":
        problems.append("`non_diegetic_music` must be `N/A`: the score is added in post.")
    if "overall_soundscape" in body and not body["overall_soundscape"].strip():
        problems.append("`overall_soundscape` is empty.")
    if facts.mode == "ref2va" and not problems:
        problems += _ref_sections(body, facts)
    return problems


def _english(text: str) -> list[str]:
    outside = _QUOTED.sub(" ", _DIALOGUE.sub(" ", text))
    found = sorted(set(_CJK.findall(outside)))
    if not found:
        return []
    sample = "".join(found[:12])
    return [
        "Write every section in English; only the spoken words inside <d>…</d> and text visibly "
        "on screen (in double quotes) keep their original language. Romanize names (林晚 → Lin "
        f"Wan) and translate place names. Non-English characters found outside <d>: {sample}"
    ]


def _labels(text: str, facts: Facts) -> list[str]:
    problems = []
    used = {(k, int(n)) for k, n in _LABEL.findall(text)}
    for kind, n in sorted(used):
        if kind == "Picture" and n > len(facts.pictures):
            problems.append(f"<Picture {n}> is used but only {len(facts.pictures)} are sent.")
        if kind == "Audio" and n > len(facts.audios):
            problems.append(f"<Audio {n}> is used but only {len(facts.audios)} are sent.")
        if kind == "Video":
            problems.append("No video is sent: do not use <Video N>.")
    if facts.mode == "i2va":
        if any((k, n) != ("Picture", 1) for k, n in used):
            problems.append(
                "Image-to-video uses only <Picture 1> (the first frame), no other label."
            )
        if ("Picture", 1) not in used:
            problems.append("Name the first frame as <Picture 1>.")
    else:
        for i in range(1, len(facts.pictures) + 1):
            if ("Picture", i) not in used:
                problems.append(f"<Picture {i}> is sent but never cited.")
        for i in range(1, len(facts.audios) + 1):
            if ("Audio", i) not in used:
                problems.append(f"<Audio {i}> is sent but never cited.")
    return problems


def _dialogue(text: str, facts: Facts) -> list[str]:
    problems = []
    blocks = _DIALOGUE.findall(text)
    want = [f"<d>[{d.language}] {d.text}</d>" for d in facts.dialogue]
    if [b.strip() for b in blocks] != want:
        listed = " ".join(want) or "none"
        problems.append(
            "The spoken lines must appear exactly once each, in this order and verbatim "
            f"(language tag, words and punctuation unchanged): {listed}"
        )
    for d in facts.dialogue:
        if f"({d.speaker})" not in text:
            problems.append(f"Give the speaker of {d.text!r} the ID ({d.speaker}).")
        if d.voiceover:
            if "says in an off-screen voiceover" not in text:
                problems.append(
                    "A voiceover uses the exact phrase `says in an off-screen voiceover`."
                )
            if "lips remain completely closed" not in text:
                problems.append("After a voiceover, say that the lips remain completely closed.")
    return problems


def _shots(main: str, facts: Facts) -> list[str]:
    problems = []
    if not main.lstrip().startswith("[Shot 1]") and facts.mode == "i2va":
        problems.append("`integrated_multimodal_description` must begin with `[Shot 1]`.")
    if "[Shot 1]" not in main:
        problems.append("The description must contain `[Shot 1]`.")
    if re.search(r"\[Shot [2-9]\d*\]", main):
        problems.append(
            "This take is one continuous shot: only [Shot 1], no cut, no change of place; use "
            "camera movement for any change of framing."
        )
    return problems


def _ref_sections(body: dict[str, str], facts: Facts) -> list[str]:
    problems = []
    defs = [ln.strip() for ln in body["subject_definitions"].splitlines() if ln.strip()]
    first = [ln for ln in defs if ln.startswith("<Picture 1> is the first frame of [Shot 1]")]
    if not first:
        problems.append(
            "`subject_definitions` needs the line `<Picture 1> is the first frame of [Shot 1], …`."
        )
    for ln in defs:
        m = re.match(r"<Picture (\d+)>", ln)
        if m and m.group(1) != "1":
            problems.append(
                f"<Picture {m.group(1)}> only shows how a character or place looks: do not give "
                "it its own line; cite it inside a `<Subject N> is …` line instead (only first "
                "frames and keyframes get a standalone <Picture N> line)."
            )
    subject_lines = [ln for ln in defs if ln.startswith("<Subject ")]
    for i, p in enumerate(facts.pictures, 1):
        if p.role == "reference" and not any(f"<Picture {i}>" in ln for ln in subject_lines):
            problems.append(
                f"<Picture {i}> ({p.name}) must be cited inside a `<Subject N> is …` definition."
            )
    for i, a in enumerate(facts.audios, 1):
        line = next((ln for ln in defs if ln.startswith(f"<Audio {i}>")), "")
        if a.role == "voice" and "voice-timbre reference" not in line:
            problems.append(
                f"Define `<Audio {i}> is the voice-timbre reference for <Subject N> ({a.speaker}).`"
            )
        if a.role == "dialogue_track" and not line:
            problems.append(f"Define <Audio {i}> as the dialogue track of the target video.")

    m = re.match(r"\[([^\]]+)\]", body["summary"])
    types = {t.strip() for t in m.group(1).split("+")} if m else set()
    if not m or not types <= TASK_TYPES:
        problems.append(
            "`summary` must begin with a square-bracketed task type, e.g. "
            "[keyframe completion + reference generation + audio reference]."
        )
    need = {"keyframe completion"}
    if any(p.role == "reference" for p in facts.pictures):
        need.add("reference generation")
    if any(a.role == "voice" for a in facts.audios):
        need.add("audio reference")
    if any(a.role == "dialogue_track" for a in facts.audios):
        need.add("audio reuse")
    if m and not need <= types:
        problems.append(f"The task type must include: {' + '.join(sorted(need))}.")

    keep = [ln.strip() for ln in body["retention_analysis"].splitlines() if ln.strip()]
    if not any(ln.startswith("<Picture 1> ([Shot 1] first frame): fully_preserved") for ln in keep):
        problems.append(
            "`retention_analysis` needs `<Picture 1> ([Shot 1] first frame): fully_preserved - …`."
        )
    for ln in keep:
        label = re.match(r"<(Subject|Picture|Audio) \d+>", ln)
        marker = re.search(r":\s*([a-z_]+)\s*-", ln)
        if not label or not marker:
            problems.append(f"Each retention line is `<Label> …: marker - reason`; fix: {ln[:80]}")
            continue
        allowed = AUDIO_MARKERS if label.group(1) == "Audio" else VISUAL_MARKERS
        if marker.group(1) not in allowed:
            problems.append(f"Use one of {', '.join(sorted(allowed))} in: {ln[:80]}")
    defined = re.findall(r"<Subject (\d+)> is", body["subject_definitions"])
    for sub in sorted({int(n) for n in defined}):
        if not any(ln.startswith(f"<Subject {sub}>") for ln in keep):
            problems.append(f"`retention_analysis` needs a line for <Subject {sub}>.")
    if "<Picture 1>" not in body["detailed_description"]:
        problems.append("`detailed_description` must say the shot begins from <Picture 1>.")
    return problems


# ---------------------------------------------------------------------------------- mock


def mock_prompt(facts: Facts) -> str:
    """A prompt that passes ``check``, from the facts alone (Mock mode and tests)."""
    lines = []
    for d in facts.dialogue:
        voice = f", using the voice timbre referenced from <Audio {d.audio}>" if d.audio else ""
        if d.voiceover:
            lines.append(
                f"The speaker ({d.speaker}) says in an off-screen voiceover{voice}: "
                f"<d>[{d.language}] {d.text}</d> while the lips remain completely closed."
            )
        else:
            lines.append(f"The speaker ({d.speaker}) says{voice}: <d>[{d.language}] {d.text}</d>")
    beat = (
        "The camera pushes in with small amplitude at slow speed and the light stays as in the "
        "first frame, while the people, their clothes and the place stay exactly as they are."
    )
    lo = WORDS[facts.mode][0]
    filler: list[str] = []
    while words(" ".join(filler)) < lo:
        filler.append(beat)
    sound = "Natural ambient sound of the scene continues softly throughout the shot."
    if facts.mode == "i2va":
        main = " ".join(
            ["[Shot 1] Live-action, cinematic, the shot begins from <Picture 1>.", *filler, *lines]
        )
        return (
            f"{I2VA_INSTRUCTION}\n\nintegrated_multimodal_description: {main}\n\n"
            f"overall_soundscape: {sound}\n\nnon_diegetic_music: N/A"
        )
    defs = ["<Picture 1> is the first frame of [Shot 1], showing the opening composition."]
    keep = ["<Picture 1> ([Shot 1] first frame): fully_preserved - the opening composition."]
    subject = 0
    for i, p in enumerate(facts.pictures, 1):
        if p.role != "reference":
            continue
        subject += 1
        what = p.kind or "subject"
        defs.append(f"<Subject {subject}> is the {what} whose look comes from <Picture {i}>.")
        keep.append(f"<Subject {subject}> (appears in [Shot 1]): fully_preserved - its look.")
    types = ["keyframe completion"]
    if subject:
        types.append("reference generation")
    for i, a in enumerate(facts.audios, 1):
        if a.role == "voice":
            defs.append(f"<Audio {i}> is the voice-timbre reference for the speaker ({a.speaker}).")
            keep.append(f"<Audio {i}>: reference - the voice timbre, without copying the signal.")
            if "audio reference" not in types:
                types.append("audio reference")
        else:
            defs.append(f"<Audio {i}> is the dialogue track of the target video.")
            keep.append(f"<Audio {i}>: fully_copy - reused 1:1 as the complete final audio track.")
            if "audio reuse" not in types:
                types.append("audio reuse")
    cited = " ".join(f"<Audio {i}>" for i in range(1, len(facts.audios) + 1))
    main = " ".join(
        [
            "The target video is live-action and cinematic.",
            "[Shot 1] The shot begins from <Picture 1>.",
            *filler,
            *lines,
            f"The sound follows {cited}." if cited else "",
        ]
    ).strip()
    return "\n".join(
        [
            "subject_definitions:",
            *defs,
            "",
            f"summary: [{' + '.join(types)}] One continuous shot starting exactly on <Picture 1>.",
            "",
            "retention_analysis:",
            *keep,
            "",
            f"detailed_description: {main}",
            "",
            f"overall_soundscape: {sound}",
            "",
            "non_diegetic_music: N/A",
        ]
    )
