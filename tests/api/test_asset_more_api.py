"""多参考图, 六视图单张替换 and 新建素材 (M5.5 step 11), in Mock mode.

- ``POST /assets/{id}/refs`` adds a picture with its purpose to the asset's ``ref_more``
  product, ``DELETE /assets/{id}/refs/{idx}`` takes one out; each is a new version, adopted.
- A keyframe sends them after every main picture, every 正脸 first, as far as the model takes,
  and depends on them.
- ``POST /products/{id}/views/{view}``: a file takes that view's place, the other five and the
  dependencies copied; without one, that view alone is drawn again.
- ``POST /series/{id}/assets``: an asset by hand, ``manual``, a shot may take it, an analysis
  keeps it.
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
from drama_series_agent.core.models_db import Asset, Dependency, ModelCall
from drama_series_agent.modelhub.adapters.mock import gradient_png
from drama_series_agent.pipeline.components import kf

LOCAL = "http://127.0.0.1"
V1 = "/api/v1"
EP1 = "demo-e1"
VIEWS = "demo-p-views-linwan"


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


def _wait(client: TestClient, job_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 30
    while True:
        job: dict[str, Any] = client.get(f"{V1}/jobs/{job_id}").json()
        if job["state"] in ("succeeded", "failed", "canceled"):
            return job
        assert time.monotonic() < deadline, "the job did not finish"
        time.sleep(0.02)


def _png(seed: int) -> bytes:
    return gradient_png(40, 60, (seed, 80, 120))


def _add(client: TestClient, asset_id: str, purpose: str, data: bytes) -> Any:
    return client.post(
        f"{V1}/assets/{asset_id}/refs",
        files={"file": (f"{purpose}.png", data, "image/png")},
        data={"purpose": purpose},
    )


def _shot(client: TestClient, label: str) -> dict[str, Any]:
    shots = client.get(f"{V1}/episodes/{EP1}/shots").json()
    shot: dict[str, Any] = next(s for s in shots if s["label"] == label)
    return shot


def _keyframe(client: TestClient, label: str) -> dict[str, Any]:
    pid = _shot(client, label)["keyframe_product_id"]
    resp = client.post(f"{V1}/products/{pid}/run", json={"mode": "rerun"})
    assert resp.status_code == 200, resp.text
    assert _wait(client, resp.json()["id"])["state"] == "succeeded"
    product: dict[str, Any] = client.get(f"{V1}/products/{pid}").json()
    return product


def _prompt(client: TestClient, version: dict[str, Any]) -> str:
    f = next(x for x in version["files"] if x["role"] == "prompt")
    return client.get(f"{V1}/files/{f['sha256']}").content.decode("utf-8")


def test_more_pictures_of_an_asset(client: TestClient) -> None:
    resp = _add(client, "linwan", "outfit", _png(1))
    assert resp.status_code == 200, resp.text
    more = resp.json()
    assert more["slot"] == "ref_more" and more["owner_id"] == "linwan"
    resp = _add(client, "linwan", "face", _png(2))
    more = resp.json()
    assert len(more["versions"]) == 2 and more["adopted_version_id"] == more["versions"][-1]["id"]
    v = more["versions"][-1]
    assert [(f["role"], f["idx"], f["purpose"]) for f in v["files"]] == [
        ("ref", 0, "outfit"),
        ("ref", 1, "face"),
    ]
    assert v["payload"]["refs"] == [{"purpose": "outfit"}, {"purpose": "face"}]
    assert v["origin"] == "upload"
    # Taking one out: the rest in a new version, numbered again.
    gone = client.delete(f"{V1}/assets/linwan/refs/0").json()
    v3 = gone["versions"][-1]
    assert v3["origin"] == "edit" and gone["adopted_version_id"] == v3["id"]
    assert [(f["idx"], f["purpose"]) for f in v3["files"]] == [(0, "face")]
    # The asset's main picture is untouched (still locked).
    assert client.get(f"{V1}/products/demo-p-asset-linwan").json()["locked_hash"]


def test_more_pictures_refuse(client: TestClient) -> None:
    assert _code(_add(client, "linwan", "feet", _png(1))) == "invalid_purpose"
    assert _code(_add(client, "linwan", "face", b"not a picture")) == "not_an_image"
    assert _code(_add(client, "vzhouyu", "face", _png(1))) == "upload_not_supported"
    assert _add(client, "nope", "face", _png(1)).status_code == 404
    assert _code(client.delete(f"{V1}/assets/linwan/refs/0")) == "ref_not_found"
    for i in range(8):
        assert _add(client, "room", "other", _png(i)).status_code == 200
    assert _code(_add(client, "room", "other", _png(9))) == "too_many_refs"


def test_a_keyframe_sends_the_extra_pictures_after_the_main_ones(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """1-06: 林晚 and her flat locked. Her 正脸 goes before her 服装 though added after it,
    both after every main picture; a model that takes fewer leaves them out first."""
    monkeypatch.setattr(kf, "ref_limit", lambda *_: None)
    first = _keyframe(client, "1-06")["versions"][-1]["payload"]["refs"]
    assert "林晚" in first
    _add(client, "linwan", "outfit", _png(1)).raise_for_status()
    more = _add(client, "linwan", "face", _png(2)).json()
    product = _keyframe(client, "1-06")
    v = product["versions"][-1]
    assert v["payload"]["refs"] == [*first, "林晚·正脸", "林晚·服装"]
    n = len(first)
    sent = _prompt(client, v)
    assert f"参考图 {n + 1}：林晚（角色·正脸）" in sent
    assert f"参考图 {n + 1} 只参考林晚的正脸；参考图 {n + 2} 只参考林晚的服装。" in sent
    deps = _rows(client, Dependency, Dependency.version_id == v["id"])
    assert [d.upstream_product_id for d in deps].count(more["id"]) == 1
    # Another picture for her: the keyframe now follows an older set.
    _add(client, "linwan", "hair", _png(3)).raise_for_status()
    assert client.get(f"{V1}/products/{product['id']}").json()["status"] == "stale"
    # Room for one more than the main pictures: her 正脸 only.
    monkeypatch.setattr(kf, "ref_limit", lambda *_: n + 1)
    v = _keyframe(client, "1-06")["versions"][-1]
    assert v["payload"]["refs"] == [*first, "林晚·正脸"]
    # Her main picture went: the left-out extras are not named as missing.
    missing = _prompt(client, v).split("[没传的参考]", 1)[-1].strip().split("（", 1)[0]
    assert "林晚" not in missing.split("、")


def test_one_view_uploaded_or_drawn_again(client: TestClient) -> None:
    views = client.get(f"{V1}/products/{VIEWS}").json()
    v1 = views["versions"][-1]
    deps1 = {
        (d.upstream_product_id, d.upstream_hash)
        for d in _rows(client, Dependency, Dependency.version_id == v1["id"])
    }
    png = _png(7)
    resp = client.post(
        f"{V1}/products/{VIEWS}/views/side", files={"file": ("side.png", png, "image/png")}
    )
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["job"] is None
    v2 = out["product"]["versions"][-1]
    assert v2["origin"] == "upload" and out["product"]["adopted_version_id"] == v2["id"]
    assert out["product"]["status"] == "adopted"
    before = {f["view"]: f["sha256"] for f in v1["files"] if f["role"] == "view"}
    after = {f["view"]: f["sha256"] for f in v2["files"] if f["role"] == "view"}
    assert list(after) == list(before)
    assert after["side"] != before["side"]
    assert {k: x for k, x in after.items() if k != "side"} == {
        k: x for k, x in before.items() if k != "side"
    }
    assert v2["payload"]["uploaded"] == ["side"]
    deps2 = {
        (d.upstream_product_id, d.upstream_hash)
        for d in _rows(client, Dependency, Dependency.version_id == v2["id"])
    }
    assert deps2 == deps1
    # 「重画这一张」: one call, that view new, the uploaded one kept.
    calls = len(_rows(client, ModelCall, ModelCall.product_id == VIEWS))
    resp = client.post(f"{V1}/products/{VIEWS}/views/smile")
    assert resp.status_code == 200, resp.text
    assert _wait(client, resp.json()["job"]["id"])["state"] == "succeeded"
    assert len(_rows(client, ModelCall, ModelCall.product_id == VIEWS)) == calls + 1
    views = client.get(f"{V1}/products/{VIEWS}").json()
    v3 = views["versions"][-1]
    assert views["adopted_version_id"] == v3["id"]
    now = {f["view"]: f["sha256"] for f in v3["files"] if f["role"] == "view"}
    assert [f["idx"] for f in v3["files"] if f["role"] == "view"] == list(range(6))
    assert now["side"] == after["side"] and now["smile"] != after["smile"]
    assert now["back"] == after["back"]
    assert v3["payload"]["uploaded"] == ["side"]
    # Drawing the uploaded one again: no longer uploaded.
    resp = client.post(f"{V1}/products/{VIEWS}/views/side")
    assert _wait(client, resp.json()["job"]["id"])["state"] == "succeeded"
    v4 = client.get(f"{V1}/products/{VIEWS}").json()["versions"][-1]
    assert "uploaded" not in v4["payload"]


def test_one_view_refuses(client: TestClient) -> None:
    png = _png(1)

    def up(product_id: str, view: str, data: bytes) -> Any:
        return client.post(
            f"{V1}/products/{product_id}/views/{view}", files={"file": ("x.png", data)}
        )

    assert _code(up(VIEWS, "left", png)) == "unknown_view"
    assert _code(client.post(f"{V1}/products/{VIEWS}/views/left")) == "unknown_view"
    assert _code(up(VIEWS, "side", b"nope")) == "not_an_image"
    assert _code(up("demo-p-asset-linwan", "side", png)) == "not_views"
    assert up("nope", "side", png).status_code == 404

    # A set that follows another picture than the locked one: only all of them again.
    adopted = client.get(f"{V1}/products/{VIEWS}").json()["adopted_version_id"]

    async def older() -> None:
        async with _state(client).db.session() as s:
            for d in (
                await s.exec(select(Dependency).where(Dependency.version_id == adopted))
            ).all():
                d.upstream_hash = "0" * 64
                s.add(d)
            await s.commit()

    client.portal.call(older)  # type: ignore[union-attr]
    assert _code(client.post(f"{V1}/products/{VIEWS}/views/smile")) == "views_outdated"


def test_an_asset_made_by_hand(client: TestClient) -> None:
    body = {"kind": "prop", "name": "旧钥匙", "description": "一把磨亮的黄铜旧钥匙"}
    resp = client.post(f"{V1}/series/demo/assets", json=body)
    assert resp.status_code == 200, resp.text
    key = resp.json()
    assert key["kind"] == "prop" and key["status"] == "not_generated"
    assert key["intent"] == "一把磨亮的黄铜旧钥匙" and key["scenes"] == []
    # The list marks it 「手动」; no scene has it yet.
    assert key["manual"] and key["source"] == {"code": "manual", "params": {}}
    (row,) = _rows(client, Asset, Asset.id == key["id"])
    assert row.manual
    assert any(a["id"] == key["id"] for a in client.get(f"{V1}/series/demo/assets").json())
    assert _code(client.post(f"{V1}/series/demo/assets", json=body)) == "asset_exists"
    assert _code(client.post(f"{V1}/series/demo/assets", json={**body, "name": " "})) == (
        "name_required"
    )
    assert client.post(f"{V1}/series/nope/assets", json=body).status_code == 404
    bad = client.post(f"{V1}/series/demo/assets", json={**body, "kind": "voice"})
    assert bad.status_code == 422
    # A shot takes it as a reference; not locked yet, the keyframe goes by words.
    shot = _shot(client, "1-04")
    ids = [*shot["asset_ids"], key["id"]]
    resp = client.patch(f"{V1}/shots/{shot['id']}", json={"asset_ids": ids})
    assert resp.status_code == 200, resp.text
    sent = _prompt(client, _keyframe(client, "1-04")["versions"][-1])
    assert "旧钥匙" in sent.split("[没传的参考]", 1)[1]
    # A new analysis keeps it, as it was written.
    job = client.post(f"{V1}/episodes/{EP1}/assets/analyze").json()
    assert _wait(client, job["id"])["state"] == "succeeded"
    (row,) = _rows(client, Asset, Asset.id == key["id"])
    assert row.manual and not row.retired and row.name == "旧钥匙"
    assert row.seed_json["description"] == "一把磨亮的黄铜旧钥匙"
