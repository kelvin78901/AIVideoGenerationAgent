"""Running products (SPEC 5, 7.4, 8): run / rerun / switch, prompts, retry-once, cache, staleness.

A test component stands in for the real ones (extract, enrich … arrive in later steps): it
reads an upstream product, returns JSON from a Mock responder and depends on its upstream.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from drama_series_agent.api.app import create_app
from drama_series_agent.api.state import StudioState
from drama_series_agent.core.models_db import Dependency, Event, ModelCall, Product
from drama_series_agent.modelhub.adapters.base import ModelRequest
from drama_series_agent.modelhub.adapters.mock import Responder
from drama_series_agent.pipeline.component import Component, Inputs
from drama_series_agent.pipeline.products import VersionDraft
from drama_series_agent.prompts.compiler import TEMPLATES, Block, PromptCompiler

LOCAL = "http://127.0.0.1"
V1 = "/api/v1"


class Lines(BaseModel):
    lines: list[str]


class EchoComponent(Component):
    """Plays ``split``: reads the series' bible product, answers with two lines."""

    id = "split"
    slot = "test_split"  # not the demo series' real plan
    owner_type = "series"
    max_tokens = 300
    upstream_id = "test-bible"

    async def inputs(self, session: AsyncSession, product: Product) -> Inputs:
        dep = await self.services.invalidation.dependency(session, self.upstream_id)
        return Inputs(blocks=[Block("原文", "[P1] 雨停之前。")], deps=[dep])

    def output_schema(self) -> type[BaseModel]:
        return Lines

    def mock_responders(self) -> dict[str, Responder]:
        def answer(req: ModelRequest) -> dict[str, Any]:
            return {"lines": [str(req.meta["task"]), str(req.seed)]}

        return {"run": answer}


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    templates = tmp_path / "templates" / "split"
    templates.mkdir(parents=True)
    (templates / "default.j2").write_text("[指令]\n{{ intent }}\n# {{ model_key }}", "utf-8")
    (templates / "intent.zh-CN.txt").write_text("按节奏分集。", "utf-8")
    with TestClient(create_app(), base_url=LOCAL, headers={"X-Drama-Studio": "1"}) as c:
        state = _state(c)
        services = state.components.services
        services.compiler = PromptCompiler([tmp_path / "templates", TEMPLATES])
        state.components.add(EchoComponent(services))
        yield c


def _state(client: TestClient) -> StudioState:
    state: StudioState = client.app.state.studio  # type: ignore[attr-defined]
    return state


def _call(client: TestClient, fn: Any, *args: Any) -> Any:
    return client.portal.call(fn, *args)  # type: ignore[union-attr]


def _code(resp: Any) -> str:
    return str(resp.json()["detail"]["code"])


def _setup(client: TestClient) -> str:
    """The upstream (adopted v1) and an empty downstream product; returns the downstream id."""
    svc = _state(client).products

    async def make() -> str:
        await svc.ensure(
            series_id="demo",
            owner_type="series",
            owner_id="demo",
            slot="test_upstream",
            component_id="upstream",
            product_id="test-bible",
        )
        await svc.append("test-bible", VersionDraft(payload={"names": ["林晚"]}), origin="run")
        p = await svc.ensure(
            series_id="demo",
            owner_type="series",
            owner_id="demo",
            slot="test_split",
            component_id="split",
        )
        return p.id

    return str(_call(client, make))


