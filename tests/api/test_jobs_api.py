from __future__ import annotations

import asyncio
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from drama_series_agent.api.app import create_app
from drama_series_agent.api.state import StudioState

LOCAL = "http://127.0.0.1"
CLIENT_HEADERS = {"X-Drama-Studio": "1"}  # required on non-GET requests


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(), base_url=LOCAL, headers=CLIENT_HEADERS) as c:
        yield c


def _state(client: TestClient) -> StudioState:
    state: StudioState = client.app.state.studio  # type: ignore[attr-defined]
    return state


def _enqueue(client: TestClient, **kwargs: object) -> str:
    async def go() -> str:
        job = await _state(client).jobs.enqueue("unregistered", "cpu", **kwargs)  # type: ignore[arg-type]
        return job.id

    return client.portal.call(go)  # type: ignore[union-attr,arg-type]


def test_list_and_get(client: TestClient) -> None:
    job_id = _enqueue(client, wait_for_confirm=True)
    rows = client.get("/api/v1/jobs").json()
    assert [r["id"] for r in rows] == [job_id]
    assert rows[0]["state"] == "waiting_confirm"
    assert client.get(f"/api/v1/jobs/{job_id}").json()["kind"] == "unregistered"
    assert client.get("/api/v1/jobs", params={"state": "waiting_confirm"}).json()[0]["id"] == job_id
    assert client.get("/api/v1/jobs", params={"state": "succeeded"}).json() == []


def test_get_missing_and_bad_state(client: TestClient) -> None:
    resp = client.get("/api/v1/jobs/nope")
    assert resp.status_code == 404
    assert resp.json()["detail"] == {"code": "job_not_found", "params": {"id": "nope"}}
    assert client.get("/api/v1/jobs", params={"state": "weird"}).status_code == 422


def test_cancel_and_confirm(client: TestClient) -> None:
    job_id = _enqueue(client, wait_for_confirm=True)
    resp = client.post(f"/api/v1/jobs/{job_id}/cancel")
    assert resp.status_code == 200 and resp.json()["state"] == "canceled"
    again = client.post(f"/api/v1/jobs/{job_id}/cancel")
    assert again.status_code == 409
    assert again.json()["detail"]["code"] == "job_invalid_state"
    assert client.post(f"/api/v1/jobs/{job_id}/confirm").status_code == 409
    assert client.post("/api/v1/jobs/nope/confirm").status_code == 404
    assert client.post("/api/v1/jobs/nope/cancel").status_code == 404


def test_confirm_moves_to_queue(client: TestClient) -> None:
    job_id = _enqueue(client, wait_for_confirm=True)
    resp = client.post(f"/api/v1/jobs/{job_id}/confirm")
    assert resp.status_code == 200
    assert resp.json()["state"] == "queued"

    async def wait_failed() -> str:
        for _ in range(200):
            job = await _state(client).jobs.get(job_id)
            if job and job.state == "failed":
                return job.state
            await asyncio.sleep(0.02)
        return "timeout"

    # nothing handles "unregistered", so the dispatcher fails it with no_handler
    assert client.portal.call(wait_failed) == "failed"  # type: ignore[union-attr,arg-type]
