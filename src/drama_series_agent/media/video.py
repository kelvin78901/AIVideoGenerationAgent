"""Video takes (M5): what a clip is, and the cuts the video component makes.

- ``probe``: size, duration, frame rate and whether there is a sound track, read from what
  FFmpeg prints about its input (``imageio-ffmpeg`` ships FFmpeg but no ffprobe).
- ``trim_head``: every take loses its first ``TRIM_HEAD_S`` (H3 opens with a garbled sound,
  SPEC 5.1). It is re-encoded so the cut is frame-exact rather than at the nearest keyframe.
- ``frame``: a PNG of the first frame (the card's poster) or the last one (the next shot's
  first frame when it continues this one, SPEC 7.4).
- ``tail_clip``: a take's last ``TAIL_FRAMES`` frames with their sound, which a local H3 take
  of the shot continuing it is guided with at frame 0 (M5 step 15e); that take then loses
  those frames instead of ``TRIM_HEAD_S``. Encoded losslessly (step 15m: no second lossy pass
  before H3's VAE encodes it again); the sound may stop sooner (``audio_frames``).
- ``scene_cuts``: where a take seems to cut to another picture inside the clip (FFmpeg's scene
  score), which a take of one continuous shot should never do (M5 step 15j; M6 checks it).
- ``usable_window``: where a take is worth cutting from and to (M5 step 15i): H3 holds its
  first frame for up to a second before anything moves, and acts and speaks across its whole
  clip (at least 5.17 s) whatever the shot's length, so an edit that takes the shot's seconds
  from the start keeps the stillness and loses the line. The take is kept whole; the window is
  recorded for the edit.

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
TAIL_FRAMES = 22  # H3's clip guides take 17k + 5 frames; 22 is a little under a second
TAIL_AUDIO_FRAMES = 22  # how much of the tail's sound goes with it (step 15m)
STILL_DB = 45.0  # two frames this alike (PSNR): nothing moved between them
SPEECH_SHARE = 0.25  # of the loudest 50 ms: what counts as the line being spoken
SPEECH_PAD_S = 0.25  # kept before and after the line
SCENE_CUT = 0.35  # FFmpeg's scene score over which two frames look like a cut
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
        # The trim filters cut by timestamp, so the first frame kept is the one at ``seconds``
        # (input seeking re-encoded showed it twice, 2026-11-09); a millisecond early, as
        # ``seconds`` is rounded (22 frames at 24 fps).
        start = max(0.0, seconds - 0.001)
        graph = f"[0:v]trim=start={start:.4f},setpts=PTS-STARTPTS[v]"
        args = ["-i", str(src)]
        if info.has_audio:
            graph += f";[0:a]atrim=start={start:.4f},asetpts=PTS-STARTPTS[a]"
            args += ["-filter_complex", graph, "-map", "[v]", "-map", "[a]"]
            args += ["-c:a", "aac", "-b:a", "192k"]
        else:
            args += ["-filter_complex", graph, "-map", "[v]"]
        # The source's frame rate, said outright (from filtered timestamps FFmpeg may guess 25.14).
        args += ["-r", f"{info.fps or 24:g}"]
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


def _frame_count(src: Path) -> int:
    """The video stream's frames, decoded and counted (the container's duration also covers a
    sound track a little longer than the picture)."""
    text = _run("-i", str(src), "-map", "0:v:0", "-f", "null", "-")
    found = re.findall(r"frame=\s*(\d+)", text)
    if not found:
        raise VideoError("video_unreadable", text[-400:])
    return int(found[-1])


def _tail(data: bytes, frames: int, fps: float, audio_frames: int, lossless: bool) -> bytes:
    with TemporaryDirectory() as tmp:
        src, out = Path(tmp) / "in.mp4", Path(tmp) / "tail.mp4"
        src.write_bytes(data)
        info = _probe_file(src)
        rate = info.fps or fps
        total = _frame_count(src)
        if total < frames:
            raise VideoError("video_too_short", f"{info.duration_s}s")
        first = total - frames
        graph = f"[0:v]trim=start_frame={first},setpts=PTS-STARTPTS[v]"
        args = ["-i", str(src)]
        if info.has_audio:
            heard = min(audio_frames, frames) / rate
            graph += f";[0:a]atrim=start={first / rate:.4f}:duration={heard:.4f}"
            graph += ",asetpts=PTS-STARTPTS[a]"
            args += ["-filter_complex", graph, "-map", "[v]", "-map", "[a]"]
            args += ["-c:a", "alac"] if lossless else ["-c:a", "aac", "-b:a", "192k"]
        else:
            args += ["-filter_complex", graph, "-map", "[v]"]
        args += ["-r", f"{rate:g}"]
        quality = ["-qp", "0"] if lossless else ["-crf", "10"]
        args += ["-c:v", "libx264", "-preset", "veryfast", *quality, "-pix_fmt", "yuv420p"]
        _run(*args, "-movflags", "+faststart", "-y", str(out))
        return out.read_bytes()


@dataclass(frozen=True)
class Window:
    in_s: float
    out_s: float


def _still_head(src: Path, fps: float) -> float:
    """Seconds before the first frame that differs from the one before (``STILL_DB``)."""
    graph = (
        "[0:v]split[a][b];[b]trim=start_frame=1,setpts=PTS-STARTPTS[c];[a][c]psnr=stats_file=p.log"
    )
    with TemporaryDirectory() as tmp:
        proc = subprocess.run(
            [ffmpeg_exe(), "-hide_banner", "-nostdin", "-i", str(src.resolve()),
             "-filter_complex", graph, "-f", "null", "-"],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, cwd=tmp, check=False,
        )  # fmt: skip
        log = Path(tmp) / "p.log"
        if proc.returncode != 0 or not log.exists():
            raise VideoError("video_ffmpeg_failed", proc.stderr.decode("utf-8", "replace")[-400:])
        values = [
            99.0 if m.group(1) == "inf" else float(m.group(1))
            for m in re.finditer(r"psnr_avg:(\S+)", log.read_text())
        ][:-1]  # the last frame is compared with itself again
    moved = next((i for i, v in enumerate(values) if v < STILL_DB), 0)
    return moved / fps


def _speech(src: Path) -> tuple[float, float] | None:
    """Where the sound is loudest (``SPEECH_SHARE`` of its peak), in 50 ms steps."""
    proc = subprocess.run(
        [ffmpeg_exe(), "-hide_banner", "-nostdin", "-loglevel", "error", "-i", str(src),
         "-map", "0:a:0", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
        capture_output=True, check=False,
    )  # fmt: skip
    pcm = proc.stdout
    step = 800  # 50 ms of 16 kHz
    if proc.returncode != 0 or len(pcm) < step * 2:
        return None
    samples = memoryview(pcm).cast("h")
    levels = []
    for i in range(0, len(samples) - step + 1, step):
        chunk = samples[i : i + step]
        levels.append((sum(x * x for x in chunk) / step) ** 0.5)
    peak = max(levels)
    if peak < 300:  # silence
        return None
    loud = [i for i, v in enumerate(levels) if v >= SPEECH_SHARE * peak]
    return loud[0] * 0.05, (loud[-1] + 1) * 0.05


def _window(data: bytes, shot_s: float, spoken: bool) -> Window:
    with TemporaryDirectory() as tmp:
        src = Path(tmp) / "in.mp4"
        src.write_bytes(data)
        info = _probe_file(src)
        duration = info.duration_s
        start = min(_still_head(src, info.fps or 24.0), max(0.0, duration - shot_s))
        end = min(duration, start + shot_s)
        span = _speech(src) if spoken and info.has_audio else None
        if span is not None:
            start = min(start, max(0.0, span[0] - SPEECH_PAD_S))
            end = min(duration, max(end, span[1] + SPEECH_PAD_S))
        return Window(round(start, 3), round(end, 3))


def _cuts(data: bytes) -> list[float]:
    with TemporaryDirectory() as tmp:
        src = Path(tmp) / "in.mp4"
        src.write_bytes(data)
        text = _run(
            "-i", str(src), "-map", "0:v:0",
            "-vf", f"select='gt(scene,{SCENE_CUT})',showinfo", "-f", "null", "-",
        )  # fmt: skip
    return [round(float(m), 3) for m in re.findall(r"pts_time:([\d.]+)", text)]


async def probe(data: bytes) -> VideoInfo:
    return await asyncio.to_thread(_probe, data)


async def trim_head(data: bytes, seconds: float = TRIM_HEAD_S) -> bytes:
    """``data`` without its first ``seconds``, re-encoded (H.264, AAC when it has sound)."""
    return await asyncio.to_thread(_trim_head, data, seconds)


async def frame(data: bytes, which: Literal["first", "last"]) -> bytes:
    """The first or last frame of a clip as a PNG."""
    return await asyncio.to_thread(_frame, data, which)


async def tail_clip(
    data: bytes,
    frames: int = TAIL_FRAMES,
    fps: float = 24.0,
    *,
    audio_frames: int = TAIL_AUDIO_FRAMES,
    lossless: bool = True,
) -> bytes:
    """The last ``frames`` frames of a clip with the sound of the first ``audio_frames`` of
    them, re-encoded losslessly unless told not to (``fps`` when FFmpeg does not say the
    clip's own)."""
    return await asyncio.to_thread(_tail, data, frames, fps, audio_frames, lossless)


async def usable_window(data: bytes, shot_s: float, *, spoken: bool) -> Window:
    """Where to cut a take: from where something first moves (not before ``shot_s`` would fit),
    for at least ``shot_s``; with a spoken line (``spoken``), the line whole with a little air.
    """
    return await asyncio.to_thread(_window, data, shot_s, spoken)


async def scene_cuts(data: bytes) -> list[float]:
    """Seconds at which the picture changes like a cut (FFmpeg's scene score over
    ``SCENE_CUT``)."""
    return await asyncio.to_thread(_cuts, data)
