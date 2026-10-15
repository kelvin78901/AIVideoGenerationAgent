"""Filesystem locations used by the studio."""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def drama_home() -> Path:
    """Per-user data directory (database, blobs, local envs). ``DRAMA_HOME`` overrides it."""
    override = os.environ.get("DRAMA_HOME")
    return Path(override) if override else Path.home() / ".drama-studio"


def config_dir() -> Path:
    """Directory holding the factory-default ``*.yaml`` files. ``DRAMA_CONFIG_DIR`` overrides it."""
    override = os.environ.get("DRAMA_CONFIG_DIR")
    return Path(override) if override else REPO_ROOT / "config"


def database_path() -> Path:
    return drama_home() / "studio.db"


def blobs_dir() -> Path:
    return drama_home() / "blobs"
