"""``media/image.py``: type and size of an uploaded picture from its header (M3 step 3)."""

from __future__ import annotations

import struct

import pytest

from drama_series_agent.media.image import NotAnImage, image_info
from drama_series_agent.modelhub.adapters.mock import gradient_png


def _jpeg(w: int, h: int) -> bytes:
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    sof = b"\xff\xc0" + struct.pack(">HBHHB", 11, 8, h, w, 1) + b"\x01\x11\x00"
    return b"\xff\xd8" + app0 + sof + b"\xff\xd9"


def _webp(chunk: bytes, body: bytes) -> bytes:
    data = chunk + struct.pack("<I", len(body)) + body
    return b"RIFF" + struct.pack("<I", len(data) + 4) + b"WEBP" + data


def test_png() -> None:
    info = image_info(gradient_png(60, 100, (1, 2, 3)))
    assert (info.mime, info.w, info.h) == ("image/png", 60, 100)


def test_jpeg() -> None:
    info = image_info(_jpeg(1080, 1920))
    assert (info.mime, info.w, info.h) == ("image/jpeg", 1080, 1920)


def test_webp_lossy_lossless_extended() -> None:
    lossy = b"\x00\x00\x00" + b"\x9d\x01\x2a" + struct.pack("<HH", 640, 480)
    assert (image_info(_webp(b"VP8 ", lossy)).w, image_info(_webp(b"VP8 ", lossy)).h) == (640, 480)
    bits = (300 - 1) | ((200 - 1) << 14)
    lossless = b"\x2f" + bits.to_bytes(4, "little")
    info = image_info(_webp(b"VP8L", lossless))
    assert (info.mime, info.w, info.h) == ("image/webp", 300, 200)
    extended = b"\x00\x00\x00\x00" + (1023).to_bytes(3, "little") + (767).to_bytes(3, "little")
    info = image_info(_webp(b"VP8X", extended))
    assert (info.w, info.h) == (1024, 768)


@pytest.mark.parametrize(
    "data", [b"", b"hello", b"GIF89a....", b"\xff\xd8\xff\xd9", b"RIFF\x00\x00\x00\x00WAVE"]
)
def test_not_a_picture(data: bytes) -> None:
    with pytest.raises(NotAnImage):
        image_info(data)
