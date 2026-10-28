"""Generate page endpoints (M5 step 8): rules, run log, 取消采纳, ratings, the shot cap and the top
bar's ``/metrics/summary``. Mock adapters on the demo series."""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from drama_series_agent.api.app import create_app

LOCAL = "http://127.0.0.1"
V1 = "/api/v1"
EP1 = "demo-e1"
SERIES = "demo"


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(), base_url=LOCAL, headers={"X-Drama-Studio": "1"}) as c:
        yield c


def _shots(client: TestClient) -> dict[str, dict[str, Any]]:
    return {s["label"]: s for s in client.get(f"{V1}/episodes/{EP1}/shots").json()}


def _confirm_storyboard(client: TestClient) -> None:
    for shot in _shots(client).values():
        if not shot["confirmed"]:
            client.patch(f"{V1}/shots/{shot['id']}", json={"confirmed": True}).raise_for_status()
    resp = client.post(f"{V1}/gates/storyboard/confirm", json={"scope_id": EP1})
    assert resp.status_code == 200, resp.text


def _settle(client: TestClient, job: dict[str, Any]) -> dict[str, Any]:
    deadline = time.monotonic() + 60
    while job["state"] in ("queued", "running"):
        assert time.monotonic() < deadline, "the job did not finish"
        time.sleep(0.02)
        job = client.get(f"{V1}/jobs/{job['id']}").json()
    return job


def _run(client: TestClient, product_id: str, **body: Any) -> dict[str, Any]:
    resp = client.post(f"{V1}/products/{product_id}/run", json={"mode": "run", **body})
    assert resp.status_code == 200, resp.text
    return _settle(client, resp.json())


def test_rules_default_to_the_config_and_save_per_series(client: TestClient) -> None:
    sid = SERIES
    rules = client.get(f"{V1}/series/{sid}/generate-rules").json()
    assert rules == {
        "takes_per_shot": 2,  # vid.candidates
        "qa_retry_max": 2,  # fallback_defaults.qa_fail_n
        "shot_cap_usd": 2.0,
        "thresholds": {"face_sim": 0.75, "syncnet_conf": 6.0, "cer_max": 0.1},
    }
    resp = client.put(f"{V1}/series/{sid}/generate-rules", json={"takes_per_shot": 3})
    assert resp.status_code == 200 and resp.json()["takes_per_shot"] == 3
    resp = client.put(f"{V1}/series/{sid}/generate-rules", json={"shot_cap_usd": 0.5})
    assert resp.json()["takes_per_shot"] == 3 and resp.json()["shot_cap_usd"] == 0.5
    # Out of range, or the read-only thresholds.
    assert (
        client.put(f"{V1}/series/{sid}/generate-rules", json={"takes_per_shot": 9}).status_code
        == 422
    )
    bad = {"thresholds": {"face_sim": 0.5, "syncnet_conf": 1, "cer_max": 1}}
    assert client.put(f"{V1}/series/{sid}/generate-rules", json=bad).status_code == 422
    assert client.get(f"{V1}/series/nope/generate-rules").status_code == 404

    # The first run of a shot makes ``takes_per_shot`` takes.
    _confirm_storyboard(client)
    pid = _shots(client)["1-01"]["video_product_id"]
    assert _run(client, pid)["state"] == "succeeded"
    assert len(client.get(f"{V1}/products/{pid}").json()["versions"]) == 3


def test_the_run_log_lists_takes_fallbacks_and_failures(client: TestClient) -> None:
    assert client.get(f"{V1}/episodes/{EP1}/generate-log").json() == []
    _confirm_storyboard(client)
    state = client.app.state.studio  # type: ignore[attr-defined]
    shots = _shots(client)
    _run(client, shots["1-01"]["video_product_id"])
    state.registry.mock_settings.fail_keys.add("comfy/h3")
    _run(client, shots["1-02"]["video_product_id"])
    state.registry.mock_settings.fail_keys.add("minimax/h3-api")
    failed = _run(client, shots["1-03"]["video_product_id"])
    assert failed["state"] == "failed"

    log = client.get(f"{V1}/episodes/{EP1}/generate-log").json()
    lines = [(e["shot_label"], e["message"]["code"], e["warn"]) for e in log]
    assert lines[:2] == [("1-01", "take", False), ("1-01", "take", False)]
    assert ("1-02", "fallback_error", True) in lines
    assert lines[-1] == ("1-03", "failed", True)
    first = log[0]["message"]["params"]
    assert first["model"] == "comfy/h3" and first["take"] == 1
    assert 0 < first["cost_usd"] < 0.01  # local: only the prompt rewrite (vprompt) costs
    fallback = next(e for e in log if e["message"]["code"] == "fallback_error")
    take = log[log.index(fallback) + 1]
    assert take["message"]["params"]["model"] == "minimax/h3-api"
    assert take["message"]["params"]["cost_usd"] > 0
    assert log[-1]["message"]["params"]["model"] == "comfy/h3"
    assert [e["at"] for e in log] == sorted(e["at"] for e in log)
    assert client.get(f"{V1}/episodes/nope/generate-log").status_code == 404


