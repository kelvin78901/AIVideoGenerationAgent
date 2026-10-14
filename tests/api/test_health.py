from __future__ import annotations

from fastapi.testclient import TestClient

from drama_series_agent.api.app import create_app

LOCAL = "http://127.0.0.1"


def test_health_reports_mock_mode() -> None:
    with TestClient(create_app(), base_url=LOCAL) as client:
        resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "version": "0.1.0", "mock": True}


def test_unknown_v1_route_is_404() -> None:
    with TestClient(create_app(), base_url=LOCAL) as client:
        assert client.get("/api/v1/nope").status_code == 404


def test_cors_rejects_foreign_origin() -> None:
    with TestClient(create_app(), base_url=LOCAL) as client:
        resp = client.get("/api/v1/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in resp.headers
