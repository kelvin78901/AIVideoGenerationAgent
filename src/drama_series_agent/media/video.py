"""Video takes (M5): what a clip is, and the cuts the video component makes.

- ``probe``: size, duration, frame rate and whether there is a sound track, read from what
  FFmpeg prints about its input (``imageio-ffmpeg`` ships FFmpeg but no ffprobe).
- ``trim_head``: every take loses its first ``TRIM_HEAD_S`` (H3 opens with a garbled sound,
  SPEC 5.1). It is re-encoded so the cut is frame-exact rather than at the nearest keyframe.
- ``frame``: a PNG of the first frame (the card's poster) or the last one (the next shot's
  first frame when it continues this one, SPEC 7.4).

All of it runs FFmpeg in a worker thread; the async functions are what components call.
"""

from __future__ import annotations

import asyncio
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal

from drama_series_agent.media.audio import ffmpeg_exe

TRIM_HEAD_S = 0.3
_DURATION = re.compile(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)")
_VIDEO = re.compile(r"Stream #\S+.*?: Video: .*?(\d{2,5})x(\d{2,5})")
_FPS = re.compile(r"(\d+(?:\.\d+)?) fps")


class VideoError(Exception):
    """A clip FFmpeg cannot read or cut; ``code`` reaches the UI (``video_unreadable`` …)."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code


@dataclass(frozen=True)
class VideoInfo:
    w: int
    h: int
    duration_s: float
    fps: float | None
    has_audio: bool


def _run(*args: str, ok_codes: tuple[int, ...] = (0,)) -> str:
    proc = subprocess.run(
        [ffmpeg_exe(), "-hide_banner", "-nostdin", *args],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        check=False,
    )
    text = proc.stderr.decode("utf-8", errors="replace")
    if proc.returncode not in ok_codes:
        raise VideoError("video_ffmpeg_failed", text[-400:])
    return text


def _probe_file(path: Path) -> VideoInfo:
    # With no output FFmpeg exits 1 after printing what it found about the input.
    text = _run("-i", str(path), ok_codes=(0, 1))
    size, duration = _VIDEO.search(text), _DURATION.search(text)
    if size is None or duration is None:
        raise VideoError("video_unreadable", text[-400:])
    h_, m_, s_ = duration.groups()
    video_line = next(line for line in text.splitlines() if ": Video: " in line)
    fps = _FPS.search(video_line)
    return VideoInfo(
        w=int(size.group(1)),
        h=int(size.group(2)),
        duration_s=round(int(h_) * 3600 + int(m_) * 60 + float(s_), 3),
        fps=float(fps.group(1)) if fps else None,
        has_audio=any(": Audio: " in line for line in text.splitlines()),
    )


def _probe(data: bytes) -> VideoInfo:
    with TemporaryDirectory() as tmp:
        src = Path(tmp) / "in.mp4"
        src.write_bytes(data)
        return _probe_file(src)


def _trim_head(data: bytes, seconds: float) -> bytes:
    with TemporaryDirectory() as tmp:
        src, out = Path(tmp) / "in.mp4", Path(tmp) / "out.mp4"
        src.write_bytes(data)
        info = _probe_file(src)
        if info.duration_s <= seconds + 0.1:
            raise VideoError("video_too_short", f"{info.duration_s}s")
        args = ["-ss", f"{seconds:.3f}", "-i", str(src), "-map", "0:v:0"]
        args += ["-map", "0:a:0", "-c:a", "aac", "-b:a", "192k"] if info.has_audio else []
        args += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p"]
        _run(*args, "-movflags", "+faststart", "-y", str(out))
        return out.read_bytes()


def _frame(data: bytes, which: Literal["first", "last"]) -> bytes:
    with TemporaryDirectory() as tmp:
        src, out = Path(tmp) / "in.mp4", Path(tmp) / "frame.png"
        src.write_bytes(data)
        if which == "first":
            _run("-i", str(src), "-frames:v", "1", "-y", str(out))
        else:
            # Decode the last half second and keep overwriting: what is left is the last frame.
            _run("-sseof", "-0.5", "-i", str(src), "-update", "1", "-y", str(out))
        if not out.exists():
            raise VideoError("video_unreadable", f"no {which} frame")
        return out.read_bytes()


async def probe(data: bytes) -> VideoInfo:
    return await asyncio.to_thread(_probe, data)


async def trim_head(data: bytes, seconds: float = TRIM_HEAD_S) -> bytes:
    """``data`` without its first ``seconds``, re-encoded (H.264, AAC when it has sound)."""
    return await asyncio.to_thread(_trim_head, data, seconds)


async def frame(data: bytes, which: Literal["first", "last"]) -> bytes:
    """The first or last frame of a clip as a PNG."""
    return await asyncio.to_thread(_frame, data, which)
