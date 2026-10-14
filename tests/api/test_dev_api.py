from __future__ import annotations

import time
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from drama_series_agent.api.app import create_app

LOCAL = "http://127.0.0.1"
CLIENT_HEADERS = {"X-Drama-Studio": "1"}  # required on non-GET requests


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(), base_url=LOCAL, headers=CLIENT_HEADERS) as c:
        yield c


def _wait_state(
    client: TestClient, job_id: str, state: str, limit_s: float = 10
) -> dict[str, object]:
    deadline = time.monotonic() + limit_s
    while time.monotonic() < deadline:
        job: dict[str, object] = client.get(f"/api/v1/jobs/{job_id}").json()
        if job["state"] == state:
            return job
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} never reached {state}")


def test_llm_test_job_runs_and_records_model_call(client: TestClient) -> None:
    assert client.get("/api/v1/dev/model-calls").json() == []
    resp = client.post("/api/v1/dev/llm-test", json={"delay_s": 0.1})
    assert resp.status_code == 200
    job = resp.json()
    assert job["queue"] == "api:deepseek" and job["state"] == "queued"
    done = _wait_state(client, job["id"], "succeeded")
    result = done["result"]
    assert isinstance(result, dict) and result["model_key"] == "deepseek/v4-pro"
    calls = client.get("/api/v1/dev/model-calls").json()
    assert len(calls) == 1
    assert calls[0]["job_id"] == job["id"] and calls[0]["status"] == "success"
    assert calls[0]["cost_usd"] > 0


def test_llm_test_rejects_unknown_component(client: TestClient) -> None:
    resp = client.post("/api/v1/dev/llm-test", json={"component_id": "nope"})
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "unknown_component"


def test_llm_test_refused_outside_mock_mode(client: TestClient) -> None:
    client.app.state.studio.registry.mock = False  # type: ignore[attr-defined]
    resp = client.post("/api/v1/dev/llm-test", json={})
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "mock_only"
