"""The local QA tools on the CPU (M6 自动质检, ``pipeline/qa.py``): one model per worker process.

``args.tool`` picks what the process loads (``providers.yaml`` gives each model key its own
worker), so the onnxruntime that AuraFace uses and the one inside sherpa-onnx never share a process:

- ``face`` (``qa_face``): YuNet finds faces and their 5 points (OpenCV 4.x, ``2023mar``); the
  face is aligned to the ArcFace template and AuraFace's ``glintr100.onnx`` embeds it. In each
  sampled frame every face goes to the character reference it is closest to (cosine), so in a
  two-hander each person is scored against their own picture; a reference's ``sim`` is the mean
  over the frames where it got a face, so a face that drifts mid-shot pulls it down. Faces
  smaller than ``min_face`` px (extras far back) are not looked at. A reference with no face in
  its picture, or that got no face in the take, → None (``qa.py`` counts that as 不适用).
- ``speaker`` (``qa_speaker``): CAM++ (sherpa-onnx) embeds each voice's reference and windows of
  the take's sound (``window_s`` / ``hop_s``; several people may speak in one shot), each voice
  keeps its best window. Silent windows are skipped; no voiced window → None.
- ``asr``: faster-whisper large-v3, int8 on the CPU, straight from the mp4 (PyAV).

Requests and answers are the ones ``pipeline/qa.py:Measure`` sends and reads. Everything in this
file above "engines" is the standard library, so the unit tests drive it with fake engines; the
engines import their libraries when the worker starts. Sources, licences and what is unverified:
``docs/studio/reports/m6-qa-tools-research.md``.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterator
from typing import Any, Protocol

from worker_protocol import WorkerError, serve

FACE_EVERY_S = 1.0
MAX_FACES = 6  # per frame / reference picture, the largest first


class FaceEngine(Protocol):
    def image(self, path: str) -> Any: ...
    def frames(self, path: str, every_s: float) -> Iterator[tuple[float, Any]]: ...
    def faces(self, picture: Any) -> list[Any]: ...  # the largest first
    def embed(self, picture: Any, face: Any) -> Any: ...
    def sim(self, a: Any, b: Any) -> float: ...


class SpeakerEngine(Protocol):
    sample_rate: int

    def audio(self, path: str) -> Any: ...
    def voiced(self, samples: Any) -> bool: ...
    def embed(self, samples: Any) -> Any: ...
    def sim(self, a: Any, b: Any) -> float: ...


class AsrEngine(Protocol):
    def transcribe(self, path: str, lang: str | None) -> tuple[str, list[dict[str, Any]]]: ...


def _path(msg: dict[str, Any]) -> str:
    path = (msg.get("params") or {}).get("path")
    if not path:
        raise WorkerError("qa_no_video", "no take path")
    return str(path)


# --------------------------------------------------------------------------- face


def face(state: dict[str, Any], msg: dict[str, Any]) -> dict[str, Any]:
    eng: FaceEngine = state["engine"]
    params = msg.get("params") or {}
    video = _path(msg)
    every = float(params.get("every_s") or FACE_EVERY_S)
    refs = [r for r in params.get("refs") or [] if r.get("path")]
    if not refs:
        raise WorkerError("qa_no_refs", "no reference pictures")
    looks: list[list[Any]] = []
    for r in refs:
        try:
            picture = eng.image(str(r["path"]))
        except OSError as exc:
            raise WorkerError("qa_bad_ref", f"{r.get('name')}: {exc}") from exc
        looks.append([eng.embed(picture, f) for f in eng.faces(picture)[:MAX_FACES]])
    seen: list[list[Any]] = []
    try:
        for _t, frame in eng.frames(video, every):
            seen.append([eng.embed(frame, f) for f in eng.faces(frame)[:MAX_FACES]])
    except OSError as exc:
        raise WorkerError("qa_bad_video", str(exc)) from exc
    got: list[list[float]] = [[] for _ in refs]  # per reference, its best face in each frame
    for shown in seen:
        best: dict[int, float] = {}
        for b in shown:
            scores = [(max(eng.sim(a, b) for a in mine), i) for i, mine in enumerate(looks) if mine]
            if scores:
                sim, i = max(scores)
                best[i] = max(best.get(i, sim), sim)
        for i, sim in best.items():
            got[i].append(sim)
    faces = [
        {
            "asset_id": r.get("asset_id"),
            "name": r.get("name"),
            "sim": round(sum(sims) / len(sims), 4) if sims else None,
            "low": round(min(sims), 4) if sims else None,
            "frames": len(sims),
        }
        for r, sims in zip(refs, got, strict=True)
    ]
    with_face = sum(1 for shown in seen if shown)
    return {"json": {"faces": faces, "frames": len(seen), "with_face": with_face}}


# --------------------------------------------------------------------------- speaker


def windows(n: int, size: int, hop: int) -> list[tuple[int, int]]:
    """[start, end) sample ranges covering ``n`` samples; one window when the clip is shorter."""
    if n <= 0:
        return []
    if n <= size:
        return [(0, n)]
    starts = list(range(0, n - size + 1, hop))
    if starts[-1] + size < n:
        starts.append(n - size)  # the tail too
    return [(s, s + size) for s in starts]


def speaker(state: dict[str, Any], msg: dict[str, Any]) -> dict[str, Any]:
    eng: SpeakerEngine = state["engine"]
    params = msg.get("params") or {}
    video = _path(msg)
    voices = [v for v in params.get("voices") or [] if v.get("path")]
    if not voices:
        raise WorkerError("qa_no_voices", "no reference voices")
    rate = eng.sample_rate
    try:
        sound = eng.audio(video)
    except OSError as exc:
        raise WorkerError("qa_bad_video", str(exc)) from exc
    size = max(1, int(float(state["window_s"]) * rate))
    hop = max(1, int(float(state["hop_s"]) * rate))
    clips = [sound[s:e] for s, e in windows(len(sound), size, hop)]
    heard = [eng.embed(c) for c in clips if eng.voiced(c)]
    sims = []
    for v in voices:
        try:
            ref = eng.audio(str(v["path"]))
        except OSError as exc:
            raise WorkerError("qa_bad_ref", f"{v.get('who')}: {exc}") from exc
        sim = None
        if heard and len(ref) and eng.voiced(ref):
            mine = eng.embed(ref)
            sim = round(max(eng.sim(mine, h) for h in heard), 4)
        sims.append({"who": v.get("who"), "sim": sim})
    return {"json": {"sims": sims, "windows": len(clips), "voiced": len(heard)}}


# --------------------------------------------------------------------------- asr


def asr(state: dict[str, Any], msg: dict[str, Any]) -> dict[str, Any]:
    eng: AsrEngine = state["engine"]
    lang = (msg.get("params") or {}).get("lang") or state.get("lang")
    try:
        text, segments = eng.transcribe(_path(msg), lang)
    except OSError as exc:
        raise WorkerError("qa_bad_video", str(exc)) from exc
    return {"text": text, "json": {"text": text, "segments": segments}}


# --------------------------------------------------------------------------- engines

# ArcFace's 5-point template for a 112×112 crop (InsightFace face_align.py; OpenCV's
# FaceRecognizerSF uses the same). YuNet's points come in this order: the person's right eye
# (left in the picture), left eye, nose tip, right and left mouth corners.
ARCFACE = [
    [38.2946, 51.6963],
    [73.5318, 51.5014],
    [56.0252, 71.7366],
    [41.5493, 92.3655],
    [70.7299, 92.2041],
]


class _Face:
    """YuNet + AuraFace. ``args``: detector, recognizer, threads, score, min_face, input_mean,
    input_std."""

    def __init__(self, args: dict[str, Any]) -> None:
        import cv2
        import numpy as np
        import onnxruntime as ort

        self.cv2, self.np = cv2, np
        self.detector = cv2.FaceDetectorYN.create(
            str(args["detector"]), "", (320, 320), float(args.get("score", 0.8)), 0.3, 5000
        )
        so = ort.SessionOptions()
        so.intra_op_num_threads = int(args.get("threads", 4))
        self.rec = ort.InferenceSession(
            str(args["recognizer"]), so, providers=["CPUExecutionProvider"]
        )
        self.input = self.rec.get_inputs()[0].name
        self.mean = float(args.get("input_mean", 127.5))
        self.std = float(args.get("input_std", 127.5))
        self.template = np.array(ARCFACE, np.float64)
        self.min_face = float(args.get("min_face", 40))

    def image(self, path: str) -> Any:
        data = self.np.fromfile(path, self.np.uint8)  # imread cannot open non-ASCII paths
        picture = self.cv2.imdecode(data, self.cv2.IMREAD_COLOR)
        if picture is None:
            raise OSError(f"cannot read {path}")
        return picture

    def frames(self, path: str, every_s: float) -> Iterator[tuple[float, Any]]:
        from worker_video import frames

        return frames(path, every_s)

    def faces(self, picture: Any) -> list[Any]:
        # YuNet is trained on faces of about 10–300 px: a close-up at 768p is shrunk first.
        h, w = picture.shape[:2]
        scale = min(1.0, 640 / max(h, w))
        small = self.cv2.resize(picture, None, fx=scale, fy=scale) if scale < 1 else picture
        self.detector.setInputSize((small.shape[1], small.shape[0]))
        _, found = self.detector.detect(small)
        if found is None:
            return []
        rows = sorted(found, key=lambda r: float(r[2] * r[3]), reverse=True)
        return [
            r[4:14].reshape(5, 2).astype(self.np.float64) / scale
            for r in rows
            if min(float(r[2]), float(r[3])) / scale >= self.min_face
        ]

    def embed(self, picture: Any, face: Any) -> Any:
        np = self.np
        crop = self.cv2.warpAffine(picture, umeyama(np, face, self.template), (112, 112))
        blob = self.cv2.dnn.blobFromImage(
            crop, 1.0 / self.std, (112, 112), (self.mean,) * 3, swapRB=True
        )
        e = np.asarray(self.rec.run(None, {self.input: blob})[0][0], np.float32)
        return e / (np.linalg.norm(e) or 1.0)

    def sim(self, a: Any, b: Any) -> float:
        return float(self.np.dot(a, b))


def umeyama(np: Any, src: Any, dst: Any) -> Any:
    """The 2×3 similarity transform (rotation, one scale, shift) taking ``src`` points onto
    ``dst`` in the least-squares sense (Umeyama 1991; what InsightFace's norm_crop estimates)."""
    n = src.shape[0]
    ms, md = src.mean(axis=0), dst.mean(axis=0)
    sc, dc = src - ms, dst - md
    cov = dc.T @ sc / n
    d = np.ones(2)
    if np.linalg.det(cov) < 0:
        d[1] = -1.0
    u, s, vt = np.linalg.svd(cov)
    rot = u @ np.diag(d) @ vt
    var = (sc**2).sum() / n
    scale = float((s * d).sum() / var) if var > 0 else 1.0
    shift = md - scale * rot @ ms
    return np.hstack([scale * rot, shift[:, None]])


class _Speaker:
    """CAM++ through sherpa-onnx. ``args``: model, threads, min_rms."""

    def __init__(self, args: dict[str, Any]) -> None:
        import numpy as np
        import sherpa_onnx

        self.np = np
        cfg = sherpa_onnx.SpeakerEmbeddingExtractorConfig(
            model=str(args["model"]), num_threads=int(args.get("threads", 2)), provider="cpu"
        )
        if not cfg.validate():
            raise WorkerError("qa_model_missing", str(args["model"]))
        self.ext = sherpa_onnx.SpeakerEmbeddingExtractor(cfg)
        self.sample_rate = 16000
        self.min_rms = float(args.get("min_rms", 0.01))

    def audio(self, path: str) -> Any:
        from worker_video import audio

        return audio(path)

    def voiced(self, samples: Any) -> bool:
        if len(samples) < self.sample_rate // 4:
            return False
        return math.sqrt(float(self.np.mean(self.np.square(samples)))) >= self.min_rms

    def embed(self, samples: Any) -> Any:
        stream = self.ext.create_stream()
        stream.accept_waveform(sample_rate=self.sample_rate, waveform=samples)
        stream.input_finished()
        v = self.np.asarray(self.ext.compute(stream), self.np.float32)
        return v / (self.np.linalg.norm(v) or 1.0)

    def sim(self, a: Any, b: Any) -> float:
        return float(self.np.dot(a, b))


class _Asr:
    """faster-whisper. ``args``: model_dir, compute_type, beam_size, vad, threads, lang."""

    def __init__(self, args: dict[str, Any]) -> None:
        from faster_whisper import WhisperModel

        self.model = WhisperModel(
            str(args["model_dir"]),
            device="cpu",
            compute_type=str(args.get("compute_type", "int8")),
            cpu_threads=int(args.get("threads", 8)),
            local_files_only=True,
        )
        self.beam = int(args.get("beam_size", 5))
        self.vad = bool(args.get("vad", True))

    def transcribe(self, path: str, lang: str | None) -> tuple[str, list[dict[str, Any]]]:
        segments, _info = self.model.transcribe(
            path,
            language=lang or None,
            beam_size=self.beam,
            vad_filter=self.vad,
            condition_on_previous_text=False,
        )
        out = [
            {"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()}
            for s in segments  # a generator: decoding happens here
        ]
        return "".join(s["text"] for s in out), out


ENGINES: dict[str, Callable[[dict[str, Any]], Any]] = {
    "face": _Face,
    "speaker": _Speaker,
    "asr": _Asr,
}
TOOLS: dict[str, tuple[str, Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]]] = {
    "qa_face": ("face", face),
    "qa_speaker": ("speaker", speaker),
    "asr": ("asr", asr),
}


def _only(kind: str) -> Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]:
    tool, handle = TOOLS[kind]

    def run(state: dict[str, Any], msg: dict[str, Any]) -> dict[str, Any]:
        if state.get("tool") != tool:  # one model per process: this one loaded another tool
            raise WorkerError("unsupported_kind", f"{kind} sent to the {state.get('tool')} worker")
        return handle(state, msg)

    return run


HANDLERS = {kind: _only(kind) for kind in TOOLS}


def init(args: dict[str, Any]) -> dict[str, Any]:
    tool = str(args.get("tool") or "")
    make = ENGINES.get(tool)
    if make is None:
        raise WorkerError("qa_unknown_tool", tool)
    return {
        "tool": tool,
        "engine": make(args),
        "window_s": args.get("window_s", 1.5),
        "hop_s": args.get("hop_s", 0.75),
        "lang": args.get("lang"),
    }


if __name__ == "__main__":
    serve(HANDLERS, init)
