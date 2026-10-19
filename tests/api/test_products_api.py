"""``/products`` and ``/versions`` (SPEC 9.1): one normal and one error case per route."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from drama_series_agent.api.app import create_app
from drama_series_agent.api.state import StudioState
from drama_series_agent.pipeline.products import VersionDraft

LOCAL = "http://127.0.0.1"
CLIENT_HEADERS = {"X-Drama-Studio": "1"}


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(), base_url=LOCAL, headers=CLIENT_HEADERS) as c:
        yield c


def _state(client: TestClient) -> StudioState:
    state: StudioState = client.app.state.studio  # type: ignore[attr-defined]
    return state


def _code(resp: object) -> str:
    return resp.json()["detail"]["code"]  # type: ignore[attr-defined,no-any-return]


def _product(client: TestClient, versions: int = 2) -> tuple[str, list[str]]:
    """An episodes product on the demo series with ``versions`` runs; returns ids."""
    svc = _state(client).products

    async def make() -> tuple[str, list[str]]:
        p = await svc.ensure(
            series_id="demo",
            owner_type="series",
            owner_id="demo",
            slot="episodes",
            component_id="split",
        )
        ids = []
        for n in range(versions):
            draft = VersionDraft(payload={"n": n + 1}, model_key="deepseek/v4-pro", where="api")
            ids.append((await svc.append(p.id, draft, origin="run" if n == 0 else "rerun")).id)
        return p.id, ids

    return client.portal.call(make)  # type: ignore[union-attr]


def test_list_and_get(client: TestClient) -> None:
    pid, (v1, v2) = _product(client)
    listed = client.get("/api/v1/products", params={"owner": "series:demo", "component": "split"})
    assert [p["id"] for p in listed.json()] == [pid]
    assert client.get("/api/v1/products", params={"component": "script"}).json() == []
    data = client.get(f"/api/v1/products/{pid}").json()
    assert data["status"] == "adopted"
    assert (data["current_version_id"], data["adopted_version_id"]) == (v2, v1)
    assert [v["n"] for v in data["versions"]] == [1, 2]
    v = data["versions"][0]
    assert v["payload"] == {"n": 1} and v["where"] == "api" and v["created_at"].endswith("Z")
    assert data["prompt"] is None and data["estimate"] is None and data["running"] is None

    assert _code(client.get("/api/v1/products/nope")) == "product_not_found"
    resp = client.get("/api/v1/products", params={"owner": "series"})
    assert resp.status_code == 422 and _code(resp) == "invalid_owner"


def test_set_current_and_adopt(client: TestClient) -> None:
    _, (v1, v2) = _product(client)
    data = client.post(f"/api/v1/versions/{v1}/set-current").json()
    assert data["current_version_id"] == v1
    data = client.post(f"/api/v1/versions/{v2}/adopt").json()
    assert (data["current_version_id"], data["adopted_version_id"]) == (v2, v2)
    for action in ("set-current", "adopt"):
        resp = client.post(f"/api/v1/versions/nope/{action}")
        assert resp.status_code == 404 and _code(resp) == "version_not_found"


def test_lock_and_unlock(client: TestClient) -> None:
    pid, (_, v2) = _product(client)
    data = client.post(f"/api/v1/products/{pid}/lock").json()
    assert data["status"] == "locked" and data["locked_hash"].startswith("sha256:")
    resp = client.post(f"/api/v1/versions/{v2}/adopt")
    assert resp.status_code == 409 and _code(resp) == "product_locked"
    data = client.post(f"/api/v1/products/{pid}/unlock").json()
    assert data["status"] == "adopted" and data["locked_hash"] is None

    empty, _ = _product_empty(client)
    resp = client.post(f"/api/v1/products/{empty}/lock")
    assert resp.status_code == 409 and _code(resp) == "nothing_adopted"
    assert _code(client.post("/api/v1/products/nope/unlock")) == "product_not_found"


def _product_empty(client: TestClient) -> tuple[str, list[str]]:
    svc = _state(client).products

    async def make() -> str:
        p = await svc.ensure(
            series_id="demo",
            owner_type="series",
            owner_id="demo",
            slot="test_empty",
            component_id="test",
        )
        return p.id

    return client.portal.call(make), []  # type: ignore[union-attr]
