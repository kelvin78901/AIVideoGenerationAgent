"""Gates and change impact (SPEC 9.1 ``/gates/…``, ``/impact/…``; M2 plan step 10a).

The demo series is seeded with the whole chain adopted: novel → bible, suggestions → plan →
episode 1's script (episodes 2 and 3 have no script yet). Confirming a gate locks what it
covers; an edit of locked work is previewed (what changes downstream, at what price), then
marked (written; staleness follows) or undone.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import select

from drama_series_agent.api.app import create_app
from drama_series_agent.api.state import StudioState
from drama_series_agent.core.models_db import GateDecision, Product, ProductVersion

LOCAL = "http://127.0.0.1"
V1 = "/api/v1"
NOVEL, BIBLE, ENRICH = "demo-novel", "demo-p-extract", "demo-p-enrich"
SPLIT, SCRIPT1, SCRIPT2 = "demo-p-split", "demo-p-script-e1", "demo-p-script-e2"


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


def _product(client: TestClient, product_id: str) -> dict[str, Any]:
    resp = client.get(f"{V1}/products/{product_id}")
    assert resp.status_code == 200, resp.text
    data: dict[str, Any] = resp.json()
    return data


def _row(client: TestClient, product_id: str) -> Product:
    async def read() -> Product:
        async with _state(client).db.session() as s:
            p = await s.get(Product, product_id)
        assert p is not None
        return p

    p: Product = _call(client, read)
    return p


def _adopted(client: TestClient, product_id: str) -> ProductVersion:
    async def read() -> ProductVersion:
        async with _state(client).db.session() as s:
            p = await s.get(Product, product_id)
            assert p is not None and p.adopted_version_id
            v = await s.get(ProductVersion, p.adopted_version_id)
        assert v is not None
        return v

    v: ProductVersion = _call(client, read)
    return v


def _gate(client: TestClient, gate: str, action: str, scope: str) -> dict[str, Any]:
    resp = client.post(f"{V1}/gates/{gate}/{action}", json={"scope_id": scope})
    assert resp.status_code == 200, resp.text
    data: dict[str, Any] = resp.json()
    return data


def _progress(client: TestClient, episode: str = "demo-e1") -> dict[str, Any]:
    steps: dict[str, Any] = client.get(f"{V1}/episodes/{episode}/progress").json()["steps"]
    return steps


def _preview(client: TestClient, kind: str, target: str, patch: dict[str, Any]) -> dict[str, Any]:
    resp = client.post(
        f"{V1}/impact/preview", json={"kind": kind, "target_id": target, "patch": patch}
    )
    assert resp.status_code == 200, resp.text
    data: dict[str, Any] = resp.json()
    return data


def _apply(client: TestClient, impact_id: str, action: str) -> Any:
    return client.post(f"{V1}/impact/apply", json={"impact_id": impact_id, "action": action})


def _codes(impact: dict[str, Any]) -> list[tuple[str, dict[str, Any], bool]]:
    return [(x["code"], x["params"], x["optional"]) for x in impact["lines"]]


def _chapter(client: TestClient, idx: int) -> dict[str, Any]:
    data: dict[str, Any] = client.get(f"{V1}/series/demo/novel", params={"chapter": idx}).json()
    return data


def _versions(client: TestClient, product_id: str) -> int:
    return len(_product(client, product_id)["versions"])


def _wait(client: TestClient, job_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        job: dict[str, Any] = client.get(f"{V1}/jobs/{job_id}").json()
        if job["state"] in ("succeeded", "failed", "canceled"):
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


# --------------------------------------------------------------------------- gates


def test_novel_gate_locks_the_novel_step_of_the_series(client: TestClient) -> None:
    decision = _gate(client, "novel", "confirm", "demo-e2")  # an episode: its series'
    assert decision["scope_id"] == "demo" and decision["action"] == "confirm"
    for pid in (NOVEL, BIBLE, ENRICH):
        assert _product(client, pid)["status"] == "locked"
        assert _row(client, pid).locked_hash == _adopted(client, pid).content_hash
    assert _product(client, SPLIT)["status"] != "locked"
    assert _progress(client, "demo-e1")["novel"]["state"] == "confirmed"

    async def rows() -> list[GateDecision]:
        async with _state(client).db.session() as s:
            return list((await s.exec(select(GateDecision))).all())

    (row,) = _call(client, rows)
    assert set(row.product_hashes_json) == {NOVEL, BIBLE, ENRICH}
    # Confirming again is the same decision.
    assert _gate(client, "novel", "confirm", "demo")["id"] == decision["id"]

    # Locked: direct edits are refused, they go through the impact preview.
    chapter = _chapter(client, 0)
    paras = [p["text"] for p in chapter["paragraphs"]]
    edit = {"title": chapter["chapters"][0]["title"], "paragraphs": ["改过的第一段。", *paras[1:]]}
    resp = client.put(f"{V1}/series/demo/novel/chapters/0", json=edit)
    assert resp.status_code == 409 and _code(resp) == "product_locked"
    resp = client.patch(f"{V1}/bible/c-clerk", json={"name": "店员"})
    assert resp.status_code == 409 and _code(resp) == "product_locked"
    sid = client.get(f"{V1}/series/demo/suggestions").json()["suggestions"][1]["id"]
    resp = client.post(f"{V1}/suggestions/{sid}/reject")
    assert resp.status_code == 409 and _code(resp) == "product_locked"

    reopened = _gate(client, "novel", "reopen", "demo-e1")
    assert reopened["action"] == "reopen" and reopened["decided_at"] > decision["decided_at"]
    assert _product(client, NOVEL)["status"] == "adopted"
    assert _progress(client)["novel"]["state"] == "in_progress"
    assert client.patch(f"{V1}/bible/c-clerk", json={"name": "店员"}).status_code == 200


def test_script_gate_is_per_episode(client: TestClient) -> None:
    resp = client.post(f"{V1}/gates/script/confirm", json={"scope_id": "demo-e2"})
    assert resp.status_code == 409 and _code(resp) == "nothing_adopted"  # no script yet
    _gate(client, "script", "confirm", "demo-e1")
    assert _product(client, SCRIPT1)["status"] == "locked"
    assert _progress(client)["script"]["state"] == "confirmed"
    listed = client.get(f"{V1}/series/demo/episodes").json()
    assert [e["script_status"] for e in listed] == ["confirmed", "none", "none"]
    resp = client.patch(f"{V1}/lines/demo-b2", json={"text": "改一行。"})
    assert resp.status_code == 409 and _code(resp) == "product_locked"
    _gate(client, "script", "reopen", "demo-e1")
    assert client.patch(f"{V1}/lines/demo-b2", json={"text": "改一行。"}).status_code == 200


def test_gate_errors(client: TestClient) -> None:
    resp = client.post(f"{V1}/gates/assets/confirm", json={"scope_id": "demo-e1"})
    assert resp.status_code == 404 and _code(resp) == "unknown_gate"
    resp = client.post(f"{V1}/gates/script/confirm", json={"scope_id": "demo"})
    assert resp.status_code == 404 and _code(resp) == "episode_not_found"
    resp = client.post(f"{V1}/gates/novel/confirm", json={"scope_id": "nope"})
    assert resp.status_code == 404 and _code(resp) == "episode_not_found"


# --------------------------------------------------------------------------- impact


def test_editing_a_confirmed_script_line(client: TestClient) -> None:
    _gate(client, "script", "confirm", "demo-e1")
    before = _versions(client, SCRIPT1)
    impact = _preview(client, "line_edit", "demo-b2", {"text": "她把伞靠在门边。"})
    # Nothing is downstream of a script in M2, but the dialog always says what changes.
    assert _codes(impact) == [("self_script", {"n": 1}, False)]
    assert impact["stale"] == {} and impact["rerun_cost_usd"] == 0
    assert impact["change"]["kind"] == "line_edit"
    assert _versions(client, SCRIPT1) == before  # a preview writes nothing

    # 撤销: nothing written, the preview is gone.
    assert _apply(client, impact["id"], "undo").json() == {
        "action": "undo",
        "stale": {},
        "job_ids": [],
    }
    assert _versions(client, SCRIPT1) == before
    assert _apply(client, impact["id"], "mark").status_code == 404

    # 只改这里: an adopted edit, still locked on the new content; the gate stays confirmed.
    impact = _preview(client, "line_edit", "demo-b2", {"text": "她把伞靠在门边。"})
    resp = _apply(client, impact["id"], "mark")
    assert resp.status_code == 200, resp.text
    assert resp.json()["action"] == "mark"
    adopted = _adopted(client, SCRIPT1)
    assert adopted.origin == "edit" and _versions(client, SCRIPT1) == before + 1
    assert _row(client, SCRIPT1).locked_hash == adopted.content_hash
    script = client.get(f"{V1}/episodes/demo-e1/script").json()
    line = next(x for x in script["lines"] if x["id"] == "demo-b2")
    assert line["text"] == "她把伞靠在门边。" and line["edited"]
    assert _progress(client)["script"]["state"] == "confirmed"

    # The same text again changes nothing: no line, and marking writes nothing.
    impact = _preview(client, "line_edit", "demo-b2", {"text": "她把伞靠在门边。"})
    assert impact["lines"] == []
    assert _apply(client, impact["id"], "mark").status_code == 200
    assert _versions(client, SCRIPT1) == before + 1

    # A scene heading: the page sends the block's text.
    impact = _preview(client, "scene_edit", "demo-b1", {"text": "老小区楼道 · 深夜"})
    assert _codes(impact) == [("self_script", {"n": 1}, False)]
    assert _apply(client, impact["id"], "mark").status_code == 200
    script = client.get(f"{V1}/episodes/demo-e1/script").json()
    assert script["scenes"][0]["heading"] == "老小区楼道 · 深夜"


def test_applying_an_outdated_preview_is_refused(client: TestClient) -> None:
    _gate(client, "script", "confirm", "demo-e1")
    first = _preview(client, "line_edit", "demo-b2", {"text": "第一种改法。"})
    second = _preview(client, "line_edit", "demo-b3", {"text": "另一行先改了。"})
    assert _apply(client, second["id"], "mark").status_code == 200
    resp = _apply(client, first["id"], "mark")
    assert resp.status_code == 409 and _code(resp) == "impact_outdated"


def test_editing_a_confirmed_novel_chapter(client: TestClient) -> None:
    _gate(client, "novel", "confirm", "demo-e1")
    _gate(client, "script", "confirm", "demo-e1")
    chapter = _chapter(client, 0)
    paras = [p["text"] for p in chapter["paragraphs"]]
    patch = {
        "chapter": 0,
        "title": chapter["chapters"][0]["title"],
        "paragraphs": [paras[0] + "楼道的灯又闪了一下。", *paras[1:]],
    }
    impact = _preview(client, "novel_edit", "demo", patch)
    codes = _codes(impact)
    assert codes[0] == ("self_novel", {}, False)
    # Everything read chapter 1: all of it directly, episode 1's script through chapter:0.
    assert [c for c, _, opt in codes if c.startswith("stale_")] == [
        "stale_suggestions",
        "stale_bible",
        "stale_episodes",
        "stale_script",
    ]
    assert ("gate_novel", {}, False) in codes and ("gate_script", {"n": 1}, False) in codes
    assert not any(c.startswith("then_") for c, _, _ in codes)
    assert impact["stale"] == {"novel": 2, "script": 2}
    priced = [x["cost_usd"] for x in impact["lines"] if x["cost_usd"] is not None]
    assert priced and impact["rerun_cost_usd"] == pytest.approx(sum(priced), abs=1e-4)
    script_line = next(x for x in impact["lines"] if x["code"] == "stale_script")
    assert script_line["params"] == {"n": 1} and script_line["cost_usd"] > 0  # Kimi / DeepSeek

    resp = _apply(client, impact["id"], "mark")
    assert resp.status_code == 200, resp.text
    assert resp.json()["stale"] == {"novel": 2, "script": 2}
    novel = _adopted(client, NOVEL)
    assert novel.origin == "edit" and _row(client, NOVEL).locked_hash == novel.content_hash
    assert _chapter(client, 0)["paragraphs"][0]["text"].endswith("楼道的灯又闪了一下。")
    for pid in (BIBLE, ENRICH, SPLIT, SCRIPT1):
        assert _product(client, pid)["status"] == "stale", pid
    steps = _progress(client)
    assert steps["novel"] == {**steps["novel"], "state": "confirmed", "stale": 2}
    assert steps["script"]["stale"] == 2


def test_a_chapter_episode_one_does_not_read_affects_its_script_further_down(
    client: TestClient,
) -> None:
    chapter = _chapter(client, 2)
    paras = [p["text"] for p in chapter["paragraphs"]]
    patch = {"chapter": 2, "title": chapter["chapters"][2]["title"], "paragraphs": paras[:-1]}
    codes = _codes(_preview(client, "novel_edit", "demo", patch))
    assert ("self_novel", {}, False) not in codes  # not confirmed: no such line
    assert ("stale_script", {"n": 1}, False) not in codes
    assert ("then_script", {"n": 1}, True) in codes  # only if the plan or the bible change


def test_moving_a_beat_affects_both_episodes(client: TestClient) -> None:
    resp = client.post(f"{V1}/products/{SCRIPT2}/run", json={"mode": "run"})
    assert resp.status_code == 200, resp.text
    assert _wait(client, resp.json()["id"])["state"] == "succeeded"
    _gate(client, "script", "confirm", "demo-e1")
    impact = _preview(client, "beat_move", "demo-bt5", {"episode_id": "demo-e2", "position": 0})
    assert _codes(impact) == [
        ("stale_script", {"n": 1}, False),
        ("stale_script", {"n": 2}, False),
        ("gate_script", {"n": 1}, False),
    ]
    assert impact["stale"] == {"script": 2}
    assert _apply(client, impact["id"], "mark").status_code == 200
    episodes = client.get(f"{V1}/series/demo/episodes").json()
    assert episodes[1]["beats"][0]["id"] == "demo-bt5"
    assert _product(client, SCRIPT1)["status"] == "stale"
    assert _product(client, SCRIPT2)["status"] == "stale"


def test_a_decision_on_a_confirmed_novel(client: TestClient) -> None:
    _gate(client, "novel", "confirm", "demo-e1")
    suggestions = client.get(f"{V1}/series/demo/suggestions").json()["suggestions"]
    pending = next(s for s in suggestions if s["status"] == "pending")
    # The staged decision is rolled back: previewing and undoing leaves it undecided.
    undone = _preview(client, "suggestion_decision", pending["id"], {"action": "accept"})
    assert _apply(client, undone["id"], "undo").status_code == 200
    again = client.get(f"{V1}/series/demo/suggestions").json()["suggestions"]
    assert next(s for s in again if s["id"] == pending["id"])["status"] == "pending"
    assert _product(client, BIBLE)["status"] == "locked"

    impact = _preview(client, "suggestion_decision", pending["id"], {"action": "accept"})
    codes = [c for c, _, _ in _codes(impact)]
    assert codes[0] == "self_suggestions"
    assert "stale_bible" in codes and "stale_episodes" in codes
    assert "stale_suggestions" not in codes
    assert _apply(client, impact["id"], "mark").status_code == 200
    after = client.get(f"{V1}/series/demo/suggestions").json()["suggestions"]
    assert next(s for s in after if s["id"] == pending["id"])["status"] == "accepted"
    assert _product(client, ENRICH)["status"] == "locked"
    assert _product(client, BIBLE)["status"] == "stale"


def test_editing_a_confirmed_bible(client: TestClient) -> None:
    _gate(client, "novel", "confirm", "demo-e1")
    # Frozen entries are part of the ``names`` slice (given in full to whatever must not
    # contradict them); in the demo the plan reads it (the seeded suggestions predate the bible).
    frozen = _preview(client, "bible_edit", "c-clerk", {"frozen": True})
    codes = _codes(frozen)
    assert codes[0] == ("self_bible", {}, False)
    assert [c for c, _, _ in codes if c.startswith("stale_")] == ["stale_episodes"]
    renamed = _preview(client, "bible_edit", "c-clerk", {"name": "便利店的店员"})
    codes = [c for c, _, _ in _codes(renamed)]
    assert codes[0] == "self_bible" and "stale_episodes" in codes
    assert _apply(client, renamed["id"], "mark").status_code == 200
    bible = client.get(f"{V1}/series/demo/bible").json()["entities"]
    assert next(e for e in bible if e["id"] == "c-clerk")["name"] == "便利店的店员"
    merge = _preview(
        client, "bible_merge", "c-linwan", {"action": "distinct", "ids": ["c-linwan", "c-zhouyu"]}
    )
    assert merge["change"]["kind"] == "bible_merge"


def test_replacing_a_confirmed_novel(client: TestClient) -> None:
    _gate(client, "novel", "confirm", "demo-e1")
    original = (_state(client).store.read_bytes(_chapter_source_sha(client))).decode("utf-8")
    changed = original.replace("林晚", "林晓", 1).encode("utf-8")
    dry = client.post(
        f"{V1}/series/demo/novel",
        files={"file": ("雨停之前.txt", changed, "text/plain")},
        data={"dry_run": "true"},
    )
    assert dry.status_code == 200, dry.text
    upload = dry.json()["upload_id"]
    patch = {"upload_id": upload, "filename": "雨停之前.txt"}
    impact = _preview(client, "novel_replace", "demo", patch)
    assert _codes(impact)[0] == ("self_novel", {}, False)
    assert _apply(client, impact["id"], "mark").status_code == 200
    novel = _adopted(client, NOVEL)
    assert novel.origin == "import" and _row(client, NOVEL).locked_hash == novel.content_hash
    # The same file again changes nothing.
    again = _preview(client, "novel_replace", "demo", patch)
    assert again["lines"] == []
    resp = client.post(
        f"{V1}/impact/preview",
        json={
            "kind": "novel_replace",
            "target_id": "demo",
            "patch": {"upload_id": "0" * 64, "filename": "x.txt"},
        },
    )
    assert resp.status_code == 404 and _code(resp) == "upload_not_found"


def _chapter_source_sha(client: TestClient) -> str:
    sha: str = client.get(f"{V1}/series/demo/novel").json()["source"]["sha256"]
    return sha


def test_impact_errors(client: TestClient) -> None:
    resp = client.post(
        f"{V1}/impact/preview", json={"kind": "nope", "target_id": "demo-b2", "patch": {}}
    )
    assert resp.status_code == 422 and _code(resp) == "unknown_change_kind"
    resp = client.post(
        f"{V1}/impact/preview",
        json={"kind": "line_edit", "target_id": "demo-b2", "patch": {"txt": "x"}},
    )
    assert resp.status_code == 422 and _code(resp) == "invalid_patch"
    resp = client.post(
        f"{V1}/impact/preview",
        json={"kind": "line_edit", "target_id": "nope", "patch": {"text": "x"}},
    )
    assert resp.status_code == 404 and _code(resp) == "line_not_found"
    assert _apply(client, "imp-nope", "mark").status_code == 404