def test_unadopt_and_rate_a_take(client: TestClient) -> None:
    _confirm_storyboard(client)
    pid = _shots(client)["1-01"]["video_product_id"]
    _run(client, pid)
    take = client.get(f"{V1}/products/{pid}").json()["versions"][0]
    client.post(f"{V1}/versions/{take['id']}/adopt").raise_for_status()
    steps = client.get(f"{V1}/episodes/{EP1}/progress").json()["steps"]
    assert steps["generate"]["done"] == 1

    resp = client.patch(f"{V1}/versions/{take['id']}", json={"rating": 4})
    assert resp.status_code == 200 and resp.json()["versions"][0]["rating"] == 4
    assert client.patch(f"{V1}/versions/{take['id']}", json={"rating": 6}).status_code == 422
    resp = client.patch(f"{V1}/versions/{take['id']}", json={"rating": None})
    assert resp.json()["versions"][0]["rating"] is None

    resp = client.post(f"{V1}/products/{pid}/unadopt")
    assert resp.status_code == 200 and resp.json()["adopted_version_id"] is None
    assert resp.json()["status"] == "ready"
    steps = client.get(f"{V1}/episodes/{EP1}/progress").json()["steps"]
    assert steps["generate"]["done"] == 0

    client.post(f"{V1}/versions/{take['id']}/adopt").raise_for_status()
    client.post(f"{V1}/products/{pid}/lock").raise_for_status()
    resp = client.post(f"{V1}/products/{pid}/unadopt")
    assert resp.status_code == 409 and resp.json()["detail"]["code"] == "product_locked"
    # The script's adopted version is mirrored into its tables: not something to undo.
    script = client.get(f"{V1}/products", params={"component": "script"}).json()[0]
    client.post(f"{V1}/products/{script['id']}/unlock").raise_for_status()
    resp = client.post(f"{V1}/products/{script['id']}/unadopt")
    assert resp.status_code == 409 and resp.json()["detail"]["code"] == "unadopt_unsupported"


def test_a_shot_over_its_cap_asks_first(client: TestClient) -> None:
    _confirm_storyboard(client)
    sid = SERIES
    pid = _shots(client)["1-01"]["video_product_id"]
    api = {"model": "minimax/h3-api", "count": 1}
    first = _run(client, pid, **api)
    assert first["state"] == "succeeded" and first["est_cost_usd"] > 0
    # The cap is now below what the shot spent plus another take (Mock: the Context-IR call is
    # what costs, about half the estimate).
    cap = first["est_cost_usd"] * 1.2
    client.put(f"{V1}/series/{sid}/generate-rules", json={"shot_cap_usd": cap}).raise_for_status()
    resp = client.post(f"{V1}/products/{pid}/run", json={"mode": "run", **api})
    job = resp.json()
    assert job["state"] == "waiting_confirm"
    confirm = job["params"]["confirm"]
    assert confirm["reason"] == "shot"
    assert 0 < confirm["limit_usd"] < confirm["estimate_usd"] < cap
    # Another shot has its own cap.
    other = _shots(client)["1-02"]["video_product_id"]
    assert _run(client, other, **api)["state"] == "succeeded"
    # The waiting job is in the run log.
    codes = [e["message"]["code"] for e in client.get(f"{V1}/episodes/{EP1}/generate-log").json()]
    assert "waiting" in codes


def test_the_summary_adds_up_spend_budget_and_whats_ahead(client: TestClient) -> None:
    sid = SERIES
    before = client.get(f"{V1}/metrics/summary", params={"scope": "episode", "episode": EP1})
    assert before.status_code == 200, before.text
    body = before.json()
    assert body["scope"] == "episode" and body["insights"] == []
    assert body["projected_usd"] >= body["spent_usd"]

    client.patch(f"{V1}/episodes/{EP1}", json={"budget_usd": 20}).raise_for_status()
    _confirm_storyboard(client)
    pid = _shots(client)["1-01"]["video_product_id"]
    _run(client, pid, model="minimax/h3-api", count=1)
    after = client.get(f"{V1}/metrics/summary", params={"scope": "episode", "episode": EP1}).json()
    assert after["budget_usd"] == 20
    assert after["spent_usd"] > body["spent_usd"]
    assert after["projected_usd"] >= after["spent_usd"]

    series = client.get(f"{V1}/metrics/summary", params={"scope": "series", "series": sid}).json()
    # The other demo episodes have budgets of their own.
    assert series["scope"] == "series" and series["budget_usd"] >= 20
    assert series["spent_usd"] >= after["spent_usd"]
    assert client.get(f"{V1}/metrics/summary", params={"episode": "nope"}).status_code == 404
    assert client.get(f"{V1}/metrics/summary", params={"scope": "series"}).status_code == 404
