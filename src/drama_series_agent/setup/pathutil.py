"""Paths as plain strings for the setup scan: they may name another machine (the samples).

Each helper keeps the separator style the path already uses, so a Windows path read from a
fixture or a config file stays backslashed.
"""

from __future__ import annotations

import posixpath
import re


def join(base: str, *parts: str) -> str:
    """Join with the separator ``base`` already uses (``D:\\ComfyUI`` stays backslashed)."""
    sep = "\\" if "\\" in base and "/" not in base else "/"
    return sep.join([base.rstrip("/\\"), *(p.strip("/\\") for p in parts)])


def dirname(path: str) -> str:
    return re.split(r"[/\\](?=[^/\\]*$)", path.rstrip("/\\"))[0]


def basename(path: str) -> str:
    return re.split(r"[/\\]", path.rstrip("/\\"))[-1]


def is_absolute(path: str) -> bool:
    return path.startswith(("/", "\\", "~")) or bool(re.match(r"^[A-Za-z]:[/\\]", path))


def norm(path: str) -> str:
    """For comparing: forward slashes, ``..`` folded, drive letters and case ignored on Windows."""
    p = posixpath.normpath(path.replace("\\", "/"))
    return p.lower() if re.match(r"^[A-Za-z]:/", p) else p


def same_path(a: str, b: str) -> bool:
    return norm(a) == norm(b)


def inside(path: str, folder: str) -> bool:
    """``path`` is ``folder`` or somewhere under it."""
    p, f = norm(path), norm(folder).rstrip("/")
    return p == f or p.startswith(f + "/")
