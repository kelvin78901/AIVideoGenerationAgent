"""Video takes (M5): probe, trim the head, first and last frames (``media/video.py``)."""

from __future__ import annotations

import pytest

from drama_series_agent.media.image import image_info
from drama_series_agent.media.video import VideoError, frame, probe, trim_head
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
    assert (cut.w, cut.h, cut.has_audio) == (160, 288, True)


async def test_a_clip_too_short_to_trim_says_so() -> None:
    with pytest.raises(VideoError) as err:
        await trim_head(await solid_mp4(160, 288, 0.3, 24, "336699"))
    assert err.value.code == "video_too_short"


async def test_first_and_last_frames_are_pngs_of_the_clip_size() -> None:
    clip = await solid_mp4(160, 288, 1.0, 24, "336699")
    for which in ("first", "last"):
        info = image_info(await frame(clip, which))
        assert (info.mime, info.w, info.h) == ("image/png", 160, 288)


async def test_not_a_video() -> None:
    with pytest.raises(VideoError) as err:
        await probe(b"not a video at all")
    assert err.value.code in {"video_unreadable", "video_ffmpeg_failed"}
