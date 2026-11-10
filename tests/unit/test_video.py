"""Video takes (M5): probe, trim the head, first and last frames, the tail clip
(``media/video.py``)."""

from __future__ import annotations

import pytest

from drama_series_agent.media.image import image_info
from drama_series_agent.media.video import VideoError, frame, probe, tail_clip, trim_head
from drama_series_agent.modelhub.adapters.mock import solid_mp4


async def test_probe_reads_size_duration_fps_and_sound() -> None:
    silent = await probe(await solid_mp4(160, 288, 2.0, 24, "336699"))
    assert (silent.w, silent.h, silent.fps, silent.has_audio) == (160, 288, 24.0, False)
    assert silent.duration_s == pytest.approx(2.0, abs=0.05)
    loud = await probe(await solid_mp4(160, 288, 2.0, 24, "336699", audio_hz=440))
    assert loud.has_audio


async def test_trim_head_cuts_the_first_0_3_seconds_and_keeps_the_sound() -> None:
    clip = await solid_mp4(160, 288, 2.0, 24, "336699", audio_hz=440)
    cut = await probe(await trim_head(clip))
    assert cut.duration_s == pytest.approx(1.7, abs=0.06)
    assert (cut.w, cut.h, cut.fps, cut.has_audio) == (160, 288, 24.0, True)


def test_trim_head_keeps_every_frame_after_the_cut_once() -> None:
    """22 frames at 24 fps off a clip whose frames all differ: 26 of 48 left, the first of them
    the source's frame 22 (seeking the input re-encoded showed it twice)."""
    import asyncio
    import subprocess
    from pathlib import Path
    from tempfile import TemporaryDirectory

    from drama_series_agent.media.audio import ffmpeg_exe

    def ff(*args: str) -> str:
        done = subprocess.run(
            [ffmpeg_exe(), "-hide_banner", *args], capture_output=True, text=True, check=True
        )
        return done.stderr

    def psnr(a: Path, b: Path, n: int) -> float:
        pick = rf"[0:v]select=eq(n\,0)[x];[1:v]select=eq(n\,{n})[y];[x][y]psnr"
        text = ff("-i", str(a), "-i", str(b), "-filter_complex", pick, "-f", "null", "-")
        return float(text.rsplit("average:", 1)[1].split()[0].replace("inf", "99"))

    with TemporaryDirectory() as tmp:
        src, out = Path(tmp) / "src.mp4", Path(tmp) / "cut.mp4"
        ff("-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=160x288:rate=24:duration=2",
           "-pix_fmt", "yuv420p", str(src))  # fmt: skip
        out.write_bytes(asyncio.run(trim_head(src.read_bytes(), round(22 / 24, 4))))
        counted = ff("-i", str(out), "-map", "0:v", "-f", "null", "-")
        assert int(counted.rsplit("frame=", 1)[1].split()[0]) == 26
        assert psnr(out, src, 22) > psnr(out, src, 21) + 5


async def test_a_clip_too_short_to_trim_says_so() -> None:
    with pytest.raises(VideoError) as err:
        await trim_head(await solid_mp4(160, 288, 0.3, 24, "336699"))
    assert err.value.code == "video_too_short"


async def test_first_and_last_frames_are_pngs_of_the_clip_size() -> None:
    clip = await solid_mp4(160, 288, 1.0, 24, "336699")
    for which in ("first", "last"):
        info = image_info(await frame(clip, which))
        assert (info.mime, info.w, info.h) == ("image/png", 160, 288)


async def test_the_tail_clip_is_the_last_22_frames_with_their_sound() -> None:
    clip = await solid_mp4(160, 288, 3.0, 24, "336699", audio_hz=440)
    tail = await probe(await tail_clip(clip, 22, 24.0))
    assert tail.duration_s == pytest.approx(22 / 24, abs=0.05)
    assert (tail.w, tail.h, tail.fps, tail.has_audio) == (160, 288, 24.0, True)
    with pytest.raises(VideoError) as err:
        await tail_clip(await solid_mp4(160, 288, 0.5, 24, "336699"), 22, 24.0)
    assert err.value.code == "video_too_short"


async def test_not_a_video() -> None:
    with pytest.raises(VideoError) as err:
        await probe(b"not a video at all")
    assert err.value.code in {"video_unreadable", "video_ffmpeg_failed"}
