"""Dialogue audio (M3): every voice sample and every dubbed line goes through
``prepare_dialogue`` before it becomes a version's file.

It decodes to 48 kHz mono, trims leading and trailing silence (keeping ``KEEP_S`` at each end,
so a cut never clips the first consonant), and brings the clip to one
loudness, then writes 16-bit WAV. It also measures the result: duration, loudness, true peak,
and a 64-bar waveform the UI draws without decoding the audio itself.

FFmpeg does the work. Its binary ships with ``imageio-ffmpeg``, which is already a dependency;
SPEC 2 names pyloudnorm, but that would bring numpy and scipy into the main environment
(DECISIONS M3).

Loudness is EBU R128 integrated loudness from FFmpeg's ``ebur128`` filter. A clip too short to
gate (under 0.4 s) falls back to its RMS level.

The gain is the smaller of two amounts:
- what brings the clip to the target loudness;
- what keeps its true peak under the ceiling.

Nothing is compressed or clipped. A very peaky clip (a scream) ends up a little quieter than the
target instead of distorted.

Components call ``prepare_clip``: with ``DRAMA_FAST_AUDIO=1`` (most tests) it skips FFmpeg and
only measures the clip, a 16-bit mono WAV as the Mock makes.
"""

from __future__ import annotations

import array
import asyncio
import io
import math
import os
import re
import subprocess
import sys
import wave
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from drama_series_agent.core.config import get_config

WAVEFORM_BARS = 64
KEEP_S = 0.05  # silence kept before the first sound
FADE_S = 0.05  # fade-out at the end of the sound, before the padding
SHORTEST_GATED_S = 0.4  # BS.1770 gating blocks are 400 ms
_I = re.compile(r"\bI:\s+(-?inf|-?\d+(?:\.\d+)?) LUFS")
_PEAK = re.compile(r"\bPeak:\s+(-?inf|-?\d+(?:\.\d+)?) dBFS")


