"""Video takes (M5): probe, trim the head, first and last frames, the tail clip
(``media/video.py``)."""

from __future__ import annotations

from pathlib import Path

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


def test_the_tail_clip_keeps_the_frames_as_they_were_and_less_of_the_sound() -> None:
    """M5 step 15m: lossless, so the tail's last frame is the source's last frame exactly; its
    sound may stop after ``audio_frames``."""
    import asyncio
    import subprocess
    from tempfile import TemporaryDirectory

    from drama_series_agent.media.audio import ffmpeg_exe

    def ff(*args: str) -> bytes:
        return subprocess.run([ffmpeg_exe(), "-hide_banner", "-nostdin", *args],
                              capture_output=True, check=True).stdout  # fmt: skip

    def last_frame(path: Path) -> bytes:
        return ff("-loglevel", "error", "-sseof", "-0.2", "-i", str(path), "-update", "1",
                  "-f", "rawvideo", "-pix_fmt", "yuv420p", "-")[-160 * 288 * 3 // 2 :]  # fmt: skip

    with TemporaryDirectory() as tmp:
        src, out = Path(tmp) / "src.mp4", Path(tmp) / "tail.mp4"
        ff("-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=160x288:rate=24:duration=2",
           "-f", "lavfi", "-i", "sine=f=440:d=2", "-pix_fmt", "yuv420p", "-c:a", "aac",
           "-shortest", str(src))  # fmt: skip
        out.write_bytes(asyncio.run(tail_clip(src.read_bytes(), 22, 24.0, audio_frames=18)))
        assert last_frame(out) == last_frame(src)
        probe_text = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", str(out)],
                                    capture_output=True, text=True).stderr  # fmt: skip
        assert "alac" in probe_text
        pcm = ff("-loglevel", "error", "-i", str(out), "-map", "0:a", "-ac", "1", "-ar", "16000",
                 "-f", "s16le", "-")  # fmt: skip
        assert len(pcm) / 2 / 16000 == pytest.approx(18 / 24, abs=0.03)


def test_the_usable_window_skips_the_still_opening_and_keeps_the_line() -> None:
    """M5 step 15i: one still second, then motion; a tone at 2.0-2.5 s stands for the line."""
    import asyncio
    import subprocess
    from tempfile import TemporaryDirectory

    from drama_series_agent.media.audio import ffmpeg_exe
    from drama_series_agent.media.video import usable_window

    graph = (
        "color=c=gray:s=160x288:r=24:d=1[still];testsrc2=s=160x288:r=24:d=2[moving];"
        "[still][moving]concat=n=2:v=1:a=0,format=yuv420p[v];"
        "sine=f=440:d=3,volume=enable='between(t,2,2.5)':volume=1,"
        "volume=enable='not(between(t,2,2.5))':volume=0.01[a]"
    )
    with TemporaryDirectory() as tmp:
        src = Path(tmp) / "src.mp4"
        subprocess.run(
            [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-filter_complex", graph,
             "-map", "[v]", "-map", "[a]", "-c:a", "aac", "-t", "3", str(src)],
            check=True,
        )  # fmt: skip
        data = src.read_bytes()
    plain = asyncio.run(usable_window(data, 1.0, spoken=False))
    assert plain.in_s == pytest.approx(1.0, abs=0.1) and plain.out_s == pytest.approx(2.0, abs=0.1)
    line = asyncio.run(usable_window(data, 0.5, spoken=True))
    assert line.in_s == pytest.approx(1.0, abs=0.1)
    assert line.out_s == pytest.approx(2.75, abs=0.1)  # the line and a quarter second after
    # A shot as long as the clip starts at 0, still opening or not.
    assert asyncio.run(usable_window(data, 3.0, spoken=False)).in_s == 0.0


def test_scene_cuts_find_a_change_of_picture() -> None:
    """M5 step 15j: two different pictures one after the other is a cut at 1 s; a still clip
    has none."""
    import asyncio
    import subprocess
    from tempfile import TemporaryDirectory

    from drama_series_agent.media.audio import ffmpeg_exe
    from drama_series_agent.media.video import scene_cuts

    graph = (
        "testsrc2=s=160x288:r=24:d=1[a];color=c=red:s=160x288:r=24:d=1[b];"
        "[a][b]concat=n=2:v=1:a=0,format=yuv420p[v]"
    )
    with TemporaryDirectory() as tmp:
        src = Path(tmp) / "src.mp4"
        subprocess.run(
            [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-filter_complex", graph,
             "-map", "[v]", str(src)],
            check=True,
        )  # fmt: skip
        data = src.read_bytes()
    (cut,) = asyncio.run(scene_cuts(data))
    assert cut == pytest.approx(1.0, abs=0.05)
    still = asyncio.run(solid_mp4(160, 288, 1.0, 24, "336699"))
    assert asyncio.run(scene_cuts(still)) == []


async def test_not_a_video() -> None:
    with pytest.raises(VideoError) as err:
        await probe(b"not a video at all")
    assert err.value.code in {"video_unreadable", "video_ffmpeg_failed"}


async def test_a_contact_sheet_has_six_frames_in_rows_of_three() -> None:
    """take 检查 (M5.5): six frames evenly through the clip on one picture, and when."""
    from drama_series_agent.media.video import SHEET_W, contact_sheet

    clip = await solid_mp4(160, 288, 2.0, 24, "336699")
    png, times = await contact_sheet(clip)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert int.from_bytes(png[16:20], "big") == 3 * SHEET_W
    assert len(times) == 6 and times[0] < times[-1] < 2.0
