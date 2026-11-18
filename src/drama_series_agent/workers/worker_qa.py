"""The local QA tools on the CPU (M6 自动质检, ``pipeline/qa.py``): one model per worker process.

``args.tool`` picks what the process loads (``providers.yaml`` gives each model key its own
worker), so the onnxruntime that AuraFace uses and the one inside sherpa-onnx never share a process:

- ``face`` (``qa_face``): YuNet finds faces and their 5 points (OpenCV 4.x, ``2023mar``); the
  face is aligned to the ArcFace template and AuraFace's ``glintr100.onnx`` embeds it. Only
  faces it can judge count (``usable``): the embedding's length before it is normalised is low
  for a face turned or bowed away (under ``min_norm``), and a profile has its nose off the line
  between the eyes and the mouth (more than ``max_yaw`` eye-widths); those score near 0 against
  the right person, so they say nothing (M6 step 5c). In each sampled frame every usable face goes
  to the character reference it is closest to (cosine), so in a two-hander each person is scored
  against their own picture; a reference's ``sim`` is the median over the frames where it got a
  face, once there are ``min_frames`` of them. Faces smaller than ``min_face`` px (extras far
  back) are not looked at. A reference with no face in its picture, or too few usable faces in
  the take, → None (``qa.py`` counts that as 不适用).
- ``speaker`` (``qa_speaker``): CAM++ (sherpa-onnx) embeds each voice's reference and windows of
  the take's sound (``window_s`` / ``hop_s``; several people may speak in one shot), each voice
  keeps its best window. Silent windows are skipped; no voiced window → None.
- ``asr``: faster-whisper large-v3, int8 on the CPU, straight from the mp4 (PyAV). ``prompt``
  (the series' names) is Whisper's ``initial_prompt``; a segment Whisper itself thinks is not
  speech (``no_speech_prob`` over ``max_no_speech``: its 「谢谢大家」 over rain) is dropped.
- ``sync`` (``qa_sync``): SyncNet (``syncnet.py``, CPU torch) as syncnet_python runs it, with
  YuNet for S3FD: the take on a 25 fps grid, faces tracked across frames, each track cropped
  (224×224) and scored against the same stretch of sound; the most confident track counts.
  ``conf`` = median − min of the mean distances over ±``vshift`` audio offsets, the mean taken
  over the windows with sound only (syncnet_python takes every window: ``syncnet.py`` says why);
  ``offset`` is syncnet_python's (frames at 25 fps; 0 = in sync). The speaking track is the most
  confident one; its ``in_sync`` (median − min within ``near`` frames of no offset) is what QA
  judges: a take whose sound is 0.4 s early still has a confident best offset (M6 step 5c).

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
MIN_FACE_FRAMES = 3  # usable faces a reference needs before it is scored
MAX_FACES = 6  # per frame / reference picture, the largest first


class FaceEngine(Protocol):
    def image(self, path: str) -> Any: ...
    def frames(self, path: str, every_s: float) -> Iterator[tuple[float, Any]]: ...
    def faces(self, picture: Any) -> list[Any]: ...  # the largest first
    def embed(self, picture: Any, face: Any) -> Any: ...
    def usable(self, face: Any, embedding: Any) -> bool: ...
    def sim(self, a: Any, b: Any) -> float: ...


class SpeakerEngine(Protocol):
    sample_rate: int

    def audio(self, path: str) -> Any: ...
    def voiced(self, samples: Any) -> bool: ...
    def embed(self, samples: Any) -> Any: ...
    def sim(self, a: Any, b: Any) -> float: ...


class AsrEngine(Protocol):
    def transcribe(
        self, path: str, lang: str | None, prompt: str | None
    ) -> tuple[str, list[dict[str, Any]]]: ...


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
    least = int(state.get("min_frames", MIN_FACE_FRAMES))
    seen: list[list[Any]] = []
    skipped = 0  # faces turned away
    try:
        for _t, frame in eng.frames(video, every):
            shown = []
            for f in eng.faces(frame)[:MAX_FACES]:
                e = eng.embed(frame, f)
                if eng.usable(f, e):
                    shown.append(e)
                else:
                    skipped += 1
            seen.append(shown)
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
            "sim": round(_median(sims), 4) if len(sims) >= least else None,
            "low": round(min(sims), 4) if sims else None,
            "frames": len(sims),
        }
        for r, sims in zip(refs, got, strict=True)
    ]
    with_face = sum(1 for shown in seen if shown)
    return {
        "json": {"faces": faces, "frames": len(seen), "with_face": with_face, "turned": skipped}
    }


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    mid = len(ordered) // 2
    return ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2


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
    params = msg.get("params") or {}
    lang = params.get("lang") or state.get("lang")
    try:
        text, segments = eng.transcribe(_path(msg), lang, params.get("prompt") or None)
    except OSError as exc:
        raise WorkerError("qa_bad_video", str(exc)) from exc
    return {"text": text, "json": {"text": text, "segments": segments}}


# --------------------------------------------------------------------------- sync

SYNC_FPS = 25  # SyncNet's video rate; the take is read on a 25 fps grid
IOU = 0.5  # a face continues a track when it overlaps the track's last box this much
MAX_GAP = 25  # frames a track may go without its face before it ends (num_failed_det)
SMOOTH = 13  # median filter over a track's box centres and sizes (crop_video)

Box = tuple[float, float, float, float]  # x1, y1, x2, y2


class SyncEngine(Protocol):
    sample_rate: int

    def grid(self, path: str) -> Iterator[tuple[int, Any]]: ...  # frames at SYNC_FPS
    def boxes(self, frame: Any) -> list[Box]: ...  # the largest first
    def crop(self, frame: Any, x: float, y: float, half: float) -> Any: ...
    def audio(self, path: str) -> Any: ...
    def score(self, crops: list[Any], samples: Any) -> dict[str, Any] | None: ...


def iou(a: Box, b: Box) -> float:
    w = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    h = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = w * h
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def tracks(found: list[list[Box]], min_len: int, min_face: float) -> list[dict[str, Any]]:
    """Face tracks over the frames (syncnet_python ``run_pipeline.track_shot``): a face continues
    the track whose last box it overlaps most (IoU > 0.5) if that track had a face in the last
    ``MAX_GAP`` frames, else starts one. Kept: more than ``min_len`` detections and a mean box
    side over ``min_face`` px. Frames between detections get boxes by linear interpolation.
    → ``[{frames: [k …], boxes: [Box …]}]`` with one box per frame."""
    seen: list[dict[str, Any]] = []
    for k, boxes in enumerate(found):
        taken: set[int] = set()
        for box in boxes:
            best, most = -1, IOU
            for n, t in enumerate(seen):
                if n in taken or k - t["frames"][-1] > MAX_GAP:
                    continue
                overlap = iou(box, t["boxes"][-1])
                if overlap > most:
                    best, most = n, overlap
            if best < 0:
                seen.append({"frames": [k], "boxes": [box]})
                best = len(seen) - 1
            else:
                seen[best]["frames"].append(k)
                seen[best]["boxes"].append(box)
            taken.add(best)
    out = []
    for t in seen:
        if len(t["frames"]) <= min_len:
            continue
        frames, boxes = _fill(t["frames"], t["boxes"])
        side = max(
            sum(b[2] - b[0] for b in boxes) / len(boxes),
            sum(b[3] - b[1] for b in boxes) / len(boxes),
        )
        if side > min_face:
            out.append({"frames": frames, "boxes": boxes})
    return out


def _fill(frames: list[int], boxes: list[Box]) -> tuple[list[int], list[Box]]:
    out: list[Box] = []
    for (k0, b0), (k1, b1) in zip(
        zip(frames, boxes, strict=True), zip(frames[1:], boxes[1:], strict=True), strict=False
    ):
        for k in range(k0, k1):
            f = (k - k0) / (k1 - k0)
            out.append(tuple(a + (b - a) * f for a, b in zip(b0, b1, strict=True)))  # type: ignore[arg-type]
    out.append(boxes[-1])
    return list(range(frames[0], frames[-1] + 1)), out


def medfilt(values: list[float], size: int = SMOOTH) -> list[float]:
    """``scipy.signal.medfilt``: the median of each ``size`` neighbourhood, zeros past the ends."""
    half = size // 2
    padded = [0.0] * half + list(values) + [0.0] * half
    return [sorted(padded[i : i + size])[half] for i in range(len(values))]


def _r3(x: Any) -> float | None:
    return None if x is None else round(float(x), 3)


def sync(state: dict[str, Any], msg: dict[str, Any]) -> dict[str, Any]:
    """SyncNet confidence of the take's sound against each face track, over the windows with
    sound; the best track counts (the one speaking). No track long enough, or too little sound
    → ``conf`` None (``qa.py``: 不适用)."""
    eng: SyncEngine = state["engine"]
    video = _path(msg)
    try:
        sound = eng.audio(video)
        found = [eng.boxes(frame) for _k, frame in eng.grid(video)]
    except OSError as exc:
        raise WorkerError("qa_bad_video", str(exc)) from exc
    kept = tracks(found, int(state["min_track"]), float(state["min_face"]))
    plans = []  # per track: frame → crop centre and half size, smoothed as in crop_video
    for t in kept:
        xs = medfilt([(b[0] + b[2]) / 2 for b in t["boxes"]])
        ys = medfilt([(b[1] + b[3]) / 2 for b in t["boxes"]])
        ss = medfilt([max(b[2] - b[0], b[3] - b[1]) / 2 for b in t["boxes"]])
        plans.append(dict(zip(t["frames"], zip(xs, ys, ss, strict=True), strict=True)))
    crops: list[list[Any]] = [[] for _ in plans]
    if plans:
        for k, frame in eng.grid(video):
            for i, plan in enumerate(plans):
                if k in plan:
                    crops[i].append(eng.crop(frame, *plan[k]))
    per = eng.sample_rate // SYNC_FPS
    scored = []
    for t, faces in zip(kept, crops, strict=True):
        first, last = t["frames"][0], t["frames"][-1]
        got = eng.score(faces, sound[first * per : (last + 1) * per]) or {}
        scored.append(
            {
                "start": round(first / SYNC_FPS, 2),
                "end": round((last + 1) / SYNC_FPS, 2),
                "conf": _r3(got.get("conf")),
                "in_sync": _r3(got.get("in_sync")),
                "offset": got.get("offset"),
                "min_dist": _r3(got.get("min_dist")),
                "voiced": got.get("voiced"),  # windows with sound, of
                "windows": got.get("windows"),
                "conf_all": _r3(got.get("conf_all")),  # over every window, as syncnet_python
            }
        )
    rated = [s for s in scored if s["conf"] is not None]
    best = max(rated, key=lambda s: s["conf"]) if rated else {}
    return {
        "json": {
            "conf": best.get("conf"),
            "in_sync": best.get("in_sync"),
            "offset": best.get("offset"),
            "min_dist": best.get("min_dist"),
            "tracks": scored,
            "frames": len(found),
        }
    }


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


class _YuNet:
    """YuNet (OpenCV ``FaceDetectorYN``): rows ``x, y, w, h``, the 5 points' x / y, at the
    picture's own scale, the largest face first."""

    def __init__(self, cv2: Any, model: str, score: float) -> None:
        self.cv2 = cv2
        self.net = cv2.FaceDetectorYN.create(model, "", (320, 320), score, 0.3, 5000)

    def detect(self, picture: Any) -> list[Any]:
        # YuNet is trained on faces of about 10–300 px: a close-up at 768p is shrunk first.
        h, w = picture.shape[:2]
        scale = min(1.0, 640 / max(h, w))
        small = self.cv2.resize(picture, None, fx=scale, fy=scale) if scale < 1 else picture
        self.net.setInputSize((small.shape[1], small.shape[0]))
        _, found = self.net.detect(small)
        if found is None:
            return []
        rows = sorted(found, key=lambda r: float(r[2] * r[3]), reverse=True)
        return [r[:14] / scale for r in rows]


