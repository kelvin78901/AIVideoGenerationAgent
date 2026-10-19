"""``web/src/test/data/{setup,config}.json``: what the Mock backend answers.

The front end's page tests serve these through their fake backend
(``web/src/test/setupBackend.ts``), so they see the items, codes and change lists this backend
sends. When a
test here fails, the backend's answers changed: regenerate the file with

    DRAMA_UPDATE_FIXTURES=1 uv run pytest tests/api/test_web_fixtures.py

and let the page tests show what that changes on screen.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from drama_series_agent.api.app import create_app
from drama_series_agent.core.paths import REPO_ROOT
from drama_series_agent.setup.installer import FAKE_FAILING_ITEM

LOCAL = "http://127.0.0.1"
V1 = "/api/v1"
FIXTURE = REPO_ROOT / "web" / "src" / "test" / "data" / "setup.json"
# Timestamps and ids differ on every run; the fixture keeps fixed ones.
FIXED_TIME = "2026-10-18T09:00:00Z"


@pytest.fixture(autouse=True)
def _fast_demo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DRAMA_SETUP_FAKE_DELAY_MS", "0")
    monkeypatch.setenv("DRAMA_SETUP_FAKE_TICK_MS", "0")


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(), base_url=LOCAL, headers={"X-Drama-Studio": "1"}) as c:
        yield c


def _wait(client: TestClient, phase: str, limit_s: float = 15) -> dict[str, Any]:
    deadline = time.monotonic() + limit_s
    while time.monotonic() < deadline:
        p: dict[str, Any] = client.get(f"{V1}/setup/profile").json()
        if p["phase"] == phase:
            return p
        time.sleep(0.02)
    raise AssertionError(f"setup never reached {phase}")


def _fixed(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: FIXED_TIME if k.endswith("_at") and v is not None else _fixed(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_fixed(v) for v in value]
    return value


def _machine(client: TestClient, machine: str) -> dict[str, Any]:
    idle = client.post(f"{V1}/dev/setup/machine", json={"machine": machine}).json()
    client.post(f"{V1}/setup/scan")
    scanned = _wait(client, "scanned")
    everything = [x["id"] for x in scanned["items"] if x["installable"]]
    body = {"items": everything, "mirror": "auto", "dir": scanned["default_dir"]}
    started = client.post(f"{V1}/setup/install", json=body).json()
    client.post(f"{V1}/setup/install/cancel")
    return _fixed(
        {
            "idle": idle,
            "scanned": scanned,
            # Installing every installable item: the order, and what needs a yes first (a
            # smaller selection gets the lines whose ``params.item`` it has).
            "install": {
                "order": started["install"]["items"],
                "confirm": started["install"]["confirm"],
            },
            "comfy": client.get(f"{V1}/comfy/env").json(),
        }
    )


def _export(client: TestClient) -> dict[str, Any]:
    return {
        "failing": {"item": FAKE_FAILING_ITEM, "pct": 60, "error": "no_wheel"},
        "pc": _machine(client, "pc"),
        "mac": _machine(client, "mac"),
    }


def test_web_setup_fixture_is_current(client: TestClient) -> None:
    text = json.dumps(_export(client), ensure_ascii=False, indent=2) + "\n"
    if os.environ.get("DRAMA_UPDATE_FIXTURES") == "1":
        FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        with open(FIXTURE, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    current = FIXTURE.read_text(encoding="utf-8") if FIXTURE.exists() else ""
    assert current == text, f"{FIXTURE.name} is out of date: see this module's docstring"


CONFIG_FIXTURE = REPO_ROOT / "web" / "src" / "test" / "data" / "config.json"


def _config_export(client: TestClient) -> dict[str, Any]:
    """The component catalog and every preset's layer per component (``test/fakes/config.ts``).

    Taken before any scan, so nothing is filtered by the machine.
    """
    catalog = client.get(f"{V1}/config/components").json()
    presets: dict[str, dict[str, Any]] = {}
    for preset in ("quality", "balanced", "cheap", "local"):
        client.put(f"{V1}/config/defaults", json={"preset": preset, "fallback_notify": "after"})
        presets[preset] = {
            c["id"]: client.get(f"{V1}/config/resolve", params={"component": c["id"]}).json()[
                "values"
            ]
            for c in catalog["components"]
        }
    client.put(f"{V1}/config/defaults", json={"preset": "balanced"})
    return {"catalog": catalog, "presets": presets}


def test_web_config_fixture_is_current(client: TestClient) -> None:
    text = json.dumps(_config_export(client), ensure_ascii=False, indent=2) + "\n"
    if os.environ.get("DRAMA_UPDATE_FIXTURES") == "1":
        with open(CONFIG_FIXTURE, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    current = CONFIG_FIXTURE.read_text(encoding="utf-8") if CONFIG_FIXTURE.exists() else ""
    assert current == text, f"{CONFIG_FIXTURE.name} is out of date: see this module's docstring"
