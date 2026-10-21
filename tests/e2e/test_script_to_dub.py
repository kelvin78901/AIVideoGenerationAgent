"""M3 acceptance (plan step 9), against a real backend process in Mock mode: a new series from
the demo novel up to episode 1's confirmed script (as in M2), then 素材分析, a reference for every
asset (candidates, a voice's final), each one locked with its hash in ``gate_decision``, the
episode's assets gate, and 全部配音: every spoken line has its audio, and a scene runs as long as
its lines' audio.
"""

from __future__ import annotations

import json
import sqlite3
from typing import TYPE_CHECKING, Any

import pytest
from test_novel_to_script import DEMO, Api

if TYPE_CHECKING:
    from conftest import Backend  # tests/e2e/conftest.py

pytestmark = pytest.mark.e2e


def _start(api: Api, product_id: str, **body: Any) -> dict[str, Any]:
    """Run and wait; a run waiting for a yes (over a cap or the episode budget) gets one."""
    job: dict[str, Any] = api.send(
        "POST", f"/products/{product_id}/run", json={"mode": "run", **body}
    )
    job = api.until(job["id"], "succeeded", "failed", "canceled", "waiting_confirm")
    if job["state"] == "waiting_confirm":
        api.send("POST", f"/jobs/{job['id']}/confirm")
        job = api.until(job["id"], "succeeded", "failed", "canceled")
    assert job["state"] == "succeeded", job
    return job


def _confirmed_script(api: Api) -> tuple[str, str]:
    """M2's road: import, 补全 (all accepted), 设定, 确认原文, 分集, episode 1's 剧本化, 确认."""
    series = api.send("POST", "/series", json={"title": "雨停之前（M3 验收）"})["id"]
    api.send(
        "POST",
        f"/series/{series}/novel",
        files={"file": ("雨停之前.txt", DEMO)},
        data={"rights_confirmed": "true"},
    )
    owner = f"series:{series}"
    _start(api, api.product(owner, "enrich")["id"])
    api.send("POST", f"/series/{series}/suggestions/accept-all")
    _start(api, api.product(owner, "extract")["id"])
    api.send("POST", "/gates/novel/confirm", json={"scope_id": series})
    _start(api, api.product(owner, "split")["id"])
    e1 = api.get(f"/series/{series}/episodes")[0]["id"]
    _start(api, api.product(f"episode:{e1}", "script")["id"])
    api.send("POST", "/gates/script/confirm", json={"scope_id": e1})
    return series, e1


def _gates(backend: Backend, series: str) -> list[tuple[str, str, str, str]]:
    """The series' gate decisions, oldest first (the demo series has its own)."""
    with sqlite3.connect(backend.home / "studio.db") as conn:
        rows = conn.execute(
            "select gate, scope_id, action, product_hashes_json from gate_decision"
            " where series_id = ? order by decided_at",
            (series,),
        ).fetchall()
    return [(r[0], r[1], r[2], r[3]) for r in rows]


def test_from_the_script_to_a_dubbed_episode(backend: Backend) -> None:
    backend.start()
    api = Api(backend)
    series, e1 = _confirmed_script(api)

    # 素材分析 of the confirmed script: characters, scenes, props, on-screen text, voices.
    job = api.send("POST", f"/episodes/{e1}/assets/analyze")
    assert api.until(job["id"], "succeeded", "failed")["state"] == "succeeded"
    assets: list[dict[str, Any]] = api.get(f"/series/{series}/assets", episode=e1)
    kinds = {k: sum(1 for a in assets if a["kind"] == k) for k in {a["kind"] for a in assets}}
    assert kinds == {
        "character": 2,
        "scene": 3,
        "prop": 4,
        "text": 2,
        "voice": 2,
    }  # 13, as the demo
    used = [a for a in assets if a["scenes"]]  # 周屿, his voice and 楼下便利店 come later
    assert len(used) == 10

    # 素材闸门 before anything is locked: refused, with the names.
    resp = api.raw("POST", "/gates/assets/confirm", json={"scope_id": e1})
    assert resp.status_code == 409 and resp.json()["detail"]["code"] == "assets_not_locked"

    # Every asset: candidates (a voice: auditions, then its MiniMax final), then locked.
    for a in assets:
        job = _start(api, a["product_id"])
        if a["kind"] == "voice":
            draft = job["result"]["version_id"]
            params = {"source_version_id": draft, "source_idx": 0}
            _start(api, a["product_id"], where="api", params=params)
        locked = api.send("POST", f"/assets/{a['id']}/lock", json={"force": True})
        assert locked["status"] == "locked", a["name"]
        # Each run spent through router.call(): its model_call rows name the product.
        calls = [c for c in api.calls(job["id"]) if c["status"] == "success"]
        assert calls and {c["product_id"] for c in calls} == {a["product_id"]}, a["name"]

    steps = api.get(f"/episodes/{e1}/progress")["steps"]
    assert (steps["assets"]["done"], steps["assets"]["total"]) == (len(used), len(used))
    api.send("POST", "/gates/assets/confirm", json={"scope_id": e1})
    assert api.get(f"/episodes/{e1}/progress")["steps"]["assets"]["state"] == "confirmed"

    # The locks are in gate_decision with their hashes: each asset's, and the episode's.
    decisions = _gates(backend, series)
    by_asset = {
        scope: json.loads(hashes)
        for gate, scope, action, hashes in decisions
        if gate == "assets" and action == "confirm" and scope != e1
    }
    assert set(by_asset) == {a["id"] for a in assets}
    hashed = [
        len(h) == 1 and all(x.startswith("sha256:") for x in h.values()) for h in by_asset.values()
    ]
    assert all(hashed), by_asset
    episode = [
        json.loads(h) for g, s, act, h in decisions if (g, s, act) == ("assets", e1, "confirm")
    ]
    assert episode and set(episode[-1]) == {a["product_id"] for a in used}

    # 全部配音: the estimate first, then a take per spoken line.
    dub = api.get(f"/episodes/{e1}/dub")
    assert dub["total"] > 0 and dub["done"] == 0
    estimate = api.send("POST", f"/episodes/{e1}/dub", json={"dry_run": True})
    assert estimate["lines"] == dub["total"] and estimate["skipped"] == []
    started = api.send("POST", f"/episodes/{e1}/dub", json={})
    for job_id in started["jobs"]:
        assert api.until(job_id, "succeeded", "failed")["state"] == "succeeded"
    dub = api.get(f"/episodes/{e1}/dub")
    assert dub["done"] == dub["total"]
    for line in dub["lines"]:
        assert line["status"] == "done" and line["audio"]["mime"] == "audio/wav", line
        assert line["seconds"] == pytest.approx(line["audio"]["duration_s"])
    for scene in dub["scenes"]:
        mine = [
            x["audio"]["duration_s"] for x in dub["lines"] if x["scene_id"] == scene["scene_id"]
        ]
        assert scene["seconds"] == pytest.approx(sum(mine))
        assert scene["dubbed"] == scene["lines"] == len(mine)
    assert api.get(f"/episodes/{e1}/progress")["steps"]["assets"]["stale"] == 0
