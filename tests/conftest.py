"""Shared fixtures: mock adapters, an isolated data dir and an in-memory keyring for every test."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import keyring
import pytest
from keyring.backend import KeyringBackend

from drama_series_agent.core.config import Accounts, Library, set_accounts, set_library
from drama_series_agent.core.db import Database, migrate
from drama_series_agent.core.paths import database_path
from drama_series_agent.studio import demo

SEEDED_GATES = demo.CONFIRMED_GATES


class MemoryKeyring(KeyringBackend):
    priority = 1  # type: ignore[assignment]

    def __init__(self) -> None:
        super().__init__()
        self.store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        self.store.pop((service, username), None)


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("DRAMA_MOCK", "1")
    monkeypatch.setenv("DRAMA_FAST_AUDIO", "1")  # voice samples skip FFmpeg's loudness pass
    monkeypatch.delenv("DRAMA_LIVE", raising=False)
    monkeypatch.setenv("DRAMA_HOME", str(tmp_path / "drama-home"))
    monkeypatch.setenv("DRAMA_ENV_FILE", str(tmp_path / "no.env"))  # never read the real .env
    monkeypatch.setenv("DRAMA_SERIES_ROOT", str(tmp_path / "upstream"))  # upstream config.json etc.
    previous = keyring.get_keyring()
    keyring.set_keyring(MemoryKeyring())
    yield
    keyring.set_keyring(previous)


@pytest.fixture(autouse=True)
def _factory_config() -> Iterator[None]:
    """Each test starts from the factory config: no workflow library or provider accounts
    left by another app."""
    set_library(Library())
    set_accounts(Accounts())
    yield
    set_library(Library())
    set_accounts(Accounts())


@pytest.fixture(autouse=True)
def _demo_gates_open(monkeypatch: pytest.MonkeyPatch) -> None:
    """The Mock demo starts with 小说 and episode 1's 剧本 confirmed; tests edit it directly, so
    by default it is seeded with its gates open. `demo_gates` seeds them as the app does."""
    monkeypatch.setattr(demo, "CONFIRMED_GATES", ())


@pytest.fixture
def demo_gates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(demo, "CONFIRMED_GATES", SEEDED_GATES)


@pytest.fixture
async def studio_db() -> AsyncIterator[Database]:
    """A migrated database under the per-test DRAMA_HOME."""
    path = database_path()
    await asyncio.to_thread(migrate, path)
    db = Database(path)
    yield db
    await db.dispose()
