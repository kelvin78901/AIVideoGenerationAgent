from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from drama_series_agent.api.app import create_app
from drama_series_agent.core.paths import database_path


def test_lifespan_migrates_and_starts_queue(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DRAMA_SERIES_ROOT", str(tmp_path / "workspace"))
    assert not database_path().exists()
    with TestClient(create_app()) as client:
        assert database_path().exists()
        state = client.app.state.studio  # type: ignore[attr-defined]
        assert state.jobs._dispatcher is not None
        # upstream routes stay mounted under /api, unchanged
        assert client.get("/api/series/conversations").status_code == 200
        assert client.get("/api/v1/health").json()["status"] == "ok"
    assert state.jobs._dispatcher is None  # stopped on shutdown


def test_openapi_lists_studio_routes() -> None:
    with TestClient(create_app()) as client:
        paths = client.get("/openapi.json").json()["paths"]
    for path in (
        "/api/v1/health",
        "/api/v1/events",
        "/api/v1/jobs",
        "/api/v1/jobs/{job_id}/cancel",
        "/api/v1/jobs/{job_id}/confirm",
        "/api/v1/providers",
        "/api/v1/providers/{provider_id}/key",
        "/api/v1/providers/{provider_id}/test",
        "/api/v1/dev/llm-test",
        "/api/v1/dev/model-calls",
    ):
        assert path in paths


def test_cli_entry_points_build_the_factory_app() -> None:
    import inspect

    from drama_series_agent import cli, studio_cli

    assert "create_app" in inspect.getsource(cli.run_api_main)
    assert "create_app" in inspect.getsource(studio_cli)
