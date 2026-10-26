"""关键帧 (SPEC 5 ``kf``; M4 step 3), in Mock mode: only locked references reach the model, a
local draft then an API final, confirming a shot locks its picked keyframe, the spec locks on
the first keyframe adopted, and what makes a confirmed shot 「待更新」.

The demo seeds 1-01–1-03 confirmed (a local draft and a Nano Banana Pro final each), 1-04–1-07
with a local draft only; 1-08 and 1-09 are continuous and have no keyframe.
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
from drama_series_agent.core.models_db import GateDecision, ModelCall, OutputSpecRow

LOCAL = "http://127.0.0.1"
V1 = "/api/v1"
EP1 = "demo-e1"


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


def _code(resp: Any) -> str:
    return str(resp.json()["detail"]["code"])


def _shot(client: TestClient, label: str) -> dict[str, Any]:
    shots = client.get(f"{V1}/episodes/{EP1}/shots").json()
    shot: dict[str, Any] = next(s for s in shots if s["label"] == label)
    return shot


def _kf(client: TestClient, label: str) -> dict[str, Any]:
    product: dict[str, Any] = client.get(
        f"{V1}/products/{_shot(client, label)['keyframe_product_id']}"
    ).json()
    return product


def _wait(client: TestClient, job_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 30
    while True:
        job: dict[str, Any] = client.get(f"{V1}/jobs/{job_id}").json()
        if job["state"] in ("succeeded", "failed", "canceled"):
            assert job["state"] == "succeeded", job
            return job
        assert time.monotonic() < deadline, "the job did not finish"
        time.sleep(0.02)


def _run(client: TestClient, label: str, **body: Any) -> dict[str, Any]:
    product = _kf(client, label)
    resp = client.post(f"{V1}/products/{product['id']}/run", json={"mode": "rerun", **body})
    assert resp.status_code == 200, resp.text
    _wait(client, resp.json()["id"])
    return _kf(client, label)


def test_the_demo_keyframes(client: TestClient) -> None:
    shots = client.get(f"{V1}/episodes/{EP1}/shots").json()
    assert [s["confirmed"] for s in shots] == [True] * 3 + [False] * 6
    assert not any(s["confirm_stale"] for s in shots)
    first = _kf(client, "1-01")
    assert [v["stage"] for v in first["versions"]][:2] == ["draft", "final"]
    assert first["locked_hash"] and first["status"] == "locked"
    draft = _kf(client, "1-04")
    assert [v["stage"] for v in draft["versions"]] == ["draft"] and not draft["locked_hash"]
    assert len([f for f in draft["versions"][0]["files"] if f["role"] == "candidate"]) == 3


def test_only_locked_references_are_sent(client: TestClient) -> None:
    """1-05 uses 林晚, the note (both locked) and the hair tie (not locked yet)."""
    product = _run(client, "1-05")
    version = product["versions"][-1]
    assert version["stage"] == "draft" and version["where"] == "local"
    assert version["payload"]["refs"] == ["林晚", "黄色便利贴"]
    assert version["payload"]["aspect"] == "9:16"
    sent = _prompt(client, version)
    assert "参考图 1：林晚（角色）" in sent and "旧黑发圈（未锁定" in sent
    calls = _rows(client, ModelCall, ModelCall.product_id == product["id"])
    assert calls and calls[-1].shot_id == "demo-shot-1-05" and calls[-1].episode_id == EP1


def test_a_shot_with_no_locked_picture_drafts_on_qwen_image(client: TestClient) -> None:
    """Qwen-Image-Edit 2511 only edits from references: with none locked, the local draft goes
    to Qwen-Image (``kf.model_for``); the estimate says so before the run."""
    assert _run(client, "1-05")["versions"][-1]["model_key"] == "comfy/qwen-image-edit"
    shot = _shot(client, "1-05")
    band = [a for a in shot["asset_ids"] if a == "band"]
    assert band, shot["asset_ids"]  # 旧黑发圈 is not locked in the demo
    client.patch(f"{V1}/shots/{shot['id']}", json={"asset_ids": band}).raise_for_status()
    before = _kf(client, "1-05")
    assert before["estimate"]["model_key"] == "comfy/qwen-image"
    version = _run(client, "1-05")["versions"][-1]
    assert version["model_key"] == "comfy/qwen-image" and version["stage"] == "draft"
    assert version["payload"]["refs"] == []
    assert "旧黑发圈（未锁定" in _prompt(client, version)


def test_a_shot_with_no_character_says_so(client: TestClient) -> None:
    """Left unsaid, the model adds a stranger (M4 step 9: 1-02, the umbrella at the door)."""
    phone = _prompt(client, _run(client, "1-07")["versions"][-1])
    assert "这个镜头里没有人物，不要画人。" in phone
    assert "没有人物" not in _prompt(client, _run(client, "1-05")["versions"][-1])


def _prompt(client: TestClient, version: dict[str, Any]) -> str:
    f = next(x for x in version["files"] if x["role"] == "prompt")
    return client.get(f"{V1}/files/{f['sha256']}").content.decode("utf-8")


def test_draft_then_final_then_confirm(client: TestClient) -> None:
    pick = client.patch(f"{V1}/shots/demo-shot-1-04", json={"keyframe_pick": 1}).json()
    assert pick["keyframe_pick"] == 1
    draft = _kf(client, "1-04")["versions"][-1]
    assert pick["keyframe_sha256"] == next(
        f["sha256"] for f in draft["files"] if f["role"] == "candidate" and f["idx"] == 1
    )
    assert _shot(client, "1-08")["keyframe_sha256"] is None  # continuous: no keyframe of its own
    final = _run(
        client,
        "1-04",
        mode="run",
        where="api",
        params={"source_version_id": draft["id"], "source_idx": 1},
    )
    v = final["versions"][-1]
    assert (v["stage"], v["where"], v["parent_version_id"]) == ("final", "api", draft["id"])
    assert len([f for f in v["files"] if f["role"] == "candidate"]) == 1
    shot = client.patch(f"{V1}/shots/demo-shot-1-04", json={"confirmed": True}).json()
    assert shot["confirmed"] and not shot["confirm_stale"]
    assert shot["keyframe_sha256"] == next(
        f["sha256"] for f in v["files"] if f["role"] == "candidate"
    )
    product = _kf(client, "1-04")
    assert product["locked_hash"] and product["current_version_id"] == v["id"]
    decisions = _rows(client, GateDecision, GateDecision.scope_id == "demo-shot-1-04")
    assert [d.gate for d in decisions] == ["shot"] and decisions[-1].action == "confirm"
    assert product["id"] in decisions[-1].product_hashes_json
    # A confirmed shot is not edited in place: that goes through the impact preview.
    resp = client.patch(f"{V1}/shots/demo-shot-1-04", json={"framing": "wide"})
    assert resp.status_code == 409 and _code(resp) == "shot_confirmed"
    # Taking it back unlocks the keyframe.
    back = client.patch(f"{V1}/shots/demo-shot-1-04", json={"confirmed": False}).json()
    assert not back["confirmed"] and not _kf(client, "1-04")["locked_hash"]
    assert client.patch(f"{V1}/shots/demo-shot-1-04", json={"framing": "wide"}).status_code == 200


def test_a_shot_without_a_keyframe_cannot_be_confirmed(client: TestClient) -> None:
    after = client.post(f"{V1}/shots/demo-shot-1-04/split", json={}).json()
    resp = client.patch(f"{V1}/shots/{after[4]['id']}", json={"confirmed": True})
    assert resp.status_code == 409 and _code(resp) == "nothing_to_confirm"
    # A continuous shot has none to make: it confirms as it is.
    shot = client.patch(f"{V1}/shots/demo-shot-1-08", json={"confirmed": True}).json()
    assert shot["confirmed"] and shot["keyframe_product_id"] is None


def test_the_first_keyframe_adopted_locks_the_spec(client: TestClient) -> None:
    state = _state(client)

    async def unlock_spec() -> None:
        async with state.db.session() as s:
            row = await s.get(OutputSpecRow, "demo")
            assert row is not None
            row.locked_at = None
            s.add(row)
            await s.commit()

    client.portal.call(unlock_spec)  # type: ignore[union-attr]
    assert client.get(f"{V1}/series/demo/spec").json()["locked_at"] is None
    client.patch(f"{V1}/shots/demo-shot-1-05", json={"confirmed": True}).raise_for_status()
    locked = client.get(f"{V1}/series/demo/spec").json()["locked_at"]
    assert locked is not None
    client.patch(f"{V1}/shots/demo-shot-1-06", json={"confirmed": True}).raise_for_status()
    assert client.get(f"{V1}/series/demo/spec").json()["locked_at"] == locked


def test_a_new_reference_picture_makes_the_confirmed_shot_stale(client: TestClient) -> None:
    """1-01 was drawn with 林晚's locked picture; locking another one makes it 待更新."""
    preview = client.post(
        f"{V1}/impact/preview", json={"kind": "asset_unlock", "target_id": "linwan", "patch": {}}
    ).json()
    client.post(f"{V1}/impact/apply", json={"impact_id": preview["id"], "action": "mark"})
    assert not _shot(client, "1-01")["confirm_stale"]  # nothing new locked yet
    body = {"version_id": "demo-p-asset-linwan-v1", "idx": 2}
    client.post(f"{V1}/assets/linwan/lock", json=body).raise_for_status()
    first = _shot(client, "1-01")
    assert first["confirmed"] and first["confirm_stale"]
    assert _kf(client, "1-01")["status"] == "stale"
    assert not _shot(client, "1-02")["confirm_stale"]  # no 林晚 in it


def test_a_keyframe_for_the_old_aspect_is_stale(client: TestClient) -> None:
    state = _state(client)

    async def widen() -> None:  # what 改画幅 writes (its impact preview is step 4's)
        async with state.db.session() as s:
            row = await s.get(OutputSpecRow, "demo")
            assert row is not None
            row.aspect = "16:9"
            s.add(row)
            await s.commit()

    client.portal.call(widen)  # type: ignore[union-attr]
    shots = client.get(f"{V1}/episodes/{EP1}/shots").json()
    assert [s["confirm_stale"] for s in shots][:3] == [True] * 3
    assert _kf(client, "1-04")["status"] == "stale"
