"""The real ``workers/worker_qa.py`` handlers and protocol with fake engines (no numpy, no
models), for ``tests/unit/test_worker_qa.py``: the reply has to be what ``pipeline/qa.py`` reads.

Pictures are their file names; a take is a list of frames, each the names of the faces in it
(``FRAMES``). A voice's reference "sound" is its name repeated; the take's sound is ``SOUND``.
For SyncNet a take is one face for 30 frames (``Sync``).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import worker_qa
from worker_protocol import serve

FRAMES = [["lin"], ["lin", "chen"], [], ["chen"]]
SOUND = ["lin"] * 4 + ["."] * 2 + ["chen"] * 4  # "." is silence


class Face:
    def image(self, path: str) -> Any:
        return Path(path).stem

    def frames(self, path: str, every_s: float) -> Iterator[tuple[float, Any]]:
        for i, shown in enumerate(FRAMES):
            yield i * every_s, shown

    def faces(self, picture: Any) -> list[Any]:
        return list(picture) if isinstance(picture, list) else [picture]

    def embed(self, picture: Any, face: Any) -> Any:
        return face

    def sim(self, a: Any, b: Any) -> float:
        return 0.9 if a == b else 0.1


class Speaker:
    sample_rate = 2  # window_s 1.0 → 2 samples

    def audio(self, path: str) -> Any:
        return SOUND if path.endswith(".mp4") else [Path(path).stem] * 4

    def voiced(self, samples: Any) -> bool:
        return any(s != "." for s in samples)

    def embed(self, samples: Any) -> Any:
        voiced = [s for s in samples if s != "."]
        return max(set(voiced), key=voiced.count)

    def sim(self, a: Any, b: Any) -> float:
        return 0.8 if a == b else 0.2


class Asr:
    def transcribe(self, path: str, lang: str | None) -> tuple[str, list[dict[str, Any]]]:
        return "三年了。", [{"start": 0.0, "end": 1.2, "text": "三年了。", "lang": lang}]


class Sync:
    """One face for 30 frames of the 25 fps grid; every track scores conf 4 (samples per crop)."""

    sample_rate = 100

    def grid(self, path: str) -> Iterator[tuple[int, Any]]:
        yield from enumerate([[(0.0, 0.0, 100.0, 100.0)]] * 30)

    def boxes(self, frame: Any) -> list[Any]:
        return list(frame)

    def crop(self, frame: Any, x: float, y: float, half: float) -> Any:
        return (x, y, half)

    def audio(self, path: str) -> Any:
        return [0] * 120

    def score(self, crops: list[Any], samples: Any) -> dict[str, Any]:
        return {"conf": len(samples) / len(crops), "offset": 0, "min_dist": 5.0}


worker_qa.ENGINES = {
    "face": lambda a: Face(),
    "speaker": lambda a: Speaker(),
    "asr": lambda a: Asr(),
    "sync": lambda a: Sync(),
}

if __name__ == "__main__":
    serve(worker_qa.HANDLERS, worker_qa.init)
