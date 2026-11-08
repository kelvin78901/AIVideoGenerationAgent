"""Inputs sent inline (data URIs) to the task APIs, made small (M5 step 15, 2026-11-08).

The video APIs (MiniMax H3, Seedance) take pictures and audio as data URIs in the task's JSON.
From a slow uplink (abroad to China: about 20 KB/s measured) a body of PNGs and WAVs (several
MB) does not get through: the task's POST timed out. So a picture over ``PICTURE_OVER`` goes as
a JPEG (quality ~90; the models read pictures as JPEG anyway), audio over ``AUDIO_OVER`` as an
MP3, whichever is smaller; and a create request's write timeout grows with its body
(``upload_timeout``, at ``UPLINK_BPS``).
"""

from __future__ import annotations

import subprocess

import httpx

from drama_series_agent.media.audio import ffmpeg_exe

PICTURE_OVER = 256 * 1024
AUDIO_OVER = 512 * 1024
UPLINK_BPS = 16 * 1024  # a slow uplink, bytes per second: the write timeout's floor rate


def _ffmpeg(data: bytes, *args: str) -> bytes | None:
    cmd = [ffmpeg_exe(), "-hide_banner", "-nostdin", "-loglevel", "error", "-i", "pipe:0", *args]
    try:
        done = subprocess.run(cmd, input=data, capture_output=True, check=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout or None


def compact_picture(data: bytes, mime: str) -> tuple[bytes, str]:
    """A PNG / WebP over ``PICTURE_OVER`` as a JPEG, when that is smaller."""
    if mime == "image/jpeg" or len(data) <= PICTURE_OVER:
        return data, mime
    out = _ffmpeg(data, "-frames:v", "1", "-q:v", "3", "-f", "mjpeg", "pipe:1")
    return (out, "image/jpeg") if out and len(out) < len(data) else (data, mime)


def compact_audio(data: bytes, mime: str) -> tuple[bytes, str]:
    """Audio over ``AUDIO_OVER`` as a 192 kbps MP3, when that is smaller."""
    if mime == "audio/mpeg" or len(data) <= AUDIO_OVER:
        return data, mime
    out = _ffmpeg(data, "-vn", "-c:a", "libmp3lame", "-b:a", "192k", "-f", "mp3", "pipe:1")
    return (out, "audio/mpeg") if out and len(out) < len(data) else (data, mime)


def upload_timeout(body_bytes: int, base_s: float) -> httpx.Timeout:
    """The usual timeouts, but writing the body may take as long as the slow uplink needs."""
    return httpx.Timeout(base_s, write=max(base_s, body_bytes / UPLINK_BPS + 30))
