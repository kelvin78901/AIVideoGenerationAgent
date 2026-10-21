"""参考图, 补视图, upload and lock (SPEC 5 ``img`` / ``views``, 9.1 ``/assets/{id}/lock|upload``;
M3 step 3), all in Mock mode.

The demo seeds the prototype's candidates: 7 of the 13 assets locked, each with its own gate
decision, and 林晚's views drawn from her locked picture.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import select

from drama_series_agent.api.app import create_app
from drama_series_agent.api.state import StudioState
from drama_series_agent.core.models_db import Dependency, GateDecision, ModelCall, Product
from drama_series_agent.modelhub.adapters.mock import gradient_png
from drama_series_agent.pipeline.component import RunContext
from drama_series_agent.pipeline.components.media import MediaCall, MediaComponent
from drama_series_agent.pipeline.hashing import hash_json
from drama_series_agent.spec.dims import dims

LOCAL = "http://127.0.0.1"
V1 = "/api/v1"
LOCKED = {"linwan", "hall", "umbrella", "note", "phone", "txt2", "vlinwan"}


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(), base_url=LOCAL, headers={"X-Drama-Studio": "1"}) as c:
        yield c


def _state(client: TestClient) -> StudioState:
    state: StudioState = client.app.state.studio  # type: ignore[attr-defined]
    return state


def _rows(client: TestClient, model: Any) -> list[Any]:
    async def read() -> list[Any]:
        async with _state(client).db.session() as s:
            return list((await s.exec(select(model))).all())

    return list(client.portal.call(read))  # type: ignore[union-attr]


def _code(resp: Any) -> str:
    return str(resp.json()["detail"]["code"])


def _wait(client: TestClient, job_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        job: dict[str, Any] = client.get(f"{V1}/jobs/{job_id}").json()
        if job["state"] in ("succeeded", "failed", "canceled"):
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def _until(client: TestClient, product_id: str, ok: Callable[[dict[str, Any]], bool]) -> Any:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        resp = client.get(f"{V1}/products/{product_id}")
        if resp.status_code == 200 and ok(resp.json()):
            return resp.json()
        time.sleep(0.02)
    raise AssertionError(f"{product_id} never got there")


def _asset(client: TestClient, asset_id: str) -> dict[str, Any]:
    listed = client.get(f"{V1}/series/demo/assets", params={"episode": "demo-e1"}).json()
    return next(a for a in listed if a["id"] == asset_id)


def _product(client: TestClient, asset_id: str) -> dict[str, Any]:
    product: dict[str, Any] = client.get(f"{V1}/products/demo-p-asset-{asset_id}").json()
    return product


def _run(client: TestClient, asset_id: str, **body: Any) -> dict[str, Any]:
    resp = client.post(f"{V1}/products/demo-p-asset-{asset_id}/run", json={"mode": "run", **body})
    assert resp.status_code == 200, resp.text
    job = _wait(client, resp.json()["id"])
    assert job["state"] == "succeeded", job
    return job


def _gates(client: TestClient, scope: str) -> list[GateDecision]:
    rows = [g for g in _rows(client, GateDecision) if g.gate == "assets" and g.scope_id == scope]
    return sorted(rows, key=lambda g: g.decided_at)


def _file_hash(sha: str, candidate: dict[str, Any] | None = None) -> str:
    """The hash a locked picture has: the pick's payload (what the candidate is, e.g. the text
    OCR read on it) and that one file."""
    return hash_json({"payload": {"candidate": candidate or {}}, "files": [sha]})


def _locked_file(product: dict[str, Any]) -> dict[str, Any]:
    adopted = next(v for v in product["versions"] if v["id"] == product["adopted_version_id"])
    assert adopted["origin"] == "pick"
    return next(f for f in adopted["files"] if f["role"] == "ref")


def test_the_demo_locks_seven_with_their_gate_decisions(client: TestClient) -> None:
    listed = client.get(f"{V1}/series/demo/assets", params={"episode": "demo-e1"}).json()
    status = {a["id"]: a["status"] for a in listed}
    assert {k for k, v in status.items() if v == "locked"} == LOCKED
    assert {k for k, v in status.items() if v == "choosing"} == {"room", "band", "txt1"}
    linwan = _product(client, "linwan")
    v1, v2, pick = linwan["versions"]
    assert (v1["stage"], v1["where"], len(v1["files"])) == ("draft", "local", 4)
    assert (v2["stage"], v2["model_key"], v2["parent_version_id"]) == (
        "final", "google/nano-banana-pro", v1["id"]
    )  # fmt: skip
    assert linwan["current_version_id"] == v2["id"]  # the grid still shows where it came from
    assert (pick["origin"], pick["parent_version_id"]) == ("pick", v2["id"])
    assert linwan["adopted_version_id"] == pick["id"]
    ref = _locked_file(linwan)
    assert ref["sha256"] == v2["files"][0]["sha256"]
    for asset_id in LOCKED - {"vlinwan"}:
        product = _product(client, asset_id)
        (decision,) = _gates(client, asset_id)
        assert decision.action == "confirm"
        adopted = next(v for v in product["versions"] if v["origin"] == "pick")
        assert decision.product_hashes_json == {
            product["id"]: _file_hash(
                _locked_file(product)["sha256"], adopted["payload"]["candidate"]
            )
        }
    # A voice's final is locked whole: the anchor and every emotion.
    voice = _product(client, "vlinwan")
    final = next(v for v in voice["versions"] if v["id"] == voice["adopted_version_id"])
    assert (final["stage"], final["origin"]) == ("final", "run")
    shas = sorted(f["sha256"] for f in final["files"] if f["role"] != "prompt")
    (decision,) = _gates(client, "vlinwan")
    assert decision.product_hashes_json == {
        voice["id"]: hash_json({"payload": final["payload"], "files": shas})
    }
    views = _until(client, "demo-p-views-linwan", lambda p: p["status"] == "adopted")
    assert [f["view"] for f in views["versions"][0]["files"]] == ["side", "back", "expressions"]
    # The pictures are real files.
    resp = client.get(f"{V1}/files/{ref['sha256']}")
    assert resp.status_code == 200 and resp.headers["content-type"] == "image/png"


def test_draft_then_api_final_then_lock(client: TestClient) -> None:
    job = _run(client, "room")
    assert job["queue"] == "gpu"  # hybrid: the draft is local
    room = _product(client, "room")
    draft = room["versions"][-1]
    assert draft["id"] == room["current_version_id"] != room["adopted_version_id"]
    assert draft["stage"] == "draft" and draft["model_key"] == "comfy/qwen-image"
    cands = [f for f in draft["files"] if f["role"] == "candidate"]
    assert [f["idx"] for f in cands] == [0, 1, 2, 3]
    assert (cands[0]["w"], cands[0]["h"]) == (768, 1366)  # 9:16 at the draft tier
    assert client.patch(f"{V1}/assets/room", json={"pick": 2}).json()["pick"] == 2

    params = {"source_version_id": draft["id"], "source_idx": 2}
    job = _run(client, "room", where="api", params=params)
    assert job["queue"] == "api:google"
    room = _product(client, "room")
    final = room["versions"][-1]
    assert (final["stage"], final["parent_version_id"]) == ("final", draft["id"])
    assert final["model_key"] == "google/nano-banana-pro" and final["cost_usd"] == 0.134
    (one,) = [f for f in final["files"] if f["role"] == "candidate"]
    assert (one["w"], one["h"]) == (1080, 1920)  # the delivery tier
    assert room["adopted_version_id"] is None  # nothing adopted before the lock
    call = next(c for c in _rows(client, ModelCall) if c.model_key == "google/nano-banana-pro")
    assert call.product_id == room["id"] and call.images == 1

    resp = client.post(f"{V1}/assets/room/lock")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "locked"
    room = _product(client, "room")
    ref = _locked_file(room)
    assert ref["sha256"] == one["sha256"] and room["current_version_id"] == final["id"]
    assert room["locked_hash"] == _file_hash(one["sha256"])
    (decision,) = _gates(client, "room")
    assert decision.product_hashes_json == {room["id"]: _file_hash(one["sha256"])}
    assert _code(client.post(f"{V1}/assets/room/lock")) == "product_locked"


def test_upload_then_lock(client: TestClient) -> None:
    png = gradient_png(60, 100, (200, 40, 40))
    files = {"file": ("band.png", png, "image/png")}
    resp = client.post(f"{V1}/assets/band/upload", files=files)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "choosing" and resp.json()["pick"] == 0
    band = _product(client, "band")
    upload = band["versions"][-1]
    assert upload["origin"] == "upload" and upload["id"] == band["current_version_id"]
    (f,) = upload["files"]
    assert (f["role"], f["w"], f["h"], f["mime"]) == ("candidate", 60, 100, "image/png")
    assert band["adopted_version_id"] is None
    assert client.post(f"{V1}/assets/band/lock").status_code == 200
    band = _product(client, "band")
    assert _locked_file(band)["sha256"] == f["sha256"]
    (decision,) = _gates(client, "band")
    assert decision.product_hashes_json == {band["id"]: _file_hash(f["sha256"])}
    # Locking the same picture from any version gives the same hash.
    assert band["locked_hash"] == _file_hash(f["sha256"])


def test_upload_errors(client: TestClient) -> None:
    def up(asset_id: str, data: bytes) -> Any:
        return client.post(f"{V1}/assets/{asset_id}/upload", files={"file": ("x", data)})

    png = gradient_png(4, 4, (0, 0, 0))
    assert _code(up("room", b"not a picture")) == "not_an_image"
    assert _code(up("vzhouyu", png)) == "upload_not_supported"
    assert _code(up("linwan", png)) == "product_locked"
    assert up("nope", png).status_code == 404


def test_lock_errors(client: TestClient) -> None:
    assert _code(client.post(f"{V1}/assets/store/lock")) == "nothing_to_lock"
    assert _code(client.post(f"{V1}/assets/room/lock", json={"idx": 9})) == "no_such_candidate"
    assert client.post(f"{V1}/assets/nope/lock").status_code == 404


def test_views_follow_the_locked_hash(client: TestClient) -> None:
    _run(client, "zhouyu")
    client.post(f"{V1}/assets/zhouyu/lock", json={"idx": 1}).raise_for_status()
    first = _product(client, "zhouyu")
    views = _until(client, _views_id(client, "zhouyu"), lambda p: p["status"] == "adopted")
    v1 = views["versions"][-1]
    assert len([f for f in v1["files"] if f["role"] == "view"]) == 3
    deps = [d for d in _rows(client, Dependency) if d.version_id == v1["id"]]
    assert [(d.upstream_product_id, d.upstream_hash) for d in deps] == [
        (first["id"], _file_hash(_locked_file(first)["sha256"]))
    ]
    calls = [c for c in _rows(client, ModelCall) if c.product_id == views["id"]]
    assert len(calls) == 3 and {c.model_key for c in calls} == {"comfy/qwen-image-edit"}

    # Unlock, lock another picture: the views are drawn again from it.
    preview = client.post(
        f"{V1}/impact/preview", json={"kind": "asset_unlock", "target_id": "zhouyu", "patch": {}}
    ).json()
    assert [line["code"] for line in preview["lines"]] == ["uses_ref_views"]
    assert preview["lines"][0]["params"] == {"name": "周屿"}
    assert preview["unaffected"]["code"] == "unlock_keeps_ref" and preview["stale"] == {}
    applied = client.post(f"{V1}/impact/apply", json={"impact_id": preview["id"], "action": "mark"})
    assert applied.status_code == 200, applied.text
    assert _asset(client, "zhouyu")["status"] == "choosing"
    assert [g.action for g in _gates(client, "zhouyu")] == ["confirm", "reopen"]
    views_now = client.get(f"{V1}/products/{views['id']}").json()
    assert views_now["status"] == "adopted"  # unlocking alone changes nothing downstream

    client.post(f"{V1}/assets/zhouyu/lock", json={"idx": 2}).raise_for_status()
    second = _product(client, "zhouyu")
    views = _until(client, views["id"], lambda p: len(p["versions"]) == 2 and not p["running"])
    v2 = views["versions"][-1]
    assert views["adopted_version_id"] == v2["id"] and views["status"] == "adopted"
    (dep,) = [d for d in _rows(client, Dependency) if d.version_id == v2["id"]]
    assert dep.upstream_hash == _file_hash(_locked_file(second)["sha256"]) != deps[0].upstream_hash


def _views_id(client: TestClient, asset_id: str) -> str:
    listed = client.get(f"{V1}/products", params={"owner": f"asset:{asset_id}"}).json()
    return str(next(p["id"] for p in listed if p["slot"] == "ref_views"))


def test_a_prop_takes_the_locked_characters_it_names(client: TestClient) -> None:
    # 旧黑发圈: 「戴在林晚左手腕上」, and 林晚 is locked.
    _run(client, "band")
    band = _product(client, "band")
    latest = band["versions"][-1]
    assert latest["payload"]["refs"] == ["林晚"]
    linwan = _product(client, "linwan")
    deps = [d for d in _rows(client, Dependency) if d.version_id == latest["id"]]
    assert [d.upstream_product_id for d in deps] == [linwan["id"]]
    call = [c for c in _rows(client, ModelCall) if c.product_id == band["id"]][-1]
    assert call.component_id == "img"

    # Unlocking 林晚 lists the prop and her views.
    preview = client.post(
        f"{V1}/impact/preview", json={"kind": "asset_unlock", "target_id": "linwan", "patch": {}}
    ).json()
    lines = {line["code"]: line["params"] for line in preview["lines"]}
    assert lines == {
        "uses_ref_image": {"count": 1, "names": "旧黑发圈"},
        "uses_ref_views": {"name": "林晚"},
    }
    client.post(f"{V1}/impact/apply", json={"impact_id": preview["id"], "action": "undo"})
    assert _asset(client, "linwan")["status"] == "locked"

    # A scene never takes a character, and an unlocked character is never a reference.
    _run(client, "room")
    assert _product(client, "room")["versions"][-1]["payload"]["refs"] == []


def test_unlock_needs_a_lock(client: TestClient) -> None:
    resp = client.post(
        f"{V1}/impact/preview", json={"kind": "asset_unlock", "target_id": "room", "patch": {}}
    )
    assert _code(resp) == "not_locked"


def test_a_run_starts_from_the_description(client: TestClient) -> None:
    _run(client, "store")
    store = _product(client, "store")
    v = store["versions"][-1]
    assert v["intent"] == _asset(client, "store")["intent"] != ""
    assert "[描述] " + v["intent"] in v["compiled"]


def test_views_fall_back_as_a_set(client: TestClient) -> None:
    """One view failing locally draws all three again on the fallback model."""
    _state(client).registry.mock_settings.fail_keys.add("comfy/qwen-image-edit")
    _run(client, "zhouyu")
    client.post(f"{V1}/assets/zhouyu/lock").raise_for_status()
    views = _until(client, _views_id(client, "zhouyu"), lambda p: p["status"] == "adopted")
    v = views["versions"][-1]
    assert v["origin"] == "fallback" and v["fallback_reason"] == "error"
    assert v["model_key"] == "google/nano-banana-pro"
    calls = [c for c in _rows(client, ModelCall) if c.product_id == views["id"]]
    ok = [c for c in calls if c.status == "success"]
    assert len(ok) == 3 and {c.model_key for c in ok} == {"google/nano-banana-pro"}
    assert all(c.is_fallback for c in ok)
    assert [c.model_key for c in calls if c.status != "success"] == ["comfy/qwen-image-edit"]


def test_a_retried_call_does_not_pay_again(client: TestClient) -> None:
    """The pictures a call made are cached by request: asking again costs nothing."""
    state = _state(client)
    comp = state.components.get("img")
    assert isinstance(comp, MediaComponent)

    async def twice() -> tuple[MediaCall, MediaCall]:
        async with state.db.session() as s:
            product = await s.get(Product, "demo-p-asset-room")
        assert product is not None
        ctx = RunContext(
            product=product,
            mode="run",
            model_key="volc/seedream-5.0",
            seed=7,
            intent="x",
            compiled="x",
            compiled_overridden=False,
        )
        req = comp.image_request(
            "x", n=2, size=dims("9:16", "1080p"), aspect="9:16", seed=7, task="ref"
        )
        first = await comp.media_call(ctx, req, None, model="volc/seedream-5.0")
        again = await comp.media_call(ctx, req, None, model="volc/seedream-5.0")
        return first, again

    first, again = client.portal.call(twice)  # type: ignore[union-attr]
    assert not first.cached and first.cost_usd == pytest.approx(2 * 0.12 / 7.1)  # 0.12 元 each
    assert again.cached and again.cost_usd == 0 and again.files == first.files
    calls = [c for c in _rows(client, ModelCall) if c.model_key == "volc/seedream-5.0"]
    assert len(calls) == 1
