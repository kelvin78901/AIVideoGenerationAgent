"""What a picture is, from its first bytes (M3 uploads): type and size, without an image library.

PNG (``IHDR``), JPEG (the first ``SOFn`` marker) and WebP (``VP8 ``, ``VP8L``, ``VP8X``) cover
what people upload as a reference and what the image models return.

An uploaded keyframe (M5.5 step 10) is cut to the frame: ``frame_rect`` is the largest box of
the output spec's aspect inside the user's rectangle (the whole picture without one, centred),
``fit`` crops it and scales it to the delivery size with FFmpeg (``crop`` + ``scale``), as PNG.
"""

from __future__ import annotations

import asyncio
import struct
import subprocess
from dataclasses import dataclass

from drama_series_agent.media.audio import ffmpeg_exe

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
# JPEG start-of-frame markers (not DHT 0xC4, JPG 0xC8, DAC 0xCC).
_SOF = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}


@dataclass(frozen=True)
class ImageInfo:
    mime: str
    w: int
    h: int


class NotAnImage(ValueError):
    pass


def image_info(data: bytes) -> ImageInfo:
    """Type and size of a PNG, JPEG or WebP; ``NotAnImage`` for anything else."""
    if data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR":
        w, h = struct.unpack(">II", data[16:24])
        return _checked("image/png", w, h)
    if data[:3] == b"\xff\xd8\xff":
        return _jpeg(data)
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return _webp(data)
    raise NotAnImage("unsupported image type")


def _checked(mime: str, w: int, h: int) -> ImageInfo:
    if w <= 0 or h <= 0:
        raise NotAnImage("empty image")
    return ImageInfo(mime, w, h)


def _jpeg(data: bytes) -> ImageInfo:
    pos = 2
    while pos + 4 <= len(data):
        if data[pos] != 0xFF:
            raise NotAnImage("broken JPEG")
        marker = data[pos + 1]
        if marker == 0xFF:  # fill byte
            pos += 1
            continue
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:  # no length
            pos += 2
            continue
        (length,) = struct.unpack(">H", data[pos + 2 : pos + 4])
        if marker in _SOF and pos + 9 <= len(data):
            h, w = struct.unpack(">HH", data[pos + 5 : pos + 9])
            return _checked("image/jpeg", w, h)
        pos += 2 + length
    raise NotAnImage("JPEG without a frame header")


def _webp(data: bytes) -> ImageInfo:
    chunk = data[12:16]
    if chunk == b"VP8 " and data[23:26] == b"\x9d\x01\x2a":
        w, h = struct.unpack("<HH", data[26:30])
        return _checked("image/webp", w & 0x3FFF, h & 0x3FFF)
    if chunk == b"VP8L" and data[20:21] == b"\x2f":
        bits = int.from_bytes(data[21:25], "little")
        return _checked("image/webp", (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1)
    if chunk == b"VP8X":
        w = int.from_bytes(data[24:27], "little") + 1
        h = int.from_bytes(data[27:30], "little") + 1
        return _checked("image/webp", w, h)
    raise NotAnImage("unsupported WebP")


@dataclass(frozen=True)
class Rect:
    """A box on a picture, in its pixels."""

    x: int
    y: int
    w: int
    h: int


class BadCrop(ValueError):
    pass


def frame_rect(src_w: int, src_h: int, w: int, h: int, box: Rect | None = None) -> Rect:
    """The largest ``w``:``h`` box centred in ``box`` (the whole picture without one);
    ``BadCrop`` when ``box`` is empty or not on the picture."""
    box = box or Rect(0, 0, src_w, src_h)
    if box.w <= 0 or box.h <= 0 or box.x < 0 or box.y < 0:
        raise BadCrop("empty box")
    if box.x + box.w > src_w or box.y + box.h > src_h:
        raise BadCrop("box outside the picture")
    if box.w * h > box.h * w:  # wider than the frame: full height
        cw, ch = max(1, box.h * w // h), box.h
    else:
        cw, ch = box.w, max(1, box.w * h // w)
    return Rect(box.x + (box.w - cw) // 2, box.y + (box.h - ch) // 2, cw, ch)


def _fit(data: bytes, crop: Rect, w: int, h: int) -> bytes:
    cmd = [
        ffmpeg_exe(),
        "-hide_banner",
        "-nostdin",
        "-loglevel",
        "error",
        "-i",
        "pipe:0",
        "-vf",
        f"crop={crop.w}:{crop.h}:{crop.x}:{crop.y},scale={w}:{h}:flags=lanczos",
        "-frames:v",
        "1",
        "-f",
        "image2pipe",
        "-c:v",
        "png",
        "pipe:1",
    ]
    try:
        done = subprocess.run(cmd, input=data, capture_output=True, check=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        raise NotAnImage("FFmpeg could not read it") from exc
    if not done.stdout:
        raise NotAnImage("FFmpeg wrote nothing")
    return done.stdout


async def fit(data: bytes, crop: Rect, w: int, h: int) -> bytes:
    """``crop`` of the picture scaled to ``w`` × ``h``, as PNG."""
    return await asyncio.to_thread(_fit, data, crop, w, h)
