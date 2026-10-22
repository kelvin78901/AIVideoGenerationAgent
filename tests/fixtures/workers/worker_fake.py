"""A fake local model for tests/unit/test_local_python.py: speaks the real worker protocol
(``workers/worker_protocol.py``) with the standard library only.

By the line's text: ``hang`` never answers, ``crash`` exits, ``fail`` answers an error; anything
else writes a short WAV. Each answer says which process made it.
"""

from __future__ import annotations

import os
import sys
import time
import wave
from typing import Any

from worker_protocol import WorkerError, out_path, serve


def init(args: dict[str, Any]) -> dict[str, Any]:
    if args.get("init_fail"):
        raise WorkerError("model_load_failed", "cannot load")
    print("loading the model (library chatter on stdout)")
    return {"args": args}


def speak(state: dict[str, Any], msg: dict[str, Any]) -> dict[str, Any]:
    text = msg.get("text") or ""
    if text == "hang":
        time.sleep(3600)
    if text == "crash":
        print("fatal: out of memory", file=sys.stderr, flush=True)
        os._exit(3)
    if text == "fail":
        raise WorkerError("bad_line", "cannot say that")
    print("chatter from Python")
    os.write(1, b"chatter from C\n")
    path = out_path(msg, ".wav")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * 4000)
    meta = {"pid": os.getpid(), "args": state["args"], "text": text, "params": msg.get("params")}
    return {"files": [{"path": path, "mime": "audio/wav", "duration_s": 0.5}], "json": meta}


def ocr(state: dict[str, Any], msg: dict[str, Any]) -> dict[str, Any]:
    return {"text": "便利贴", "json": {"text": "便利贴", "pid": os.getpid()}}


if __name__ == "__main__":
    serve({"tts": speak, "ocr": ocr}, init)
