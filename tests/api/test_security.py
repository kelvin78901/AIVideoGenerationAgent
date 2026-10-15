"""Other web pages must not be able to drive the backend (DNS rebinding, cross-site POSTs)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from drama_series_agent.api.app import create_app
from drama_series_agent.api.security import _hostname

HEADER = {"X-Drama-Studio": "1"}


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(), base_url="http://127.0.0.1:8000") as c:
        yield c


@pytest.mark.parametrize(
    "host", ["127.0.0.1", "127.0.0.1:8000", "localhost:5173", "LOCALHOST", "[::1]:8000"]
)
def test_local_hosts_are_allowed(client: TestClient, host: str) -> None:
    assert client.get("/api/v1/health", headers={"Host": host}).status_code == 200


@pytest.mark.parametrize(
    "host", ["evil.example", "evil.example:8000", "127.0.0.1.evil.example", "192.168.1.5:8000", ""]
)
def test_other_hosts_are_rejected(client: TestClient, host: str) -> None:
    """DNS rebinding: evil.example resolves to 127.0.0.1 but the Host header gives it away."""
    resp = client.get("/api/v1/health", headers={"Host": host})
    assert resp.status_code == 421
    assert resp.json() == {"detail": {"code": "host_not_allowed", "params": {}}}
    # also for the upstream routes and the event stream
    assert client.get("/api/series/conversations", headers={"Host": host}).status_code == 421
    assert client.get("/api/v1/events", headers={"Host": host}).status_code == 421


def test_writes_need_the_client_header(client: TestClient) -> None:
    resp = client.post("/api/v1/dev/llm-test", json={"delay_s": 0})
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "missing_client_header"
    assert (
        client.post("/api/v1/dev/llm-test", json={"delay_s": 0}, headers=HEADER).status_code == 200
    )
    assert client.delete("/api/v1/providers/deepseek/key").status_code == 403
    assert client.post("/api/v1/jobs/x/cancel", headers={"X-Drama-Studio": "0"}).status_code == 403
    # upstream routes are guarded too (e.g. the settings write)
    assert client.put("/api/series/settings", json={}).status_code == 403


def test_cross_site_post_is_rejected_even_with_header(client: TestClient) -> None:
    headers = {**HEADER, "Origin": "https://evil.example"}
    resp = client.post("/api/v1/dev/llm-test", json={}, headers=headers)
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "origin_not_allowed"
    # a plain HTML form post: foreign Origin, no custom header
    form = client.post(
        "/api/v1/providers/deepseek/key",
        data={"api_key": "x"},
        headers={"Origin": "https://evil.example"},
    )
    assert form.status_code == 403


def test_own_front_end_origin_is_allowed(client: TestClient) -> None:
    headers = {**HEADER, "Origin": "http://127.0.0.1:5173"}
    assert client.post("/api/v1/dev/llm-test", json={}, headers=headers).status_code == 200


def test_preflight_only_allows_our_front_end(client: TestClient) -> None:
    ok = client.options(
        "/api/v1/dev/llm-test",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-drama-studio",
        },
    )
    assert ok.status_code == 200
    assert ok.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "x-drama-studio" in ok.headers["access-control-allow-headers"].lower()
    bad = client.options(
        "/api/v1/dev/llm-test",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-drama-studio",
        },
    )
    assert "access-control-allow-origin" not in bad.headers


def test_hostname_parsing() -> None:
    assert _hostname("LocalHost:5173") == "localhost"
    assert _hostname("[::1]:8000") == "[::1]"
    assert _hostname("[::1]") == "[::1]"
    assert _hostname("127.0.0.1") == "127.0.0.1"


def test_extra_loopback_origins_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """The Playwright tests run their own Vite server on another port."""
    monkeypatch.setenv("DRAMA_WEB_ORIGINS", "http://127.0.0.1:5183, http://localhost:5183/")
    with TestClient(create_app(), base_url="http://127.0.0.1:8000") as c:
        headers = {**HEADER, "Origin": "http://127.0.0.1:5183"}
        resp = c.post("/api/v1/dev/llm-test", json={"delay_s": 0}, headers=headers)
        assert resp.status_code == 200
        headers["Origin"] = "http://127.0.0.1:5999"
        assert c.post("/api/v1/dev/llm-test", json={}, headers=headers).status_code == 403


@pytest.mark.parametrize(
    "origin", ["https://127.0.0.1:5183", "http://evil.example:5183", "http://192.168.1.5:5173"]
)
def test_extra_origins_must_be_loopback_http(monkeypatch: pytest.MonkeyPatch, origin: str) -> None:
    monkeypatch.setenv("DRAMA_WEB_ORIGINS", origin)
    with pytest.raises(ValueError, match="not a loopback http origin"):
        create_app()
