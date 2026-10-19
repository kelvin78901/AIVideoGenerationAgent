"""Content hashes for versions and dependency slices: sha256 of canonical JSON."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(value: Any) -> str:
    """Sorted keys, no whitespace, UTF-8 kept: the same data always gives the same text."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def hash_json(value: Any) -> str:
    digest = hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def content_hash(payload: dict[str, Any], files: list[dict[str, Any]]) -> str:
    """A version's hash: its payload plus the content of its files (not their paths).

    The prompt that was sent (role ``prompt``) is a record of how it was made, not content.
    """
    shas = sorted(str(f.get("sha256")) for f in files if f.get("role") != "prompt")
    return hash_json({"payload": payload, "files": shas})
