"""The local QA workers (M6 steps 5a, 5b) without their models: ``workers/worker_qa.py`` with fake
engines, in process and through the real protocol (``LocalPythonAdapter``), and the video branch of
``workers/worker_rapidocr.py``. What they answer is what ``pipeline/qa.py:Measure`` reads.

Never the real engines here (no OpenCV, onnxruntime, faster-whisper, sherpa-onnx or torch in the
app's environment, no weights): those run in ``scripts/smoke/local_qa.py`` on the real machine.
"""

from __future__ import annotations

import sys
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from drama_series_agent.core.config import get_config
from drama_series_agent.core.paths import REPO_ROOT
from drama_series_agent.modelhub.adapters.base import (
    CallContext,
    ModelError,
    ModelRequest,
    ModelSpec,
)
from drama_series_agent.modelhub.adapters.local_python import (
    WORKERS_DIR,
    LocalPythonAdapter,
    RuntimePaths,
)
from drama_series_agent.modelhub.vram import VramLease

FAKE_WORKERS = REPO_ROOT / "tests" / "fixtures" / "workers"
PYTHON = Path(getattr(sys, "_base_executable", sys.executable))
for _dir in (WORKERS_DIR, FAKE_WORKERS):
    if str(_dir) not in sys.path:
        sys.path.insert(0, str(_dir))

import worker_qa  # noqa: E402
import worker_qa_fake  # noqa: E402
import worker_rapidocr  # noqa: E402
from worker_protocol import WorkerError  # noqa: E402

REFS = [
    {"asset_id": "a-lin", "name": "林晚", "path": "refs/lin.png"},
    {"asset_id": "a-chen", "name": "陈默", "path": "refs/chen.png"},
]


def _run(kind: str, state: dict[str, Any], **params: Any) -> dict[str, Any]:
    msg = {"id": "r1", "op": "run", "kind": kind, "text": "", "params": params, "out": "."}
    return worker_qa.HANDLERS[kind](state, msg)


def _code(kind: str, state: dict[str, Any], **params: Any) -> str:
    with pytest.raises(WorkerError) as err:
        _run(kind, state, **params)
    return err.value.code


# --------------------------------------------------------------------------- face


class Faces:
    """A take's faces are (who, how alike); a reference picture is its file name. A face whose
    who starts with "~" is turned away (not ``usable``)."""

    def __init__(self, frames: list[list[tuple[str, float]]], blank: tuple[str, ...] = ()) -> None:
        self.shown = frames
        self.blank = blank  # reference pictures with no face found

    def image(self, path: str) -> Any:
        if "missing" in path:
            raise OSError("no such file")
        return Path(path).stem

    def frames(self, path: str, every_s: float) -> Iterator[tuple[float, Any]]:
        if path.endswith(".txt"):
            raise OSError("not a video")
        for i, faces in enumerate(self.shown):
            yield i * every_s, faces

    def faces(self, picture: Any) -> list[Any]:
        if isinstance(picture, list):
            return picture
        return [] if picture in self.blank else [picture]

    def embed(self, picture: Any, face: Any) -> Any:
        return face

    def usable(self, face: Any, embedding: Any) -> bool:
        return not str(face[0]).startswith("~")

    def sim(self, a: Any, b: Any) -> float:
        who, alike = b
        return alike if who == a else 0.1


