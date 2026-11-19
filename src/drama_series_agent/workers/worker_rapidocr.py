"""RapidOCR on the CPU (画面文字 checks): the text in a picture, read top to bottom.

``rapidocr`` 3.10 (``RapidOCR()(path).txts``, None when it finds no text) on onnxruntime; its
models come in the wheel. First run on the real machine in M3 step 13. args: none.

A take (M6 自动质检): ``params.every_s`` given → the video is sampled every ``every_s`` seconds
(``worker_video.frames``, OpenCV's FFmpeg) and each frame read; the answer carries
``json.frames[{t, text, boxes}]``, ``boxes`` where the text is on the frame as
``[x0, y0, x1, y1]`` on 0–1 (M6: the take's mask dialog warns when the mask covers it).
RapidOCR takes a BGR ndarray as it is, so the frames go in directly.
"""

from __future__ import annotations

from typing import Any

from worker_protocol import WorkerError, serve


def init(args: dict[str, Any]) -> dict[str, Any]:
    from rapidocr import RapidOCR
    from worker_video import frames

    return {"engine": RapidOCR(), "frames": frames}


def _text(state: dict[str, Any], picture: Any) -> str:
    result = state["engine"](picture)
    return "".join(str(t) for t in (getattr(result, "txts", None) or ()))


def _read(state: dict[str, Any], picture: Any) -> dict[str, Any]:
    """A frame's text and where it is: each detected line's box (its four corners) as the
    rectangle around it on 0–1 of the frame."""
    result = state["engine"](picture)
    text = "".join(str(t) for t in (getattr(result, "txts", None) or ()))
    h, w = picture.shape[:2]
    boxes = []
    for quad in (
        getattr(result, "boxes", None) if getattr(result, "boxes", None) is not None else ()
    ):
        xs = [float(p[0]) for p in quad]
        ys = [float(p[1]) for p in quad]
        boxes.append(
            [
                round(min(xs) / w, 4),
                round(min(ys) / h, 4),
                round(max(xs) / w, 4),
                round(max(ys) / h, 4),
            ]
        )
    return {"text": text, "boxes": boxes}


def read(state: dict[str, Any], msg: dict[str, Any]) -> dict[str, Any]:
    params = msg.get("params") or {}
    path = params.get("path")
    if not path:
        raise WorkerError("ocr_no_image", "no picture path")
    every = params.get("every_s")
    if not every:
        text = _text(state, str(path))
        return {"text": text, "json": {"text": text}}
    try:
        frames = [{"t": t, **_read(state, f)} for t, f in state["frames"](str(path), every)]
    except OSError as exc:
        raise WorkerError("ocr_bad_video", str(exc)) from exc
    text = "\n".join(f["text"] for f in frames if f["text"])
    return {"text": text, "json": {"text": text, "frames": frames}}


if __name__ == "__main__":
    serve({"ocr": read}, init)
