from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from drama_series_agent.core.storage import BlobStore


def test_put_bytes_is_content_addressed(tmp_path: Path) -> None:
    store = BlobStore(tmp_path / "blobs")
    sha = store.put_bytes(b"hello")
    assert sha == hashlib.sha256(b"hello").hexdigest()
    path = store.path_for(sha)
    assert path == tmp_path / "blobs" / "sha256" / sha[:2] / sha
    assert store.read_bytes(sha) == b"hello"


def test_duplicate_content_is_stored_once(tmp_path: Path) -> None:
    store = BlobStore(tmp_path / "blobs")
    a = store.put_bytes(b"same")
    mtime = store.path_for(a).stat().st_mtime_ns
    b = store.put_bytes(b"same")
    assert a == b
    assert store.path_for(a).stat().st_mtime_ns == mtime
    files = [p for p in (tmp_path / "blobs").rglob("*") if p.is_file()]
    assert len(files) == 1


def test_put_file_streams_and_matches_bytes(tmp_path: Path) -> None:
    src = tmp_path / "中文 路径" / "clip.bin"
    src.parent.mkdir()
    data = bytes(range(256)) * 9000  # > 1 chunk
    src.write_bytes(data)
    store = BlobStore(tmp_path / "blobs")
    sha = store.put_file(src)
    assert sha == hashlib.sha256(data).hexdigest()
    with store.open(sha) as fh:
        assert fh.read() == data
    assert store.put_bytes(data) == sha


def test_no_temp_files_left_after_failure(tmp_path: Path) -> None:
    store = BlobStore(tmp_path / "blobs")
    target = store.path_for("0" * 64)

    def boom(_out: object) -> None:
        raise RuntimeError("disk full")

    with pytest.raises(RuntimeError):
        store._write_atomic(target, boom)
    assert not target.exists()
    assert list(target.parent.iterdir()) == []


def test_rejects_bad_hash(tmp_path: Path) -> None:
    store = BlobStore(tmp_path)
    with pytest.raises(ValueError):
        store.path_for("../etc/passwd")
    assert not store.exists("a" * 64)


def test_default_root_under_drama_home() -> None:
    store = BlobStore()
    assert store.root.parts[-2:] == ("drama-home", "blobs")
