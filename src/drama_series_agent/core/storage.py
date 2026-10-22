"""Content-addressed blob store: ``blobs/sha256/<ab>/<full hash>``.

Images, audio, video and large texts live here; database rows reference them by hash.
Writes go to a temporary file in the same directory and are renamed into place, so a
blob path either does not exist or holds the complete content.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO

from drama_series_agent.core.paths import blobs_dir

_CHUNK = 1024 * 1024
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


class BlobStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or blobs_dir()

    def path_for(self, sha256: str) -> Path:
        if not _HASH_RE.match(sha256):
            raise ValueError(f"not a sha256 hex digest: {sha256!r}")
        return self.root / "sha256" / sha256[:2] / sha256

    @staticmethod
    def relative(sha256: str) -> str:
        """Where a blob lives under the data directory, as a version's ``files[].path``."""
        return f"blobs/sha256/{sha256[:2]}/{sha256}"

    def exists(self, sha256: str) -> bool:
        return self.path_for(sha256).is_file()

    def put_bytes(self, data: bytes) -> str:
        sha = hashlib.sha256(data).hexdigest()
        target = self.path_for(sha)
        if not target.is_file():
            self._write_atomic(target, lambda fh: fh.write(data))
        return sha

    def put_file(self, source: Path) -> str:
        """Copy ``source`` into the store (streamed, so large videos are fine)."""
        digest = hashlib.sha256()
        with source.open("rb") as fh:
            while chunk := fh.read(_CHUNK):
                digest.update(chunk)
        sha = digest.hexdigest()
        target = self.path_for(sha)
        if not target.is_file():

            def copy(out: BinaryIO) -> None:
                with source.open("rb") as src:
                    shutil.copyfileobj(src, out, _CHUNK)

            self._write_atomic(target, copy)
        return sha

    def open(self, sha256: str) -> BinaryIO:
        return self.path_for(sha256).open("rb")

    def read_bytes(self, sha256: str) -> bytes:
        return self.path_for(sha256).read_bytes()

    @staticmethod
    def _write_atomic(target: Path, write: Callable[[BinaryIO], object]) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=".tmp-", dir=target.parent)
        tmp = Path(tmp_name)
        try:
            with os.fdopen(fd, "wb") as out:
                write(out)
                out.flush()
                os.fsync(out.fileno())
            try:
                os.replace(tmp, target)
            except PermissionError:
                # Windows: another writer just placed the same content and a reader holds it open.
                if not target.is_file():
                    raise
        finally:
            tmp.unlink(missing_ok=True)
