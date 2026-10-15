"""API keys: OS keyring first, environment / ``.env`` as a fallback (hard rule 3).

Keys never go into the database, logs, API responses or the front end. ``redact()`` scrubs
anything that looks like a credential, plus every key value this process has loaded.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Literal

import keyring
from keyring.errors import KeyringError, PasswordDeleteError
from loguru import logger

from drama_series_agent.core.paths import REPO_ROOT

SERVICE = "drama-studio"
Source = Literal["keyring", "env", "none"]

_known_values: set[str] = set()

_PATTERNS = [
    re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s\"',]+"),
    re.compile(r"(?i)((?:api[_-]?key|x-api-key|secret|token)[\"']?\s*[:=]\s*[\"']?)[^\s\"',}]+"),
    re.compile(r"\b(sk-)[A-Za-z0-9_\-]{8,}"),
]


class SecretStoreError(Exception):
    pass


def _remember(value: str | None) -> str | None:
    if value and len(value) >= 6:
        _known_values.add(value)
    return value


def _dotenv(path: Path | None = None) -> dict[str, str]:
    override = os.environ.get("DRAMA_ENV_FILE")  # tests point this at an empty location
    env_file = path or (Path(override) if override else REPO_ROOT / ".env")
    if not env_file.is_file():
        return {}
    values: dict[str, str] = {}
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        values[name.strip()] = value.strip().strip('"').strip("'")
    return values


def lookup(key_name: str) -> tuple[str | None, Source]:
    try:
        value = keyring.get_password(SERVICE, key_name)
    except KeyringError as exc:
        logger.warning("keyring unavailable ({}); falling back to environment", type(exc).__name__)
        value = None
    if value:
        return _remember(value), "keyring"
    value = os.environ.get(key_name) or _dotenv().get(key_name)
    if value:
        return _remember(value), "env"
    return None, "none"


def get_secret(key_name: str) -> str | None:
    return lookup(key_name)[0]


def has_secret(key_name: str) -> Source:
    return lookup(key_name)[1]


def set_secret(key_name: str, value: str) -> None:
    value = value.strip()
    if not value:
        raise ValueError("empty key")
    try:
        keyring.set_password(SERVICE, key_name, value)
    except KeyringError as exc:
        raise SecretStoreError(type(exc).__name__) from exc
    _remember(value)


def delete_secret(key_name: str) -> None:
    try:
        keyring.delete_password(SERVICE, key_name)
    except PasswordDeleteError:
        pass
    except KeyringError as exc:
        raise SecretStoreError(type(exc).__name__) from exc


def redact(text: str) -> str:
    for value in _known_values:
        text = text.replace(value, "***")
    for pattern in _PATTERNS:
        text = pattern.sub(lambda m: m.group(1) + "***", text)
    return text


def _patch_record(record: Any) -> None:
    record["message"] = redact(record["message"])


def install_log_redaction() -> None:
    """Scrub credentials from every loguru message (upstream code logs through loguru too)."""
    logger.configure(patcher=_patch_record)