class _Face:
    """YuNet + AuraFace. ``args``: detector, recognizer, threads, score, min_face, input_mean,
    input_std, min_norm, max_yaw. ``embed`` keeps the length (``usable`` reads it); ``sim`` is
    the cosine."""

    def __init__(self, args: dict[str, Any]) -> None:
        import cv2
        import numpy as np
        import onnxruntime as ort

        self.cv2, self.np = cv2, np
        self.detector = _YuNet(cv2, str(args["detector"]), float(args.get("score", 0.8)))
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
        self.min_norm = float(args.get("min_norm", 16.0))
        self.max_yaw = float(args.get("max_yaw", 0.6))

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
        return [
            r[4:14].reshape(5, 2).astype(self.np.float64)
            for r in self.detector.detect(picture)
            if min(float(r[2]), float(r[3])) >= self.min_face
        ]

    def embed(self, picture: Any, face: Any) -> Any:
        np = self.np
        crop = self.cv2.warpAffine(picture, umeyama(np, face, self.template), (112, 112))
        blob = self.cv2.dnn.blobFromImage(
            crop, 1.0 / self.std, (112, 112), (self.mean,) * 3, swapRB=True
        )
        return np.asarray(self.rec.run(None, {self.input: blob})[0][0], np.float32)

    def usable(self, face: Any, embedding: Any) -> bool:
        np = self.np
        if float(np.linalg.norm(embedding)) < self.min_norm:
            return False
        right, left, nose, mouth_r, mouth_l = face
        eyes = (right + left) / 2
        down = (mouth_r + mouth_l) / 2 - eyes
        down = down / (np.linalg.norm(down) or 1.0)
        across = np.array([down[1], -down[0]])
        yaw = float(np.dot(nose - eyes, across)) / (float(np.linalg.norm(left - right)) or 1.0)
        return abs(yaw) <= self.max_yaw

    def sim(self, a: Any, b: Any) -> float:
        np = self.np
        return float(np.dot(a, b) / ((np.linalg.norm(a) * np.linalg.norm(b)) or 1.0))


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
    """faster-whisper. ``args``: model_dir, compute_type, beam_size, vad, threads, lang,
    max_no_speech."""

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
        self.max_no_speech = float(args.get("max_no_speech", 0.5))

    def transcribe(
        self, path: str, lang: str | None, prompt: str | None
    ) -> tuple[str, list[dict[str, Any]]]:
        segments, _info = self.model.transcribe(
            path,
            language=lang or None,
            beam_size=self.beam,
            vad_filter=self.vad,
            condition_on_previous_text=False,
            initial_prompt=prompt,
        )
        out = [
            {
                "start": round(s.start, 2),
                "end": round(s.end, 2),
                "text": s.text.strip(),
                "no_speech": round(s.no_speech_prob, 3),
            }
            for s in segments  # a generator: decoding happens here
            if s.no_speech_prob <= self.max_no_speech
        ]
        return "".join(s["text"] for s in out), out


