"""以这张为底重画 (M5.5 step 13, component ``redraw``), in Mock mode.

``POST /versions/{id}/redraw {idx, prompt, strength}`` queues a run of ``redraw`` on that
version's product: a keyframe or reference picture gets a new version with one candidate (not
adopted), a views set gets that view replaced (adopted). Locally the picture is where FLUX 3
Klein starts from, the strength its denoise; on an API it is reference 1 and the strength is
said in words. The product's own prompt is left alone; the new version keeps the dependencies
of the one it came from.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_asset_more_api import V1, _code, _png, _prompt, _rows, _shot, _wait, client

from drama_series_agent.core.models_db import Dependency
from drama_series_agent.pipeline.components import redraw

__all__ = ["client"]
VIEWS = "demo-p-views-linwan"


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """The requests the redraw component sends."""
    seen: list[Any] = []
    real = redraw.RedrawComponent.media_call

    async def spy(self: Any, ctx: Any, req: Any, *args: Any, **kwargs: Any) -> Any:
        seen.append(req)
        return await real(self, ctx, req, *args, **kwargs)

    monkeypatch.setattr(redraw.RedrawComponent, "media_call", spy)
    return seen


def _redraw(client: TestClient, version_id: str, **body: Any) -> Any:
    return client.post(f"{V1}/versions/{version_id}/redraw", json=body)


def _done(client: TestClient, resp: Any, product_id: str) -> dict[str, Any]:
    assert resp.status_code == 200, resp.text
    assert _wait(client, resp.json()["id"])["state"] == "succeeded"
    product: dict[str, Any] = client.get(f"{V1}/products/{product_id}").json()
    return product


def _deps(client: TestClient, version_id: str) -> set[tuple[str, str, str]]:
    rows = _rows(client, Dependency, Dependency.version_id == version_id)
    return {(d.upstream_product_id, d.upstream_hash, d.slice) for d in rows}


def test_a_keyframe_candidate_drawn_again_locally(client: TestClient, sent: list[Any]) -> None:
    kf_id = _shot(client, "1-04")["keyframe_product_id"]
    before = client.get(f"{V1}/products/{kf_id}").json()
    source = before["versions"][-1]
    base = next(f for f in source["files"] if f["role"] == "candidate" and f["idx"] == 1)
    resp = _redraw(client, source["id"], idx=1, prompt="伞换成深蓝色", strength=0.3)
    product = _done(client, resp, kf_id)
    v = product["versions"][-1]
    assert v["origin"] == "redraw" and v["parent_version_id"] == source["id"]
    assert v["model_key"] == "comfy/flux3-klein-redraw" and v["stage"] == "draft"
    assert [f["role"] for f in v["files"] if f["role"] != "prompt"] == ["candidate"]
    assert v["payload"]["redraw"] == {
        "version_id": source["id"],
        "idx": 1,
        "from": base["sha256"],
        "strength": 0.3,
    }
    # Not adopted (the user picks, as with any keyframe); the shot's prompt untouched.
    assert product["adopted_version_id"] == before["adopted_version_id"]
    assert product["prompt"] == before["prompt"]
    assert _deps(client, v["id"]) == _deps(client, source["id"])
    (req,) = sent
    assert req.params["base_image"] == base["sha256"] and req.params["refs"] == [base["sha256"]]
    assert req.params["denoise"] == 0.3
    text = _prompt(client, v)
    assert "伞换成深蓝色" in text and "[改动幅度]\n" + redraw.strength_words(0.3) in text
    assert "只做细微的改动" in text


def test_on_an_api_the_strength_is_in_words(client: TestClient, sent: list[Any]) -> None:
    kf_id = _shot(client, "1-05")["keyframe_product_id"]
    source = client.get(f"{V1}/products/{kf_id}").json()["versions"][-1]
    product = _done(client, _redraw(client, source["id"], strength=0.9, where="api"), kf_id)
    v = product["versions"][-1]
    assert v["model_key"] == "google/nano-banana-2.1" and v["where"] == "api"
    assert v["stage"] is None and v["origin"] == "redraw"
    assert "可以大改" in _prompt(client, v)
    assert sent[0].params["refs"] == [v["payload"]["redraw"]["from"]]


def test_one_view_drawn_again(client: TestClient) -> None:
    before = client.get(f"{V1}/products/{VIEWS}").json()
    source = before["versions"][-1]
    product = _done(client, _redraw(client, source["id"], idx=2, prompt="笑得再淡一点"), VIEWS)
    v = product["versions"][-1]
    assert product["adopted_version_id"] == v["id"] and v["origin"] == "redraw"
    old = {f["view"]: f["sha256"] for f in source["files"] if f["role"] == "view"}
    new = {f["view"]: f["sha256"] for f in v["files"] if f["role"] == "view"}
    changed = [k for k in old if old[k] != new[k]]
    assert changed == ["calm"] and list(new) == list(old)


def test_a_reference_picture_keeps_its_shape(client: TestClient, sent: list[Any]) -> None:
    up = client.post(f"{V1}/assets/band/upload", files={"file": ("band.png", _png(5))})
    assert up.status_code == 200, up.text
    band = client.get(f"{V1}/products/demo-p-asset-band").json()
    source = band["versions"][-1]
    product = _done(client, _redraw(client, source["id"]), band["id"])
    v = product["versions"][-1]
    assert v["origin"] == "redraw" and v["payload"]["candidates"] == [{}]
    assert (sent[0].params["width"], sent[0].params["height"]) == (40, 60)
    assert sent[0].params["aspect"] == "3:4"
    assert v["intent"] == "按原样重画，细节更清楚"  # no instruction: the default one


def test_a_redraw_refuses(client: TestClient) -> None:
    locked = client.get(f"{V1}/products/{_shot(client, '1-01')['keyframe_product_id']}").json()
    assert _code(_redraw(client, locked["versions"][-1]["id"])) == "product_locked"
    kf = client.get(f"{V1}/products/{_shot(client, '1-04')['keyframe_product_id']}").json()
    assert _code(_redraw(client, kf["versions"][-1]["id"], idx=9)) == "file_not_found"
    assert _redraw(client, "nope").status_code == 404
    assert _redraw(client, kf["versions"][-1]["id"], strength=2).status_code == 422
    listed = client.get(f"{V1}/products", params={"owner": "episode:demo-e1"}).json()
    script = next(p for p in listed if p["slot"] == "script" and p["versions"])
    assert _code(_redraw(client, script["versions"][-1]["id"])) == "redraw_not_supported"
