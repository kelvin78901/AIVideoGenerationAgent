"""Files of versions (M3): ``GET /files/{sha256}`` serves a blob by its content hash.

Pictures and audio of candidates, picks and line audio are blobs (``core/storage.py``); the
front end shows them from here. The type comes from the file's first bytes (the store keeps no
metadata). Range requests work, so an audio player can seek. Only a 64-character hex hash is
accepted, so nothing outside the blob store can be named.
"""

from __future__ import annotations

import re
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from drama_series_agent.api.errors import ApiError
from drama_series_agent.api.state import StudioState, get_state

router = APIRouter(tags=["files"])

State = Annotated[StudioState, Depends(get_state)]

_SHA = re.compile(r"^[0-9a-f]{64}$")
# (offset, magic bytes, mime): enough for what models and the user produce.
_MAGIC: tuple[tuple[int, bytes, str], ...] = (
    (0, b"\x89PNG\r\n\x1a\n", "image/png"),
    (0, b"\xff\xd8\xff", "image/jpeg"),
    (0, b"GIF8", "image/gif"),
    (8, b"WEBP", "image/webp"),
    (8, b"WAVE", "audio/wav"),
    (0, b"ID3", "audio/mpeg"),
    (0, b"\xff\xfb", "audio/mpeg"),
    (0, b"\xff\xf3", "audio/mpeg"),
    (0, b"fLaC", "audio/flac"),
    (0, b"OggS", "audio/ogg"),
    (4, b"ftyp", "video/mp4"),
)


def sniff(head: bytes) -> str:
    for offset, magic, mime in _MAGIC:
        if head[offset : offset + len(magic)] == magic:
            return mime
    try:
        head.decode("utf-8")
    except UnicodeDecodeError:
        return "application/octet-stream"
    return "text/plain; charset=utf-8"


@router.get("/files/{sha256}")
async def get_file(sha256: str, state: State) -> FileResponse:
    """A blob by content hash; immutable, so the browser may cache it for good."""
    if not _SHA.match(sha256):
        raise ApiError(404, "file_not_found", sha256=sha256[:80])
    path = state.store.path_for(sha256)
    if not path.is_file():
        raise ApiError(404, "file_not_found", sha256=sha256)
    with path.open("rb") as fh:
        head = fh.read(16)
    return FileResponse(
        path,
        media_type=sniff(head),
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )
