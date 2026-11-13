"""局部修复's mask (M5.5 step 14, ``media/image.py``): the painted picture made the picture's
size and black or white, in ComfyUI's form (grayscale, white = change) and OpenAI's (RGBA,
transparent = change)."""

from __future__ import annotations

import asyncio
import struct
import subprocess
import zlib

import pytest

from drama_series_agent.media.audio import ffmpeg_exe
from drama_series_agent.media.image import BadMask, as_png, image_info, mask_for, png


def _pixels(data: bytes) -> tuple[int, int, int, bytes]:
    """Width, height, channels and rows (filter bytes dropped) of a PNG ``png()`` wrote."""
    w, h, _, color = struct.unpack(">IIBB", data[16:26])
    channels = {0: 1, 6: 4}[color]
    pos, idat = 8, b""
    while pos < len(data):
        (n,) = struct.unpack(">I", data[pos : pos + 4])
        if data[pos + 4 : pos + 8] == b"IDAT":
            idat += data[pos + 8 : pos + 8 + n]
        pos += 12 + n
    raw = zlib.decompress(idat)
    stride = w * channels
    rows = b"".join(raw[y * (stride + 1) + 1 : (y + 1) * (stride + 1)] for y in range(h))
    return w, h, channels, rows


def _top_half_white(w: int, h: int) -> bytes:
    return png(b"\xff" * (w * h // 2) + b"\x00" * (w * h // 2), w, h, channels=1)


async def test_a_mask_at_the_pictures_size_in_both_forms() -> None:
    made = await mask_for(_top_half_white(20, 40), 40, 80)  # half the size, same shape
    w, h, channels, gray = _pixels(made.gray)
    assert (w, h, channels) == (40, 80, 1)
    assert set(gray[: 40 * 40]) == {255} and set(gray[40 * 40 :]) == {0}
    w, h, channels, rgba = _pixels(made.alpha)
    assert (w, h, channels) == (40, 80, 4)
    alpha = rgba[3::4]
    assert set(alpha[: 40 * 40]) == {0} and set(alpha[40 * 40 :]) == {255}  # painted: clear
    assert set(rgba[0::4]) == {0}  # black everywhere
    assert made.share == pytest.approx(0.5)


async def test_strokes_on_a_transparent_layer_count_as_painted() -> None:
    """What a canvas exports: white strokes, the rest transparent (whatever its colour)."""
    w, h = 16, 16
    rows = bytearray()
    for y in range(h):
        for _ in range(w):
            rows += b"\xff\xff\xff\xff" if y < 4 else b"\xff\xff\xff\x00"
    made = await mask_for(png(bytes(rows), w, h, channels=4), w, h)
    _, _, _, gray = _pixels(made.gray)
    assert set(gray[: 4 * w]) == {255} and set(gray[4 * w :]) == {0}
    assert made.share == pytest.approx(0.25)


async def test_masks_refused() -> None:
    with pytest.raises(BadMask, match="nothing is painted"):
        await mask_for(png(b"\x00" * 64, 8, 8, channels=1), 8, 8)
    with pytest.raises(BadMask, match="shape"):
        await mask_for(_top_half_white(20, 40), 40, 40)


async def test_a_picture_as_png() -> None:
    gray = png(b"\x80" * 64, 8, 8, channels=1)
    assert await as_png(gray) is gray
    jpeg = await _jpeg()
    out = await as_png(jpeg)
    info = image_info(out)
    assert (info.mime, info.w, info.h) == ("image/png", 8, 8)


async def _jpeg() -> bytes:
    cmd = [
        ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
        "color=c=red:s=8x8", "-frames:v", "1", "-f", "image2pipe", "-c:v", "mjpeg", "pipe:1",
    ]  # fmt: skip
    done = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, check=True)
    return done.stdout