def test_each_face_is_scored_against_the_reference_it_is_closest_to() -> None:
    frames = [
        [("lin", 0.9)],
        [("lin", 0.5), ("chen", 0.8)],  # a two-hander: each against their own picture
        [],
        [("stranger", 0.0)],  # nobody's: it goes to the nearest and pulls it down
        [("lin", 0.6), ("~chen", 0.0)],  # a profile says nothing
        [("chen", 0.7)],
    ]
    state = {"tool": "face", "engine": Faces(frames, blank=("zhao",)), "min_frames": 3}
    refs = [*REFS, {"asset_id": "a-zhao", "name": "赵", "path": "refs/zhao.png"}]
    out = _run("qa_face", state, path="take.mp4", refs=refs, every_s=1.0)["json"]
    assert (out["frames"], out["with_face"], out["turned"]) == (6, 5, 1)
    assert out["faces"] == [
        {"asset_id": "a-lin", "name": "林晚", "sim": 0.6, "low": 0.5, "frames": 3},  # median
        {"asset_id": "a-chen", "name": "陈默", "sim": 0.7, "low": 0.1, "frames": 3},
        # no face in the picture → not scored (qa.py: 不适用)
        {"asset_id": "a-zhao", "name": "赵", "sim": None, "low": None, "frames": 0},
    ]


def test_too_few_usable_faces_are_not_scored() -> None:
    frames = [[("lin", 0.9)], [("~lin", 0.1)], [("~lin", 0.0)], [("lin", 0.8)]]
    state = {"tool": "face", "engine": Faces(frames)}  # min_frames: 3
    out = _run("qa_face", state, path="take.mp4", refs=REFS)["json"]
    assert out["faces"][0] == {
        "asset_id": "a-lin",
        "name": "林晚",
        "sim": None,
        "low": 0.8,
        "frames": 2,
    }
    assert out["turned"] == 2


def test_a_take_without_faces_scores_nobody() -> None:
    state = {"tool": "face", "engine": Faces([[], []])}
    out = _run("qa_face", state, path="take.mp4", refs=REFS)["json"]
    assert [f["sim"] for f in out["faces"]] == [None, None]
    assert (out["frames"], out["with_face"]) == (2, 0)


def test_face_errors() -> None:
    state = {"tool": "face", "engine": Faces([])}
    assert _code("qa_face", state, refs=REFS) == "qa_no_video"
    assert _code("qa_face", state, path="take.mp4", refs=[]) == "qa_no_refs"
    missing = [{"name": "林晚", "path": "refs/missing.png"}]
    assert _code("qa_face", state, path="take.mp4", refs=missing) == "qa_bad_ref"
    assert _code("qa_face", state, path="take.txt", refs=REFS) == "qa_bad_video"


# --------------------------------------------------------------------------- speaker


def test_windows_cover_the_clip_and_its_tail() -> None:
    assert worker_qa.windows(0, 4, 2) == []
    assert worker_qa.windows(3, 4, 2) == [(0, 3)]  # shorter than a window: all of it
    assert worker_qa.windows(10, 4, 2) == [(0, 4), (2, 6), (4, 8), (6, 10)]
    assert worker_qa.windows(11, 4, 3) == [(0, 4), (3, 7), (6, 10), (7, 11)]


def _speaker_state() -> dict[str, Any]:
    return {"tool": "speaker", "engine": worker_qa_fake.Speaker(), "window_s": 1.0, "hop_s": 0.5}


def test_each_voice_keeps_its_best_window_and_silence_is_skipped() -> None:
    voices = [
        {"who": "林晚", "path": "voices/lin.wav"},
        {"who": "陈默", "path": "voices/chen.wav"},
        {"who": "赵", "path": "voices/zhao.wav"},  # not in this take
    ]
    out = _run("qa_speaker", _speaker_state(), path="take.mp4", voices=voices)["json"]
    assert out["sims"] == [
        {"who": "林晚", "sim": 0.8},
        {"who": "陈默", "sim": 0.8},
        {"who": "赵", "sim": 0.2},
    ]
    assert (out["windows"], out["voiced"]) == (9, 8)  # (4, 6) is silence