class _Sync:
    """YuNet + SyncNet (``syncnet.py``, CPU torch). ``args``: detector, weights, threads, score,
    vshift, batch, min_rms, min_voiced, near."""

    sample_rate = 16000
    CROP_SCALE = 0.4  # run_pipeline --crop_scale

    def __init__(self, args: dict[str, Any]) -> None:
        import cv2
        from syncnet import SyncNet

        self.cv2 = cv2
        self.detector = _YuNet(cv2, str(args["detector"]), float(args.get("score", 0.8)))
        self.net = SyncNet(
            str(args["weights"]),
            threads=int(args.get("threads", 4)),
            vshift=int(args.get("vshift", 15)),
            batch=int(args.get("batch", 20)),
            min_rms=float(args.get("min_rms", 0.01)),
            min_voiced=int(args.get("min_voiced", 10)),
            near=int(args.get("near", 2)),
        )

    def grid(self, path: str) -> Iterator[tuple[int, Any]]:
        from worker_video import grid

        return grid(path, float(SYNC_FPS))

    def boxes(self, frame: Any) -> list[Box]:
        return [
            (float(r[0]), float(r[1]), float(r[0] + r[2]), float(r[1] + r[3]))
            for r in self.detector.detect(frame)
        ]

    def crop(self, frame: Any, x: float, y: float, half: float) -> Any:
        # crop_video: the box's centre, a square from just above the eyes to below the chin,
        # the picture padded with grey 110 first; 224×224.
        cs = self.CROP_SCALE
        pad = int(half * (1 + 2 * cs))
        big = self.cv2.copyMakeBorder(
            frame, pad, pad, pad, pad, self.cv2.BORDER_CONSTANT, value=(110, 110, 110)
        )
        my, mx = y + pad, x + pad
        face = big[
            int(my - half) : int(my + half * (1 + 2 * cs)),
            int(mx - half * (1 + cs)) : int(mx + half * (1 + cs)),
        ]
        return self.cv2.resize(face, (224, 224))

    def audio(self, path: str) -> Any:
        from worker_video import audio

        return audio(path)

    def score(self, crops: list[Any], samples: Any) -> dict[str, Any] | None:
        return self.net.score(crops, samples)


ENGINES: dict[str, Callable[[dict[str, Any]], Any]] = {
    "face": _Face,
    "speaker": _Speaker,
    "asr": _Asr,
    "sync": _Sync,
}
TOOLS: dict[str, tuple[str, Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]]] = {
    "qa_face": ("face", face),
    "qa_speaker": ("speaker", speaker),
    "asr": ("asr", asr),
    "qa_sync": ("sync", sync),
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
        "min_track": args.get("min_track", 25),
        "min_face": args.get("min_face", 50),
        "min_frames": args.get("min_frames", MIN_FACE_FRAMES),
    }


if __name__ == "__main__":
    serve(HANDLERS, init)
