"""The worker side of the local model protocol (``modelhub/adapters/local_python.py``).

- One JSON object per line on stdin; one reply per line on stdout, carrying the request's
  ``id``. The first request is ``{"op": "init", "args": {...}}`` (load the model); then
  ``{"op": "run", "kind", "text", "params", "out"}``, files written under ``out``.
- stdout carries replies only: whatever a library prints (Python or C) goes to stderr.
- stdin closing ends the loop, so the worker exits with the app.

Only the standard library here: this file runs in every model's environment.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from collections.abc import Callable
from typing import Any

Handler = Callable[[Any, dict[str, Any]], dict[str, Any]]


class WorkerError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


def out_path(msg: dict[str, Any], suffix: str) -> str:
    """Where this request writes its file."""
    return os.path.join(str(msg["out"]), f"{msg['id']}{suffix}")


def serve(
    handlers: dict[str, Handler], init: Callable[[dict[str, Any]], Any] | None = None
) -> None:
    out_fd = os.dup(1)
    os.dup2(2, 1)  # C libraries writing to fd 1 now land on stderr
    out = os.fdopen(out_fd, "w", encoding="utf-8", newline="\n")
    sys.stdout = sys.stderr
    stdin = sys.stdin.buffer
    state: Any = None

    def reply(data: dict[str, Any]) -> None:
        out.write(json.dumps(data, ensure_ascii=False) + "\n")
        out.flush()

    while True:
        raw = stdin.readline()
        if not raw:
            return  # the app closed stdin
        try:
            msg = json.loads(raw.decode("utf-8"))
        except ValueError:
            continue
        rid = msg.get("id")
        try:
            if msg.get("op") == "init":
                state = init(msg.get("args") or {}) if init else None
                answer: dict[str, Any] = {}
            else:
                handler = handlers.get(str(msg.get("kind")))
                if handler is None:
                    raise WorkerError("unsupported_kind", str(msg.get("kind")))
                answer = handler(state, msg)
            reply({"id": rid, "ok": True, **answer})
        except WorkerError as exc:
            reply({"id": rid, "ok": False, "code": exc.code, "message": str(exc)[:500]})
        except Exception as exc:
            traceback.print_exc()
            message = f"{type(exc).__name__}: {exc}"[:500]
            reply({"id": rid, "ok": False, "code": "worker_error", "message": message})