def test_a_silent_take_scores_no_voice(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(worker_qa_fake, "SOUND", ["."] * 6)
    voices = [{"who": "林晚", "path": "voices/lin.wav"}]
    out = _run("qa_speaker", _speaker_state(), path="take.mp4", voices=voices)["json"]
    assert out["sims"] == [{"who": "林晚", "sim": None}]
    assert _code("qa_speaker", _speaker_state(), path="take.mp4", voices=[]) == "qa_no_voices"


# --------------------------------------------------------------------------- sync (SyncNet)


class Lips:
    """A take on the 25 fps grid: each frame is its list of face boxes. A crop is its rounded
    centre and half size; a track's confidence is its crop's x / 10."""

    sample_rate = 100  # 4 samples per frame

    def __init__(self, frames: list[list[worker_qa.Box]]) -> None:
        self.shown = frames
        self.scored: list[tuple[list[Any], list[int]]] = []

    def grid(self, path: str) -> Iterator[tuple[int, Any]]:
        if path.endswith(".txt"):
            raise OSError("not a video")
        yield from enumerate(self.shown)

    def boxes(self, frame: Any) -> list[worker_qa.Box]:
        return list(frame)

    def crop(self, frame: Any, x: float, y: float, half: float) -> Any:
        return (round(x), round(y), round(half))

    def audio(self, path: str) -> Any:
        return list(range(4 * len(self.shown)))

    def score(self, crops: list[Any], samples: Any) -> dict[str, Any] | None:
        self.scored.append((crops, samples))
        if len(crops) < 5:
            return None
        n = len(crops) - 4
        conf = crops[0][0] / 10
        return {
            "conf": conf,
            "in_sync": conf - 1,
            "offset": 1,
            "min_dist": 7.04,
            "voiced": n,
            "windows": n,
        }


SPEAKER = (300.0, 0.0, 380.0, 80.0)  # centre (340, 40), half size 40
LISTENER = (0.0, 0.0, 100.0, 100.0)
EXTRA = (500.0, 0.0, 520.0, 20.0)  # too small to read lips from
PASSING = (600.0, 600.0, 700.0, 700.0)  # in 5 frames only


def _lips_state(frames: list[list[worker_qa.Box]]) -> dict[str, Any]:
    return {"tool": "sync", "engine": Lips(frames), "min_track": 8, "min_face": 50}


def test_sync_scores_each_face_track_and_keeps_the_most_confident() -> None:
    frames: list[list[worker_qa.Box]] = []
    for k in range(40):
        shown = [LISTENER, EXTRA]
        if k >= 10 and k != 20:  # the speaker comes in at 0.4 s; YuNet misses them once
            shown.append(SPEAKER)
        if k < 5:
            shown.append(PASSING)
        frames.append(shown)
    state = _lips_state(frames)
    out = _run("qa_sync", state, path="take.mp4")["json"]
    assert (out["conf"], out["in_sync"], out["offset"]) == (34.0, 33.0, 1)
    assert (out["min_dist"], out["frames"]) == (7.04, 40)
    same = {"end": 1.6, "offset": 1, "min_dist": 7.04, "conf_all": None}
    assert out["tracks"] == [
        {"start": 0.0, "conf": 5.0, "in_sync": 4.0, "voiced": 36, "windows": 36, **same},
        {"start": 0.4, "conf": 34.0, "in_sync": 33.0, "voiced": 26, "windows": 26, **same},
    ]
    crops, samples = state["engine"].scored[1]
    assert len(crops) == 30 and set(crops) == {(340, 40, 40)}  # frame 20 filled in
    assert samples == list(range(40, 160))  # the same stretch of sound: 0.4 s to 1.6 s


def test_sync_without_a_face_track_is_not_scored() -> None:
    out = _run("qa_sync", _lips_state([[EXTRA]] * 30), path="take.mp4")["json"]
    assert (out["conf"], out["in_sync"], out["offset"], out["tracks"]) == (None, None, None, [])
    state = {**_lips_state([[LISTENER]] * 4), "min_track": 3}
    short = _run("qa_sync", state, path="take.mp4")["json"]
    assert short["conf"] is None and short["tracks"][0]["conf"] is None  # under one window
    assert _code("qa_sync", _lips_state([]), path="take.txt") == "qa_bad_video"
    assert _code("qa_sync", _lips_state([])) == "qa_no_video"


def test_tracks_follow_a_moving_face_and_end_after_a_long_gap() -> None:
    moving = [[(10.0 * k, 0.0, 10.0 * k + 100, 100.0)] for k in range(12)]
    (one,) = worker_qa.tracks(moving, min_len=8, min_face=50)
    assert one["frames"] == list(range(12)) and one["boxes"][11] == moving[11][0]
    gap = [[LISTENER]] * 10 + [[]] * (worker_qa.MAX_GAP + 1) + [[LISTENER]] * 10
    assert len(worker_qa.tracks(gap, min_len=8, min_face=50)) == 2


def test_medfilt_is_scipys_zero_padded_median() -> None:
    assert worker_qa.medfilt([1, 2, 3, 4, 5], 3) == [1, 2, 3, 4, 4]
    assert worker_qa.medfilt([50.0] * 20) == [50.0] * 20  # 13 wide: the ends keep their value


# --------------------------------------------------------------------------- asr, one tool each


def test_asr_answers_text_and_segments() -> None:
    state = {"tool": "asr", "engine": worker_qa_fake.Asr(), "lang": "zh"}
    out = _run("asr", state, path="take.mp4")
    assert out["text"] == "三年了。" and out["json"]["text"] == "三年了。"
    assert out["json"]["segments"][0]["lang"] == "zh"  # the worker's default
    assert _run("asr", state, path="take.mp4", lang="en")["json"]["segments"][0]["lang"] == "en"
    hinted = _run("asr", state, path="take.mp4", prompt="人物：周屿、林晚。")
    assert hinted["json"]["segments"][0]["prompt"] == "人物：周屿、林晚。"
    assert out["json"]["segments"][0]["prompt"] is None


def test_a_worker_only_does_the_tool_it_loaded() -> None:
    state = {"tool": "face", "engine": Faces([])}
    assert _code("asr", state, path="take.mp4") == "unsupported_kind"
    with pytest.raises(WorkerError) as err:
        worker_qa.init({"tool": "lipsync"})  # the tool is "sync"
    assert err.value.code == "qa_unknown_tool"


def test_the_configured_qa_models_name_a_tool_of_their_worker() -> None:
    models = {m.key: m for m in get_config().providers.local_models}
    for key in ("local/auraface", "local/campplus", "local/whisper-large-v3", "local/syncnet"):
        m = models[key]
        assert (m.worker, m.env, m.gpu, m.needs) == ("worker_qa", "qa", False, ["rt_qa", "w_qa"])
        assert worker_qa.TOOLS[m.kind][0] == m.args["tool"], key
        assert m.args["tool"] in worker_qa.ENGINES
    assert (WORKERS_DIR / "worker_qa.py").is_file()
    tools = get_config().components.component("qa").tools
    assert {tools["face"], tools["speaker"], tools["asr"], tools["lipsync"]} <= set(models)


# --------------------------------------------------------------------------- RapidOCR on a take


def _ocr_state(texts: list[list[str]]) -> dict[str, Any]:
    def frames(path: str, every_s: float) -> Iterator[tuple[float, Any]]:
        for i in range(len(texts)):
            yield i * every_s, SimpleNamespace(i=i, shape=(100, 200, 3))

    def engine(picture: Any) -> Any:
        if isinstance(picture, str):
            return SimpleNamespace(txts=("招牌",))
        lines = texts[picture.i]
        # A line at a time down a 200×100 frame, each 100 wide and 10 high.
        quads = [
            [[20, 10 + 20 * n], [120, 10 + 20 * n], [120, 20 + 20 * n], [20, 20 + 20 * n]]
            for n in range(len(lines))
        ]
        return SimpleNamespace(txts=tuple(lines) or None, boxes=quads or None)

    return {"engine": engine, "frames": frames}


def test_rapidocr_reads_a_take_frame_by_frame() -> None:
    state = _ocr_state([["回春", "堂"], [], ["回春堂"]])
    msg = {"id": "r", "kind": "ocr", "params": {"path": "take.mp4", "every_s": 1.0}}
    out = worker_rapidocr.read(state, msg)
    assert out["json"]["frames"] == [
        {"t": 0.0, "text": "回春堂", "boxes": [[0.1, 0.1, 0.6, 0.2], [0.1, 0.3, 0.6, 0.4]]},
        {"t": 1.0, "text": "", "boxes": []},
        {"t": 2.0, "text": "回春堂", "boxes": [[0.1, 0.1, 0.6, 0.2]]},
    ]
    assert out["text"] == "回春堂\n回春堂"
    # A picture as before.
    picture = worker_rapidocr.read(state, {"id": "r", "params": {"path": "kf.png"}})
    assert picture == {"text": "招牌", "json": {"text": "招牌"}}


# --------------------------------------------------------------------------- the real protocol


@pytest.fixture
async def made() -> AsyncIterator[list[LocalPythonAdapter]]:
    adapters: list[LocalPythonAdapter] = []
    yield adapters
    for adapter in adapters:
        await adapter.stop()


def _adapter(
    made: list[LocalPythonAdapter], tmp_path: Path, key: str, kind: str, **args: Any
) -> LocalPythonAdapter:
    async def paths() -> RuntimePaths:
        return RuntimePaths(envs=tmp_path / "envs", models=tmp_path / "models")

    spec = ModelSpec(
        key=key,
        kind=kind,
        where="local",
        display=key,
        runtime="python",
        worker="worker_qa_fake",
        env="qa",
        gpu=False,
        worker_args=args,
    )
    adapter = LocalPythonAdapter(
        spec, paths=paths, lease=VramLease(), python=lambda _env: PYTHON, workers_dir=FAKE_WORKERS
    )
    made.append(adapter)
    return adapter


async def test_the_workers_answer_what_measure_reads(
    made: list[LocalPythonAdapter], tmp_path: Path
) -> None:
    face = _adapter(made, tmp_path, "local/auraface", "qa_face", tool="face", min_frames=2)
    req = ModelRequest(kind="qa_face", params={"path": "take.mp4", "refs": REFS, "every_s": 1.0})
    got = (await face.run(req, CallContext())).json
    assert [(f["asset_id"], f["sim"], f["frames"]) for f in got["faces"]] == [
        ("a-lin", 0.9, 2),
        ("a-chen", 0.9, 2),
    ]
    with pytest.raises(ModelError) as err:  # the face process does not transcribe
        await face.run(ModelRequest(kind="asr", params={"path": "take.mp4"}), CallContext())
    assert err.value.code == "unsupported_kind"

    voice = _adapter(
        made, tmp_path, "local/campplus", "qa_speaker", tool="speaker", window_s=1.0, hop_s=0.5
    )
    voices = [{"who": "林晚", "path": "voices/lin.wav"}]
    req = ModelRequest(kind="qa_speaker", params={"path": "take.mp4", "voices": voices})
    assert (await voice.run(req, CallContext())).json["sims"] == [{"who": "林晚", "sim": 0.8}]

    asr = _adapter(made, tmp_path, "local/whisper-large-v3", "asr", tool="asr", lang="zh")
    req = ModelRequest(kind="asr", params={"path": "take.mp4", "lang": "zh"})
    assert (await asr.run(req, CallContext())).text == "三年了。"

    lips = _adapter(made, tmp_path, "local/syncnet", "qa_sync", tool="sync", min_track=8)
    got = await lips.run(ModelRequest(kind="qa_sync", params={"path": "take.mp4"}), CallContext())
    assert (got.json["conf"], got.json["in_sync"], got.json["offset"]) == (4.0, 3.5, 0)

    with pytest.raises(ModelError) as err:
        await _adapter(made, tmp_path, "x", "qa_face", tool="nope").run(req, CallContext())
    assert err.value.code == "qa_unknown_tool"
