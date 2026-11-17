"""Frames and sound from a take, for the CPU QA workers (``worker_qa``, ``worker_rapidocr``).

Imports are inside the functions: this file is on every worker's path, and only the environments
that sample video (``qa``, ``ocr``: both ship OpenCV with FFmpeg) or decode audio (``qa``: PyAV)
have the libraries.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

SAMPLE_RATE = 16000


def frames(path: str, every_s: float) -> Iterator[tuple[float, Any]]:
    """(seconds, BGR frame) at 0, every_s, 2·every_s … read in order, never seeking.

    Short clips: a sequential ``grab()`` is cheap, and seeking is not exact with every codec.
    """
    import cv2

    cap = cv2.VideoCapture(path, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        raise OSError(f"cannot open {path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    try:
        index, due = 0, 0.0
        while cap.grab():
            t = index / fps if fps > 0 else cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
            index += 1
            if t + 1e-6 < due:
                continue
            ok, frame = cap.retrieve()
            if ok and frame is not None:
                yield round(t, 3), frame
            due += every_s
            while due <= t:
                due += every_s
    finally:
        cap.release()


def grid(path: str, fps: float = 25.0) -> Iterator[tuple[int, Any]]:
    """(k, BGR frame) for k = 0, 1, 2 … at ``fps``: frame k is the source frame nearest to
    ``k / fps`` (what ``ffmpeg -r 25`` does to a 24 / 30 fps clip), read in order, never seeking.
    A frame is repeated or skipped when the source rate differs; the source's rate unknown → taken
    as ``fps``."""
    import cv2

    cap = cv2.VideoCapture(path, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        raise OSError(f"cannot open {path}")
    src = cap.get(cv2.CAP_PROP_FPS) or fps
    try:
        index, k = 0, 0
        while cap.grab():
            want = round(k * src / fps)
            if want == index:
                ok, frame = cap.retrieve()
                if not ok or frame is None:
                    return
                while want == index:
                    yield k, frame
                    k += 1
                    want = round(k * src / fps)
            index += 1
    finally:
        cap.release()


def audio(path: str) -> Any:
    """Mono float32 samples in [-1, 1] at 16 kHz (``faster_whisper.audio.decode_audio``'s way).

    Works on the take's mp4 and on a voice's reference wav / mp3. Empty when there is no sound.
    """
    import av
    import numpy as np

    chunks: list[Any] = []
    with av.open(path, metadata_errors="ignore") as container:
        if not container.streams.audio:
            return np.zeros(0, np.float32)
        resampler = av.audio.resampler.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
        for frame in container.decode(audio=0):
            for out in resampler.resample(frame):
                chunks.append(out.to_ndarray().reshape(-1))
        for out in resampler.resample(None):
            chunks.append(out.to_ndarray().reshape(-1))
    if not chunks:
        return np.zeros(0, np.float32)
    return np.concatenate(chunks).astype(np.float32) / 32768.0
