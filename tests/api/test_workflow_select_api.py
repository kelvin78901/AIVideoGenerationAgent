"""按镜头选工作流 (M5 step 12a), in Mock mode: the series' rules table, the shot's own pick, the
LLM's suggestion, and what decided it on the take's ``model_call.select_json``.

The demo: 1-04 is 原生同步 with a locked voice sample; 1-01 has no voice.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import col, select

from drama_series_agent.api.app import create_app
from drama_series_agent.api.state import StudioState
from drama_series_agent.core.models_db import ModelCall

LOCAL = "http://127.0.0.1"
V1 = "/api/v1"
SERIES = "demo"
EP1 = "demo-e1"
NATIVE_RULE = {"when": {"audio_mode": "native", "voices": True}, "model": "comfy/h3-r2v"}


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(), base_url=LOCAL, headers={"X-Drama-Studio": "1"}) as c:
        yield c


def _state(client: TestClient) -> StudioState:
    state: StudioState = client.app.state.studio  # type: ignore[attr-defined]
    return state


def _rows(client: TestClient, model: Any, *where: Any) -> list[Any]:
    async def read() -> list[Any]:
        async with _state(client).db.session() as s:
            return list((await s.exec(select(model).where(*where))).all())

    return list(client.portal.call(read))  # type: ignore[union-attr]


def _shots(client: TestClient) -> dict[str, dict[str, Any]]:
    return {s["label"]: s for s in client.get(f"{V1}/episodes/{EP1}/shots").json()}


def _run(client: TestClient, product_id: str) -> dict[str, Any]:
    resp = client.post(f"{V1}/products/{product_id}/run", json={"mode": "run"})
    assert resp.status_code == 200, resp.text
    deadline = time.monotonic() + 60
    while (job := client.get(f"{V1}/jobs/{resp.json()['id']}").json())["state"] not in (
        "succeeded", "failed", "canceled",
    ):  # fmt: skip
        assert time.monotonic() < deadline, "the job did not finish"
        time.sleep(0.02)
    assert job["state"] == "succeeded", job
    product: dict[str, Any] = client.get(f"{V1}/products/{product_id}").json()
    return product


def _confirm_storyboard(client: TestClient) -> None:
    for label, shot in _shots(client).items():
        if not shot["confirmed"]:
            resp = client.patch(f"{V1}/shots/{shot['id']}", json={"confirmed": True})
            assert resp.status_code == 200, (label, resp.text)
    resp = client.post(f"{V1}/gates/storyboard/confirm", json={"scope_id": EP1})
    assert resp.status_code == 200, resp.text


def _video_calls(client: TestClient, product_id: str) -> list[ModelCall]:
    calls = _rows(client, ModelCall, col(ModelCall.product_id) == product_id)
    return [c for c in calls if c.component_id == "vid"]


def _take(client: TestClient, label: str) -> tuple[dict[str, Any], ModelCall]:
    pid = _shots(client)[label]["video_product_id"]
    take = _run(client, pid)["versions"][0]
    call = next(c for c in _video_calls(client, pid) if c.model_key == take["model_key"])
    return take, call


def _put_rules(client: TestClient, **body: Any) -> dict[str, Any]:
    resp = client.put(f"{V1}/series/{SERIES}/workflow-rules", json=body)
    assert resp.status_code == 200, resp.text
    out: dict[str, Any] = resp.json()
    return out


def test_the_rules_table_starts_from_the_config_and_names_only_pickable_workflows(
    client: TestClient,
) -> None:
    url = f"{V1}/series/{SERIES}/workflow-rules"
    first = client.get(url).json()
    assert first["rules"] == [NATIVE_RULE] and first["suggest"] is False
    assert first["saved"] is False
    assert {"comfy/h3", "comfy/h3-r2v"} <= set(first["models"])
    assert "comfy/wan-2.2" not in first["models"]  # no workflow: cannot be picked
    rule = {"when": {"framing": "closeup", "dialogue": True}, "model": "comfy/h3"}
    saved = _put_rules(client, rules=[rule], suggest=True)
    assert saved["saved"] and saved["suggest"] and saved["rules"] == [rule]
    for model in ("comfy/wan-2.2", "minimax/h3-api", "nope/x"):
        bad = client.put(url, json={"rules": [{"when": {}, "model": model}]})
        assert bad.status_code == 422 and bad.json()["detail"]["code"] == "workflow_rule_model"
    bad = client.put(url, json={"rules": [{"when": {"mood": "sad"}, "model": "comfy/h3"}]})
    assert bad.status_code == 422
    reset = client.delete(url).json()
    assert reset["saved"] is False and reset["rules"] == [NATIVE_RULE]
    assert client.get(f"{V1}/series/nope/workflow-rules").status_code == 404


def test_a_rule_picks_the_workflow_and_the_call_says_which(client: TestClient) -> None:
    _confirm_storyboard(client)
    take, call = _take(client, "1-04")  # 原生同步 with a voice: the default rule
    assert take["model_key"] == "comfy/h3-r2v"
    assert call.select_json == {"by": "rule", "rule": 0, "when": NATIVE_RULE["when"]}
    assert take["params"]["select"] == call.select_json
    take, call = _take(client, "1-01")
    assert take["model_key"] == "comfy/h3" and call.select_json == {"by": "default"}
    # The rewrite the take asked for is not the video's choice.
    rewrites = _rows(client, ModelCall, col(ModelCall.component_id) == "vprompt")
    assert rewrites and all(r.select_json is None for r in rewrites)


def test_the_series_table_decides_in_order(client: TestClient) -> None:
    _confirm_storyboard(client)
    framing = _shots(client)["1-01"]["framing"]
    _put_rules(
        client,
        rules=[
            {"when": {"framing": framing, "audio_mode": "none"}, "model": "comfy/h3"},
            {"when": {"framing": framing}, "model": "comfy/h3-r2v"},
        ],
    )
    take, call = _take(client, "1-01")
    assert take["model_key"] == "comfy/h3-r2v" and call.select_json == {
        "by": "rule", "rule": 1, "when": {"framing": framing},
    }  # fmt: skip
    # The estimate reads the same table.
    product = client.get(f"{V1}/products/{_shots(client)['1-01']['video_product_id']}").json()
    assert product["estimate"]["model_key"] == "comfy/h3-r2v"


def test_a_workflow_picked_for_the_shot_wins_over_the_rules(client: TestClient) -> None:
    _confirm_storyboard(client)
    shot = _shots(client)["1-04"]
    body = {"scope": "item", "scope_id": f"shot:{shot['id']}", "component_id": "vid"}
    client.put(
        f"{V1}/config/override", json={**body, "data": {"local_model": "comfy/h3"}}
    ).raise_for_status()
    take, call = _take(client, "1-04")
    assert take["model_key"] == "comfy/h3" and call.select_json == {"by": "manual"}


def test_the_llm_suggests_when_no_rule_matches_and_is_asked_once(client: TestClient) -> None:
    _confirm_storyboard(client)
    _put_rules(client, rules=[], suggest=True)
    pid = _shots(client)["1-04"]["video_product_id"]
    take, call = _take(client, "1-04")
    assert take["model_key"] == "comfy/h3-r2v"  # Mock: the one that takes voice samples
    assert call.select_json is not None and call.select_json["by"] == "suggest"
    assert call.select_json["reason"] and call.select_json["suggested_by"]
    asked = _rows(client, ModelCall, col(ModelCall.component_id) == "vselect")
    assert len(asked) == 1 and asked[0].shot_id == _shots(client)["1-04"]["id"]
    # Another take of the same shot, and its estimate: the cached answer, no new call.
    assert client.get(f"{V1}/products/{pid}").json()["estimate"]["model_key"] == "comfy/h3-r2v"
    again = _run(client, pid)["versions"][0]
    assert again["model_key"] == "comfy/h3-r2v"
    assert len(_rows(client, ModelCall, col(ModelCall.component_id) == "vselect")) == 1


def test_an_answer_that_names_no_candidate_keeps_the_route(client: TestClient) -> None:
    _confirm_storyboard(client)
    _put_rules(client, rules=[], suggest=True)
    _state(client).registry.add_mock_responder(
        "vid", "select", lambda req: {"model": "comfy/nope", "reason": "?"}
    )
    take, call = _take(client, "1-04")
    assert take["model_key"] == "comfy/h3" and call.select_json == {"by": "default"}


async def test_many_products_at_once_do_not_run_the_pool_dry() -> None:
    """Choosing a workflow reads the rules in a session of its own; inside the estimate's
    session that held two connections per request, and a page loading dozens of products at
    once waited out the pool's 30 s timeout (CI's e2e hangs, M5 step 12c)."""
    import asyncio

    import httpx

    app = create_app()
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url=LOCAL, headers={"X-Drama-Studio": "1"}, timeout=60
        ) as c:
            shots = (await c.get(f"{V1}/episodes/{EP1}/shots")).json()
            ids = [s["video_product_id"] for s in shots] * 4  # > 15 connections' worth
            start = time.monotonic()
            responses = await asyncio.gather(*(c.get(f"{V1}/products/{i}") for i in ids))
    assert [r.status_code for r in responses] == [200] * len(ids)
    assert time.monotonic() - start < 20
