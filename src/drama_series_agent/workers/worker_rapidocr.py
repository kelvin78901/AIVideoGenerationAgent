"""RapidOCR on the CPU (画面文字 checks): the text in a picture, read top to bottom.

``rapidocr`` 3.10 (``RapidOCR()(path).txts``, None when it finds no text) on onnxruntime; its
models come in the wheel. First run on the real machine in M3 step 13. args: none.
"""

from __future__ import annotations

from typing import Any

from rapidocr import RapidOCR
from worker_protocol import WorkerError, serve


def init(args: dict[str, Any]) -> dict[str, Any]:
    return {"engine": RapidOCR()}


def read(state: dict[str, Any], msg: dict[str, Any]) -> dict[str, Any]:
    path = (msg.get("params") or {}).get("path")
    if not path:
        raise WorkerError("ocr_no_image", "no picture path")
    result = state["engine"](str(path))
    text = "".join(str(t) for t in (getattr(result, "txts", None) or ()))
    return {"text": text, "json": {"text": text}}


if __name__ == "__main__":
    serve({"ocr": read}, init)
