from __future__ import annotations

from fastapi.testclient import TestClient

from drama_series_agent.api.app import create_app


def test_health_ok() -> None:
    client = TestClient(create_app())
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_unknown_v1_route_is_404() -> None:
    client = TestClient(create_app())
    assert client.get("/api/v1/nope").status_code == 404


def test_cors_rejects_foreign_origin() -> None:
    client = TestClient(create_app())
    resp = client.get("/api/v1/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in resp.headers
