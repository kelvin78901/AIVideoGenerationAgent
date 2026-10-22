"""What a picture is, from its first bytes (M3 uploads): type and size, without an image library.

PNG (``IHDR``), JPEG (the first ``SOFn`` marker) and WebP (``VP8 ``, ``VP8L``, ``VP8X``) cover
what people upload as a reference and what the image models return.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

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