class AudioError(Exception):
    """Audio that cannot be prepared; ``code`` reaches the UI (``audio_silent`` …)."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code


@dataclass(frozen=True)
class DialogueTarget:
    """``config/components.yaml`` ``audio.dialogue``."""

    lufs: float = -18.0
    peak_dbtp: float = -1.5
    trim_db: float = -45.0  # quieter than this at either end counts as silence (after levelling)
    sample_rate: int = 48000
    # After the last sound: half kept of what follows it (its decay), half added as silence.
    tail_s: float = 0.3

    @classmethod
    def from_config(cls) -> DialogueTarget:
        d = get_config().components.audio.dialogue
        return cls(
            lufs=d.lufs,
            peak_dbtp=d.peak_dbtp,
            trim_db=d.trim_db,
            sample_rate=d.sample_rate,
            tail_s=d.tail_s,
        )


@dataclass(frozen=True)
class Measured:
    lufs: float | None  # None: silent
    peak_db: float | None  # true peak, dBTP


@dataclass(frozen=True)
class PreparedAudio:
    data: bytes  # 16-bit mono WAV
    duration_s: float
    lufs: float | None
    peak_db: float | None
    waveform: list[float]  # WAVEFORM_BARS peaks, 0–1 of full scale


def ffmpeg_exe() -> str:
    import imageio_ffmpeg

    return str(imageio_ffmpeg.get_ffmpeg_exe())


def _ffmpeg(*args: str) -> str:
    """Run FFmpeg; returns what it printed on stderr (the filters' reports)."""
    proc = subprocess.run(
        [ffmpeg_exe(), "-hide_banner", "-nostdin", *args],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        check=False,
    )
    text = proc.stderr.decode("utf-8", errors="replace")
    if proc.returncode != 0:
        raise AudioError("audio_ffmpeg_failed", text[-400:])
    return text


def _number(pattern: re.Pattern[str], text: str) -> float | None:
    found = pattern.findall(text)
    if not found or "inf" in found[-1]:
        return None
    return float(found[-1])


def _samples(wav_bytes: bytes) -> tuple[array.array[int], int]:
    with wave.open(io.BytesIO(wav_bytes)) as w:
        if w.getsampwidth() != 2 or w.getnchannels() != 1:
            raise AudioError("audio_bad_format", "expected 16-bit mono")
        frames = w.readframes(w.getnframes())
        rate = w.getframerate()
    samples = array.array("h")
    samples.frombytes(frames)
    if sys.byteorder == "big":
        samples.byteswap()
    return samples, rate


def rms_db(samples: array.array[int]) -> float | None:
    if not samples:
        return None
    mean = sum(s * s for s in samples) / len(samples)
    return 20 * math.log10(math.sqrt(mean) / 32768) if mean > 0 else None


def waveform(samples: array.array[int], bars: int = WAVEFORM_BARS) -> list[float]:
    if not samples:
        return [0.0] * bars
    size = len(samples) / bars
    out = []
    for i in range(bars):
        chunk = samples[int(i * size) : max(int((i + 1) * size), int(i * size) + 1)]
        peak = max((abs(s) for s in chunk), default=0)
        out.append(round(min(peak / 32767, 1.0), 3))
    return out


def measure(path: Path) -> Measured:
    """Integrated loudness (LUFS) and true peak (dBTP) of a file."""
    text = _ffmpeg("-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-")
    return Measured(lufs=_number(_I, text), peak_db=_number(_PEAK, text))


async def prepare_clip(data: bytes) -> PreparedAudio:
    """What a voice sample or a dubbed line goes through: ``prepare_dialogue``, or under
    ``DRAMA_FAST_AUDIO=1`` the clip as it is, measured (no loudness)."""
    if os.environ.get("DRAMA_FAST_AUDIO") == "1":
        samples, rate = _samples(data)
        if not samples:
            raise AudioError("audio_silent")
        duration = round(len(samples) / rate, 3)
        return PreparedAudio(data, duration, None, None, waveform(samples))
    return await prepare_dialogue(data)


async def prepare_dialogue(data: bytes, target: DialogueTarget | None = None) -> PreparedAudio:
    """Trim, level and re-encode one clip (any format FFmpeg reads: WAV, MP3, FLAC …), in a
    worker thread."""
    return await asyncio.to_thread(_prepare, data, target or DialogueTarget.from_config())


def _level(path: Path, tmp: str) -> float | None:
    """Integrated loudness, or the RMS level of a clip too short to gate."""
    lufs = measure(path).lufs
    if lufs is None or lufs <= -69.0:  # too short to gate (or silent): use the RMS level
        plain = Path(tmp, "plain.wav")
        _ffmpeg("-i", str(path), "-c:a", "pcm_s16le", "-y", str(plain))
        samples, _ = _samples(plain.read_bytes())
        return rms_db(samples)
    return lufs


def _prepare(data: bytes, t: DialogueTarget) -> PreparedAudio:
    with TemporaryDirectory(prefix="drama-audio-") as tmp:
        src, trimmed, out = Path(tmp, "in"), Path(tmp, "trimmed.wav"), Path(tmp, "out.wav")
        src.write_bytes(data)
        # Silence is judged as it will sound after levelling: a whispered line raised by 15 dB
        # keeps its soft ending, which a fixed threshold on the raw clip would cut off.
        raw = _level(src, tmp)
        if raw is None:
            raise AudioError("audio_silent")
        threshold = max(t.trim_db - max(t.lufs - raw, 0.0), -90.0)
        tail = t.tail_s / 2

        def trim(keep: float) -> str:
            return (
                "silenceremove=start_periods=1"
                f":start_threshold={threshold:.1f}dB:start_silence={keep}"
            )

        # Float in between, so the gain below never works on clipped samples. The end keeps
        # half the tail of what follows the last sound, fades its last FADE_S out and gets
        # the other half as silence: a line never stops on a sound still ringing.
        chain = (
            f"{trim(KEEP_S)},areverse,{trim(tail)},afade=t=in:d={FADE_S},areverse,"
            f"apad=pad_dur={tail}"
        )
        _ffmpeg(
            "-i", str(src),
            "-af", chain,
            "-ac", "1", "-ar", str(t.sample_rate), "-c:a", "pcm_f32le", "-y", str(trimmed),
        )  # fmt: skip
        before = measure(trimmed)
        lufs = _level(trimmed, tmp)
        if lufs is None:
            raise AudioError("audio_silent")
        gain = t.lufs - lufs
        if before.peak_db is not None:
            gain = min(gain, t.peak_dbtp - before.peak_db)
        _ffmpeg(
            "-i", str(trimmed),
            "-af", f"volume={gain:.3f}dB",
            "-ac", "1", "-ar", str(t.sample_rate), "-c:a", "pcm_s16le", "-y", str(out),
        )  # fmt: skip
        result = out.read_bytes()
        after = measure(out)
    samples, rate = _samples(result)
    if not samples:
        raise AudioError("audio_silent")
    return PreparedAudio(
        data=result,
        duration_s=round(len(samples) / rate, 3),
        lufs=after.lufs,
        peak_db=after.peak_db,
        waveform=waveform(samples),
    )