def _wait(client: TestClient, job_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        job: dict[str, Any] = client.get(f"{V1}/jobs/{job_id}").json()
        if job["state"] in ("succeeded", "failed", "canceled"):
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def _run(client: TestClient, pid: str, **body: Any) -> dict[str, Any]:
    resp = client.post(f"{V1}/products/{pid}/run", json={"mode": "run", **body})
    assert resp.status_code == 200, resp.text
    return _wait(client, resp.json()["id"])


def _rows(client: TestClient, model: Any) -> list[Any]:
    async def read() -> list[Any]:
        async with _state(client).db.session() as s:
            return list((await s.exec(select(model))).all())

    return list(_call(client, read))


def test_first_run_makes_an_adopted_version(client: TestClient) -> None:
    pid = _setup(client)
    before = client.get(f"{V1}/products/{pid}").json()
    assert before["status"] == "empty"
    # A product that never ran shows the default prompt and what a run would cost.
    assert before["prompt"]["intent"] == "按节奏分集。"
    assert before["prompt"]["compiled"] == "[指令]\n按节奏分集。\n# deepseek/v4.1-flash"
    assert before["estimate"]["model_key"] == "deepseek/v4.1-flash"
    assert before["estimate"]["cost_usd"] > 0

    job = _run(client, pid)
    assert job["state"] == "succeeded" and job["queue"] == "api:deepseek"
    data = client.get(f"{V1}/products/{pid}").json()
    assert data["status"] == "adopted" and data["running"] is None
    v1 = data["versions"][0]
    assert (v1["origin"], v1["model_key"], v1["where"]) == ("run", "deepseek/v4.1-flash", "api")
    assert v1["payload"] == {"lines": ["run", str(job["params"]["seed"])]}
    assert v1["files"][0]["role"] == "prompt" and v1["cost_usd"] > 0
    assert v1["intent"] == "按节奏分集。" and not v1["compiled_overridden"]

    calls = [c for c in _rows(client, ModelCall) if c.product_id == pid]
    assert len(calls) == 1 and calls[0].component_id == "split" and calls[0].status == "success"
    deps = [d for d in _rows(client, Dependency) if d.product_id == pid]
    assert [(d.version_id, d.upstream_product_id) for d in deps] == [(v1["id"], "test-bible")]
    toasts = [e.data_json for e in _rows(client, Event) if e.type == "toast"]
    assert toasts[-1]["code"] == "version_created" and toasts[-1]["params"]["n"] == 1


def test_rerun_and_switch(client: TestClient) -> None:
    pid = _setup(client)
    first = _run(client, pid)
    second = _run(client, pid, mode="rerun")
    assert second["params"]["seed"] != first["params"]["seed"]
    data = client.get(f"{V1}/products/{pid}").json()
    v1, v2 = data["versions"]
    assert v2["origin"] == "rerun" and v2["parent_version_id"] == v1["id"]
    assert data["adopted_version_id"] == v1["id"] and data["current_version_id"] == v2["id"]

    # 不满意换一个: the next model in alt_order after the one on screen.
    third = _run(client, pid, mode="switch")
    assert third["params"]["model_key"] == "qwen/qwen3.7-plus"
    data = client.get(f"{V1}/products/{pid}").json()
    assert data["versions"][-1]["origin"] == "switch"
    assert data["prompt"]["compiled"].endswith("# qwen/qwen3.7-plus")
    switched = [c for c in _rows(client, ModelCall) if c.model_key == "qwen/qwen3.7-plus"]
    assert switched and switched[0].is_switch
    # A model picked by hand.
    fourth = _run(client, pid, mode="switch", model="moonshot/kimi-k2.6")
    assert fourth["params"]["model_key"] == "moonshot/kimi-k2.6"


def test_prompt_layers(client: TestClient) -> None:
    pid = _setup(client)
    preview = client.post(f"{V1}/products/{pid}/compile", json={"intent": "节奏再快一点"}).json()
    assert preview == {
        "compiled": "[指令]\n节奏再快一点\n# deepseek/v4.1-flash",
        "model_key": "deepseek/v4.1-flash",
    }
    data = client.put(
        f"{V1}/products/{pid}/prompt", json={"intent": "快", "compiled": "手写"}
    ).json()
    assert data["prompt"]["compiled"] == "手写" and data["prompt"]["compiled_overridden"]
    # A plain rerun keeps the hand-edited layer …
    job = _run(client, pid, mode="rerun")
    assert job["params"]["compiled"] == "手写"
    # … switching models compiles afresh for the target.
    job = _run(client, pid, mode="switch")
    assert job["params"]["compiled"].startswith("[指令]\n快")
    assert not job["params"]["compiled_overridden"]
    # 保存并重跑 with a new intent.
    job = _run(client, pid, mode="rerun", intent="慢一点")
    assert job["params"]["compiled"].startswith("[指令]\n慢一点")

    resp = client.post(f"{V1}/products/{pid}/compile", json={"intent": "x", "model": "no/such"})
    assert resp.status_code == 422 and _code(resp) == "unknown_model"


def test_invalid_json_is_retried_once(client: TestClient) -> None:
    pid = _setup(client)
    settings = _state(client).registry.mock_settings
    settings.bad_json = 1
    assert _run(client, pid)["state"] == "succeeded"
    assert len([c for c in _rows(client, ModelCall) if c.product_id == pid]) == 2

    settings.bad_json = 2
    job = _run(client, pid, mode="rerun")
    assert job["state"] == "failed" and job["error"]["code"] == "invalid_output"
    assert _state(client).store.exists(job["error"]["params"]["raw"])  # the raw answer is kept
    data = client.get(f"{V1}/products/{pid}").json()
    assert data["status"] == "failed" and len(data["versions"]) == 1
    toasts = [e.data_json for e in _rows(client, Event) if e.type == "toast"]
    assert toasts[-1] == {
        "level": "error",
        "code": "run_failed",
        "params": {"error": "invalid_output"},
    }


def test_cached_answers_are_not_paid_twice(client: TestClient) -> None:
    pid = _setup(client)
    state = _state(client)
    comp = state.components.get("split")
    assert comp is not None
    from drama_series_agent.pipeline.component import RunContext

    async def ask_twice() -> tuple[bool, bool]:
        async with state.db.session() as s:
            product = await s.get(Product, pid)
        assert product is not None
        ctx = RunContext(
            product=product,
            mode="run",
            model_key="deepseek/v4.1-flash",
            seed=7,
            intent="",
            compiled="x",
            compiled_overridden=False,
        )
        msgs = [{"role": "system", "content": "x"}]
        a = await comp.call_json(ctx, msgs, Lines)
        b = await comp.call_json(ctx, msgs, Lines)
        return a.cached, b.cached

    assert _call(client, ask_twice) == (False, True)
    assert len([c for c in _rows(client, ModelCall) if c.product_id == pid]) == 1


def test_stale_when_the_upstream_changes(client: TestClient) -> None:
    pid = _setup(client)
    _run(client, pid)
    svc = _state(client).products

    async def change_upstream(adopt_new: bool) -> None:
        if adopt_new:
            draft = VersionDraft(payload={"names": ["林晚", "周屿"]})
            await svc.append("test-bible", draft, origin="edit", adopt=True)
        else:
            first = (await svc.get("test-bible")).versions[0]
            await svc.adopt(first.id)

    _call(client, change_upstream, True)
    assert client.get(f"{V1}/products/{pid}").json()["status"] == "stale"
    _call(client, change_upstream, False)  # back to what it was built from
    assert client.get(f"{V1}/products/{pid}").json()["status"] == "adopted"


def test_run_errors(client: TestClient) -> None:
    pid = _setup(client)
    _state(client).registry.mock_settings.delay_s = 0.3
    first = client.post(f"{V1}/products/{pid}/run", json={"mode": "run"})
    assert client.get(f"{V1}/products/{pid}").json()["running"]["job_id"] == first.json()["id"]
    resp = client.post(f"{V1}/products/{pid}/run", json={"mode": "rerun"})
    assert resp.status_code == 409 and _code(resp) == "product_busy"
    _wait(client, first.json()["id"])
    _state(client).registry.mock_settings.delay_s = 0

    resp = client.post(f"{V1}/products/test-bible/run", json={"mode": "run"})
    assert resp.status_code == 409 and _code(resp) == "component_not_ready"  # no such component
    resp = client.post(f"{V1}/products/{pid}/run", json={"mode": "run", "model": "no/such"})
    assert resp.status_code == 422 and _code(resp) == "unknown_model"
    resp = client.post(f"{V1}/products/nope/run", json={"mode": "run"})
    assert resp.status_code == 404 and _code(resp) == "product_not_found"


# --------------------------------------------------------------------------- budget (SPEC 7.6)


def _cap(client: TestClient, usd: float) -> None:
    body = {"scope": "component", "scope_id": None, "component_id": "split"}
    resp = client.put(f"{V1}/config/override", json={**body, "data": {"per_call_cap_usd": usd}})
    assert resp.status_code == 200


def _until_state(client: TestClient, job_id: str, state: str) -> dict[str, Any]:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        job: dict[str, Any] = client.get(f"{V1}/jobs/{job_id}").json()
        if job["state"] == state:
            return job
        time.sleep(0.02)
    raise AssertionError(f"job never reached {state}")


def test_over_the_cap_waits_for_a_yes(client: TestClient) -> None:
    pid = _setup(client)
    _cap(client, 0.00001)
    resp = client.post(f"{V1}/products/{pid}/run", json={"mode": "run"})
    job = resp.json()
    assert job["state"] == "waiting_confirm"
    confirm = job["params"]["confirm"]
    assert confirm["reason"] == "per_call" and confirm["limit_usd"] == 0.0
    assert confirm["estimate_usd"] == pytest.approx(job["est_cost_usd"], abs=1e-4)
    product = client.get(f"{V1}/products/{pid}").json()
    assert product["status"] == "queued"
    assert product["running"]["state"] == "waiting_confirm"
    assert not [c for c in _rows(client, ModelCall) if c.product_id == pid]  # nothing spent

    confirmed = client.post(f"{V1}/jobs/{job['id']}/confirm").json()
    assert confirmed["confirmed_usd"] == job["est_cost_usd"]
    assert _wait(client, job["id"])["state"] == "succeeded"
    assert client.get(f"{V1}/products/{pid}").json()["status"] == "adopted"


def test_a_pricier_fallback_after_a_yes_fails(client: TestClient) -> None:
    pid = _setup(client)
    _cap(client, 0.00001)
    settings = _state(client).registry.mock_settings
    settings.fail_keys = {"deepseek/v4.1-flash"}  # fallback: Qwen3.7-plus, which costs more
    job = client.post(f"{V1}/products/{pid}/run", json={"mode": "run"}).json()
    client.post(f"{V1}/jobs/{job['id']}/confirm")
    done = _wait(client, job["id"])
    assert done["state"] == "failed" and done["error"]["code"] == "budget_exceeded"
    assert not [c for c in _rows(client, ModelCall) if c.model_key == "qwen/qwen3.7-plus"]


def test_fallback_asks_first_when_set_to(client: TestClient) -> None:
    pid = _setup(client)
    client.put(f"{V1}/config/defaults", json={"fallback_notify": "ask"})
    _state(client).registry.mock_settings.fail_keys = {"deepseek/v4.1-flash"}
    job = client.post(f"{V1}/products/{pid}/run", json={"mode": "run"}).json()
    waiting = _until_state(client, job["id"], "waiting_confirm")
    assert waiting["params"]["model_key"] == "qwen/qwen3.7-plus"
    assert waiting["params"]["confirm"]["reason"] == "fallback"
    assert waiting["params"]["confirm"]["failed_model"] == "deepseek/v4.1-flash"
    assert client.get(f"{V1}/products/{pid}").json()["running"]["model_key"] == "qwen/qwen3.7-plus"

    client.post(f"{V1}/jobs/{job['id']}/confirm")
    assert _wait(client, job["id"])["state"] == "succeeded"
    version = client.get(f"{V1}/products/{pid}").json()["versions"][0]
    assert (version["origin"], version["fallback_reason"]) == ("fallback", "error")
    assert version["model_key"] == "qwen/qwen3.7-plus"
    calls = [c for c in _rows(client, ModelCall) if c.product_id == pid]
    assert [(c.model_key, c.status, c.is_fallback) for c in calls] == [
        ("deepseek/v4.1-flash", "error", False),
        ("qwen/qwen3.7-plus", "success", True),
    ]


def test_episode_budget_counts_reservations(client: TestClient) -> None:
    """Left = budget − spent − queued / waiting estimates − what running jobs may still spend."""
    state = _state(client)

    async def scenario() -> tuple[float | None, float | None, Any]:
        async def budget_of(episode_id: str) -> float | None:
            return 1.0 if episode_id == "e1" else None

        state.budget.episode_budget = budget_of
        await state.jobs.enqueue("nothing", "api:x", {}, episode_id="e1", est_cost_usd=0.25,
                                 wait_for_confirm=True)  # fmt: skip
        left = await state.budget.left("e1")
        other = await state.budget.left("e2")
        verdict = await state.budget.before_enqueue(0.8, cap=None, episode_id="e1")
        return left, other, verdict

    left, other, verdict = _call(client, scenario)
    assert left == pytest.approx(0.75) and other is None
    assert (verdict.ok, verdict.reason) == (False, "episode")
    assert verdict.limit_usd == pytest.approx(0.75)
