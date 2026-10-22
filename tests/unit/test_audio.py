"""Dialogue audio (``media/audio.py``): trimmed, levelled, peak-safe, measured."""

from __future__ import annotations

import io
import math
import struct
import wave

import pytest

from drama_series_agent.media.audio import (
    KEEP_S,
    WAVEFORM_BARS,
    AudioError,
    DialogueTarget,
    prepare_dialogue,
)


def _wav(parts: list[tuple[float, float]], rate: int = 44100, freq: float = 440.0) -> bytes:
    """(seconds, amplitude 0–1) pieces of a sine; amplitude 0 is silence."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = bytearray()
        for seconds, amp in parts:
            for i in range(int(seconds * rate)):
                level = amp * 32767 * math.sin(2 * math.pi * freq * i / rate)
                frames += struct.pack("<h", int(level))
        w.writeframes(bytes(frames))
    return buf.getvalue()


async def test_trims_silence_and_levels_to_the_target() -> None:
    target = DialogueTarget()
    out = await prepare_dialogue(_wav([(0.5, 0.0), (1.0, 0.1), (0.5, 0.0)]), target)
    # 0.05 s before, then half the 0.3 s tail kept of the silence after and half added
    assert out.duration_s == pytest.approx(KEEP_S + 1.0 + target.tail_s, abs=0.03)
    assert out.lufs is not None and out.lufs == pytest.approx(target.lufs, abs=0.5)
    assert out.peak_db is not None and out.peak_db <= target.peak_dbtp + 0.1
    assert len(out.waveform) == WAVEFORM_BARS and max(out.waveform) > 0.1
    with wave.open(io.BytesIO(out.data)) as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (48000, 1, 2)


async def test_the_peak_ceiling_wins_over_loudness() -> None:
    """A quiet line with one loud bang: raising it to -18 LUFS would clip, so it stays
    quieter and the true peak stays under the ceiling."""
    target = DialogueTarget()
    clip = _wav([(1.0, 0.005), (0.02, 0.98), (1.0, 0.005)])
    out = await prepare_dialogue(clip, target)
    assert out.peak_db is not None and out.peak_db <= target.peak_dbtp + 0.1
    assert out.lufs is not None and out.lufs < target.lufs - 3


async def test_a_short_clip_falls_back_to_rms() -> None:
    out = await prepare_dialogue(_wav([(0.25, 0.2)]))
    assert out.duration_s == pytest.approx(0.25 + DialogueTarget().tail_s / 2, abs=0.03)
    assert out.peak_db is not None and out.peak_db <= DialogueTarget().peak_dbtp + 0.1


async def test_silence_is_refused() -> None:
    with pytest.raises(AudioError) as err:
        await prepare_dialogue(_wav([(1.0, 0.0)]))
    assert err.value.code == "audio_silent"


async def test_a_whispered_line_keeps_its_soft_ending_and_a_tail() -> None:
    """Silence is judged after levelling: a quiet line's fading last syllable (about -57 dBFS
    raw, far louder once raised to -18 LUFS) stays, then half the tail of silence after it is
    kept and half added, so the line never stops on a sound still ringing."""
    target = DialogueTarget()
    clip = _wav([(0.5, 0.0), (0.6, 0.02), (0.3, 0.002), (0.5, 0.0)])
    out = await prepare_dialogue(clip, target)
    assert out.duration_s == pytest.approx(KEEP_S + 0.6 + 0.3 + target.tail_s, abs=0.04)
    assert out.lufs is not None and out.lufs == pytest.approx(target.lufs, abs=1.0)
    with wave.open(io.BytesIO(out.data)) as w:
        frames = w.readframes(w.getnframes())
    last = struct.unpack(f"<{int(0.1 * 48000)}h", frames[-int(0.1 * 48000) * 2 :])
    assert max(abs(s) for s in last) == 0  # it ends on silence, not mid-sound
