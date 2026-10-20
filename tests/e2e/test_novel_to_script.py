"""M2 acceptance (plan step 12): a new series, the demo novel imported, the four components run
in order, then both gates confirmed, against a real backend process. Each step leaves a version
and a ``model_call`` row; one run goes over the per-call cap and waits for a yes first.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import httpx
import pytest

from drama_series_agent.core.paths import REPO_ROOT

if TYPE_CHECKING:
    from conftest import Backend  # tests/e2e/conftest.py

pytestmark = pytest.mark.e2e

DEMO = (REPO_ROOT / "tests" / "fixtures" / "demo" / "雨停之前.txt").read_bytes()
HEADERS = {"X-Drama-Studio": "1"}


class Api:
    def __init__(self, backend: Backend) -> None:
        self.base = backend.base

    def get(self, path: str, **params: Any) -> Any:
        resp = httpx.get(f"{self.base}{path}", params=params or None, timeout=10)
        assert resp.status_code == 200, (path, resp.text)
        return resp.json()

    def send(self, method: str, path: str, **kwargs: Any) -> Any:
        resp = httpx.request(method, f"{self.base}{path}", headers=HEADERS, timeout=10, **kwargs)
        assert resp.status_code in (200, 201), (path, resp.text)
        return resp.json()

    def until(self, job_id: str, *states: str) -> dict[str, Any]:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            job: dict[str, Any] = self.get(f"/jobs/{job_id}")
            if job["state"] in states:
                return job
            time.sleep(0.05)
        raise AssertionError(f"job {job_id} never reached {states}")

    def product(self, owner: str, component: str) -> dict[str, Any]:
        listed: list[dict[str, Any]] = self.get("/products", owner=owner)
        return next(p for p in listed if p["component_id"] == component)

    def run(self, product_id: str) -> dict[str, Any]:
        """Run a product and wait; a run over the cap is confirmed at the price it showed."""
        job: dict[str, Any] = self.send("POST", f"/products/{product_id}/run", json={"mode": "run"})
        job = self.until(job["id"], "succeeded", "failed", "canceled", "waiting_confirm")
        if job["state"] == "waiting_confirm":
            self.send("POST", f"/jobs/{job['id']}/confirm")
            job = self.until(job["id"], "succeeded", "failed", "canceled")
        assert job["state"] == "succeeded", job
        return job

    def calls(self, job_id: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = self.get("/dev/model-calls", limit=500)
        return [c for c in rows if c["job_id"] == job_id]


def _check_step(api: Api, product: dict[str, Any], job: dict[str, Any], series: str) -> None:
    """The run made the product's adopted version, and spent through ``router.call()``."""
    after = api.get(f"/products/{product['id']}")
    version_id = job["result"]["version_id"]
    assert after["adopted_version_id"] == after["current_version_id"] == version_id
    version = next(v for v in after["versions"] if v["id"] == version_id)
    assert version["origin"] == "run" and version["model_key"]
    # One call or more (the bible: one per chunk, then the "same person?" check).
    calls = [c for c in api.calls(job["id"]) if c["status"] == "success"]
    assert calls
    assert {(c["component_id"], c["product_id"], c["series_id"]) for c in calls} == {
        (product["component_id"], product["id"], series)
    }
    assert version["model_key"] in {c["model_key"] for c in calls}


def test_new_series_from_the_novel_to_a_confirmed_script(backend: Backend) -> None:
    backend.start()
    api = Api(backend)

    series = api.send("POST", "/series", json={"title": "雨停之前（复刻）"})["id"]
    imported = api.send(
        "POST",
        f"/series/{series}/novel",
        files={"file": ("雨停之前.txt", DEMO)},
        data={"rights_confirmed": "true"},
    )
    titles = [c["title"] for c in imported["chapters"]]
    assert titles == ["第一章 红伞", "第二章 十二点", "第三章 旧发圈"]
    owner = f"series:{series}"
    assert api.product(owner, "import")["status"] == "adopted"

    # 补全 (accepted) → 设定提取 (reads the accepted additions) → 分集规划; each one's first
    # success is adopted, and nothing it read changes after it ran.
    for component in ("enrich", "extract", "split"):
        product = api.product(owner, component)
        assert product["status"] == "empty", component
        _check_step(api, product, api.run(product["id"]), series)
        if component == "enrich":
            sugs = api.get(f"/series/{series}/suggestions")["suggestions"]
            assert sugs and all(s["status"] == "pending" for s in sugs)
            api.send("POST", f"/series/{series}/suggestions/accept-all")

    assert api.get(f"/series/{series}/bible")["entities"]
    episodes = api.get(f"/series/{series}/episodes")
    assert len(episodes) == 3 and all(e["beats"] for e in episodes)
    e1 = episodes[0]["id"]

    # 剧本化 of episode 1, with the per-call cap below its estimate: it waits for a yes.
    cap = {"scope": "component", "scope_id": None, "component_id": "script"}
    api.send("PUT", "/config/override", json={**cap, "data": {"per_call_cap_usd": 0.00001}})
    script = api.product(f"episode:{e1}", "script")
    assert script["status"] == "empty"
    job = api.send("POST", f"/products/{script['id']}/run", json={"mode": "run"})
    assert job["state"] == "waiting_confirm"
    assert job["params"]["confirm"]["reason"] == "per_call"
    assert api.calls(job["id"]) == []  # nothing spent before the yes
    api.send("POST", f"/jobs/{job['id']}/confirm")
    done = api.until(job["id"], "succeeded", "failed", "canceled")
    assert done["state"] == "succeeded", done
    _check_step(api, script, done, series)
    lines = api.get(f"/episodes/{e1}/script")["lines"]
    assert lines and all(x["source_spans"] for x in lines)

    # The two gates: the novel (scope: an episode, the backend takes its series), episode 1.
    api.send("POST", "/gates/novel/confirm", json={"scope_id": e1})
    api.send("POST", "/gates/script/confirm", json={"scope_id": e1})
    steps = api.get(f"/episodes/{e1}/progress")["steps"]
    assert (steps["novel"]["state"], steps["script"]["state"]) == ("confirmed", "confirmed")
    assert api.get(f"/episodes/{episodes[1]['id']}/progress")["steps"]["script"]["state"] == (
        "not_started"
    )
    assert steps["novel"]["stale"] == steps["script"]["stale"] == 0
    # The novel gate locks the novel, the bible and the suggestions; the plan stays editable.
    for component in ("import", "enrich", "extract"):
        assert api.product(owner, component)["status"] == "locked", component
    assert api.product(owner, "split")["status"] == "adopted"
    assert api.get(f"/products/{script['id']}")["status"] == "locked"

    # Survives a restart: same versions, gates still confirmed.
    backend.kill()
    backend.start()
    steps = api.get(f"/episodes/{e1}/progress")["steps"]
    assert (steps["novel"]["state"], steps["script"]["state"]) == ("confirmed", "confirmed")
    assert api.get(f"/episodes/{e1}/script")["lines"] == lines
