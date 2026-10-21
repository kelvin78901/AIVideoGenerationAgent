"""小说补全 and its suggestions (SPEC 5 ``enrich``, 9.1 ``/series/{id}/suggestions``,
``/suggestions/…``; M2 plan step 7).

The demo series is seeded with the suggestions a Mock run makes (v2 adopted, s1 accepted) and a
bible read with that addition. Decisions never make a version; accepting or undoing one turns
the bible stale or fresh (the ``adopted`` slice), while the bible running again leaves the
suggestions fresh (they read its ``names`` slice only).
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import select

from drama_series_agent.api.app import create_app
from drama_series_agent.api.state import StudioState
from drama_series_agent.core.models_db import ModelCall, ProductVersion, Suggestion
from drama_series_agent.core.paths import REPO_ROOT
from drama_series_agent.suggestions import service as suggestions

LOCAL = "http://127.0.0.1"
V1 = "/api/v1"
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "demo"
DEMO = (FIXTURES / "雨停之前.txt").read_bytes()
FIXTURE = json.loads((FIXTURES / "enrich.json").read_text(encoding="utf-8"))


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(), base_url=LOCAL, headers={"X-Drama-Studio": "1"}) as c:
        yield c


def _state(client: TestClient) -> StudioState:
    state: StudioState = client.app.state.studio  # type: ignore[attr-defined]
    return state


def _call(client: TestClient, fn: Any, *args: Any) -> Any:
    return client.portal.call(fn, *args)  # type: ignore[union-attr]


def _code(resp: Any) -> str:
    return str(resp.json()["detail"]["code"])


def _rows(client: TestClient, model: Any) -> list[Any]:
    async def read() -> list[Any]:
        async with _state(client).db.session() as s:
            return list((await s.exec(select(model))).all())

    return list(_call(client, read))


def _wait(client: TestClient, job_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        job: dict[str, Any] = client.get(f"{V1}/jobs/{job_id}").json()
        if job["state"] in ("succeeded", "failed", "canceled"):
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def _product(client: TestClient, series: str, component: str) -> dict[str, Any]:
    listed = client.get(f"{V1}/products", params={"owner": f"series:{series}"}).json()
    return next(p for p in listed if p["component_id"] == component)


def _status(client: TestClient, series: str, component: str) -> str:
    return str(_product(client, series, component)["status"])


def _run(client: TestClient, product_id: str, mode: str = "run") -> dict[str, Any]:
    resp = client.post(f"{V1}/products/{product_id}/run", json={"mode": mode})
    assert resp.status_code == 200, resp.text
    job = _wait(client, resp.json()["id"])
    assert job["state"] == "succeeded", job
    return job


def _list(client: TestClient, series: str = "demo") -> dict[str, Any]:
    resp = client.get(f"{V1}/series/{series}/suggestions")
    assert resp.status_code == 200, resp.text
    data: dict[str, Any] = resp.json()
    return data


def _by_id(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {s["id"]: s for s in data["suggestions"]}


def _act(client: TestClient, sid: str, action: str, **body: Any) -> dict[str, Any]:
    resp = client.post(f"{V1}/suggestions/{sid}/{action}", json=body or None)
    assert resp.status_code == 200, resp.text
    data: dict[str, Any] = resp.json()
    return data


def _new_series_with_demo_novel(client: TestClient) -> str:
    series = str(client.post(f"{V1}/series", json={"title": "复刻"}).json()["id"])
    resp = client.post(
        f"{V1}/series/{series}/novel",
        files={"file": ("雨停之前.txt", DEMO)},
        data={"rights_confirmed": "true"},
    )
    assert resp.status_code == 200, resp.text
    return series


def _prompt_text(client: TestClient, version_id: str) -> str:
    async def read() -> str:
        async with _state(client).db.session() as s:
            v = await s.get(ProductVersion, version_id)
        assert v is not None
        sha = next(f["sha256"] for f in v.files_json if f["role"] == "prompt")
        return _state(client).store.read_bytes(sha).decode("utf-8")

    return str(_call(client, read))


def _comparable(data: dict[str, Any]) -> list[tuple[Any, ...]]:
    return [(s["kind"], s["para_idx"], s["reason"], s["text"]) for s in data["suggestions"]]


def test_demo_suggestions_are_seeded(client: TestClient) -> None:
    data = _list(client)
    enrich = _product(client, "demo", "enrich")
    assert data["product_id"] == enrich["id"] == "demo-p-enrich"
    assert data["version_id"] == "demo-p-enrich-v2" and data["adopted"] is True
    assert [s["id"] for s in data["suggestions"]] == ["s1", "s2", "s3", "s4"]
    statuses = [s["status"] for s in data["suggestions"]]
    assert statuses == ["accepted", "pending", "pending", "pending"]
    novel = client.get(f"{V1}/series/demo/novel").json()
    first = novel["paragraphs"][0]
    s1 = data["suggestions"][0]
    assert (s1["para_idx"], s1["text"]) == (0, FIXTURE["suggestions"][0]["text"])
    span = {"source_id": "demo-src", "start": first["start"], "end": first["end"]}
    assert s1["anchor_span"] == span
    # v1 local → v2 DeepSeek; nothing downstream is stale at the start.
    assert [v["model_key"] for v in enrich["versions"]] == ["local/qwen3.6-27b", "deepseek/v4-pro"]
    assert enrich["status"] == "adopted" and _status(client, "demo", "extract") == "adopted"


def test_a_run_on_the_demo_novel_matches_the_seed(client: TestClient) -> None:
    series = _new_series_with_demo_novel(client)
    assert _list(client, series)["suggestions"] == []
    job = _run(client, _product(client, series, "enrich")["id"])
    data = _list(client, series)
    assert data["adopted"] is True and data["version_id"] == job["result"]["version_id"]
    assert _comparable(data) == _comparable(_list(client))
    assert all(s["status"] == "pending" for s in data["suggestions"])
    assert all(s["id"].startswith("sug-") for s in data["suggestions"])
    calls = [c for c in _rows(client, ModelCall) if c.component_id == "enrich"]
    assert calls and all(c.series_id == series for c in calls)


def test_a_rerun_keeps_ids_and_decisions(client: TestClient) -> None:
    _act(client, "s3", "reject")
    pid = _product(client, "demo", "enrich")["id"]
    _run(client, pid)
    product = _product(client, "demo", "enrich")
    # A rerun only becomes current; the screen shows it as not adopted (硬规则 5).
    assert product["current_version_id"] != product["adopted_version_id"]
    data = _list(client)
    assert data["adopted"] is False
    assert [(s["id"], s["status"]) for s in data["suggestions"]] == [
        ("s1", "accepted"), ("s2", "pending"), ("s3", "rejected"), ("s4", "pending"),
    ]  # fmt: skip


def test_decisions_turn_the_bible_stale_and_back(client: TestClient) -> None:
    versions = len(_product(client, "demo", "enrich")["versions"])
    assert _act(client, "s2", "accept")["status"] == "accepted"
    assert _status(client, "demo", "extract") == "stale"
    assert _status(client, "demo", "enrich") == "adopted"
    assert _act(client, "s2", "reset")["status"] == "pending"
    assert _status(client, "demo", "extract") == "adopted"
    # Ignoring a pending one changes nothing downstream reads.
    assert _act(client, "s4", "reject")["status"] == "rejected"
    assert _status(client, "demo", "extract") == "adopted"
    assert len(_product(client, "demo", "enrich")["versions"]) == versions  # no version made


def test_accept_all_skips_ignored(client: TestClient) -> None:
    _act(client, "s3", "reject")
    resp = client.post(f"{V1}/series/demo/suggestions/accept-all")
    assert resp.status_code == 200, resp.text
    assert [s["status"] for s in resp.json()["suggestions"]] == [
        "accepted", "accepted", "rejected", "accepted",
    ]  # fmt: skip
    assert _status(client, "demo", "extract") == "stale"


def test_the_bible_reads_accepted_additions(client: TestClient) -> None:
    # The demo's suggestions were made before the bible; a rerun now reads its names.
    enrich = _run(client, _product(client, "demo", "enrich")["id"])
    client.post(f"{V1}/versions/{enrich['result']['version_id']}/adopt")
    s2 = FIXTURE["suggestions"][1]["text"]
    _act(client, "s2", "accept")
    assert _status(client, "demo", "extract") == "stale"
    job = _run(client, _product(client, "demo", "extract")["id"])
    prompt = _prompt_text(client, job["result"]["version_id"])
    assert f"【补写】{FIXTURE['suggestions'][0]['text']}【补写】{s2}" in prompt
    client.post(f"{V1}/versions/{job['result']['version_id']}/adopt")
    assert _status(client, "demo", "extract") == "adopted"
    # The bible ran again over the same names: the suggestions stay fresh (no cycle).
    assert _status(client, "demo", "enrich") == "adopted"
    # A new name is something 补全 read: now it is stale.
    entity = client.get(f"{V1}/series/demo/bible").json()["entities"][0]
    resp = client.patch(f"{V1}/bible/{entity['id']}", json={"name": "林小晚"})
    assert resp.status_code == 200, resp.text
    assert _status(client, "demo", "enrich") == "stale"


def test_rewrite_on_request(client: TestClient) -> None:
    out = _act(client, "s2", "rewrite", instruction="写成灯一闪一闪的")
    assert out["text"] == FIXTURE["rewrites"]["s2"]
    assert out["status"] == "rewritten" and out["rewrite_instruction"] == "写成灯一闪一闪的"
    [call] = [c for c in _rows(client, ModelCall) if c.component_id == "enrich"]
    assert out["rewritten_by"] == call.model_key and call.product_id == "demo-p-enrich"
    # Kept after accepting, and 「撤销」 goes back to 「已重写」.
    assert _act(client, "s2", "accept")["text"] == FIXTURE["rewrites"]["s2"]
    assert _act(client, "s2", "reset")["status"] == "rewritten"
    # An accepted one stays accepted with its new text; downstream reads the rewrite.
    _act(client, "s1", "rewrite", instruction="换成工装外套")
    assert _by_id(_list(client))["s1"]["status"] == "accepted"
    assert _status(client, "demo", "extract") == "stale"
    calls = [c for c in _rows(client, ModelCall) if c.component_id == "enrich"]
    assert len(calls) == 2 and all(c.product_id == "demo-p-enrich" for c in calls)


def test_rewrite_over_the_cap_asks_first(client: TestClient) -> None:
    body = {"scope": "component", "scope_id": None, "component_id": "enrich"}
    data = {"mode": "api", "per_call_cap_usd": 0.0000001}
    assert client.put(f"{V1}/config/override", json={**body, "data": data}).status_code == 200
    resp = client.post(f"{V1}/suggestions/s2/rewrite", json={"instruction": "短一点"})
    assert (resp.status_code, _code(resp)) == (409, "over_budget")
    params = resp.json()["detail"]["params"]
    assert params["estimate_usd"] > params["limit_usd"]
    assert not [c for c in _rows(client, ModelCall) if c.component_id == "enrich"]
    out = _act(client, "s2", "rewrite", instruction="短一点", confirm_budget=True)
    assert out["status"] == "rewritten"
    assert [c.status for c in _rows(client, ModelCall) if c.component_id == "enrich"] == ["success"]


def test_errors(client: TestClient) -> None:
    assert _code(client.post(f"{V1}/suggestions/nope/accept")) == "suggestion_not_found"
    assert client.post(f"{V1}/suggestions/s1/maybe").status_code == 422
    resp = client.post(f"{V1}/suggestions/s1/rewrite", json={"instruction": "  "})
    assert (resp.status_code, _code(resp)) == (422, "instruction_required")
    assert _code(client.get(f"{V1}/series/nope/suggestions")) == "series_not_found"
    assert _code(client.post(f"{V1}/series/nope/suggestions/accept-all")) == "series_not_found"
    pid = _product(client, "demo", "enrich")["id"]
    assert client.post(f"{V1}/products/{pid}/lock").status_code == 200
    resp = client.post(f"{V1}/suggestions/s2/accept")
    assert (resp.status_code, _code(resp)) == (409, "product_locked")
    assert _code(client.post(f"{V1}/series/demo/suggestions/accept-all")) == "product_locked"


def test_busy_while_enrichment_runs(client: TestClient) -> None:
    settings = _state(client).registry.mock_settings
    settings.delay_s = 0.5
    pid = _product(client, "demo", "enrich")["id"]
    job = client.post(f"{V1}/products/{pid}/run", json={"mode": "run"}).json()
    resp = client.post(f"{V1}/suggestions/s2/accept")
    assert (resp.status_code, _code(resp)) == (409, "product_busy")
    settings.delay_s = 0
    _wait(client, job["id"])


def test_a_series_without_a_novel(client: TestClient) -> None:
    series = str(client.post(f"{V1}/series", json={"title": "空"}).json()["id"])
    data = _list(client, series)
    assert data["product_id"] is None and data["suggestions"] == []
    accepted = client.post(f"{V1}/series/{series}/suggestions/accept-all").json()
    assert accepted["suggestions"] == []


def test_accepted_additions_follow_an_edited_novel(client: TestClient) -> None:
    """The novel replaced with a change in chapter 3: a rerun keeps the accepted addition on
    its paragraph in the new text, with its id and decision."""
    _act(client, "s3", "accept")
    changed = DEMO.replace("便利店里没有他。".encode(), "便利店里空无一人。".encode())
    resp = client.post(
        f"{V1}/series/demo/novel",
        files={"file": ("雨停之前.txt", changed)},
        data={"rights_confirmed": "true"},
    )
    assert resp.status_code == 200, resp.text
    source = resp.json()["source_id"]
    assert _status(client, "demo", "enrich") == "stale"
    job = _run(client, _product(client, "demo", "enrich")["id"])
    client.post(f"{V1}/versions/{job['result']['version_id']}/adopt")
    data = _by_id(_list(client))
    assert data["s1"]["status"] == data["s3"]["status"] == "accepted"
    assert data["s3"]["anchor_span"]["source_id"] == source and data["s3"]["para_idx"] == 1
    assert _status(client, "demo", "enrich") == "adopted"


def test_the_mirror_can_be_rebuilt_from_the_adopted_version(client: TestClient) -> None:
    def rows() -> list[tuple[Any, ...]]:
        return sorted(
            (r.id, r.version_id, r.kind, r.para_idx, r.text, r.retired)
            for r in _rows(client, Suggestion)
        )

    before = rows()
    assert len(before) == 4

    async def rebuild() -> None:
        async with _state(client).db.session() as s:
            for r in (await s.exec(select(Suggestion))).all():
                await s.delete(r)
            await s.commit()
            p = await suggestions.enrich_product(s, "demo")
            assert p is not None and p.adopted_version_id is not None
            v = await s.get(ProductVersion, p.adopted_version_id)
            assert v is not None
            await suggestions.materialize(s, p, v)
            await s.commit()

    _call(client, rebuild)
    assert rows() == before
