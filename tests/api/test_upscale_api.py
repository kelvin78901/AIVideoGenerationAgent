"""图片超分 (M5.5 step 15, component ``iup``), in Mock mode.

``POST /versions/{id}/upscale {idx}`` queues a run of ``iup`` on that version's product, as a
redraw does: a keyframe at the delivery size, a reference picture or a view at a long edge of
2048; a new version with origin ``upscale``. Only locally (SeedVR2): a machine that cannot run
it is refused with the reason.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_asset_more_api import V1, _code, _png, _shot, client
from test_capabilities_api import _scan
from test_redraw_api import VIEWS, _deps, _done

from drama_series_agent.pipeline.components import iup, redraw

__all__ = ["client"]


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    seen: list[Any] = []
    real = redraw.RedrawComponent.media_call

    async def spy(self: Any, ctx: Any, req: Any, *args: Any, **kwargs: Any) -> Any:
        seen.append(req)
        return await real(self, ctx, req, *args, **kwargs)

    monkeypatch.setattr(iup.IupComponent, "media_call", spy)
    return seen


def _upscale(client: TestClient, version_id: str, **body: Any) -> Any:
    return client.post(f"{V1}/versions/{version_id}/upscale", json=body)


def test_larger_keeps_the_shape() -> None:
    assert iup.larger(40, 60) == iup.Dims(w=1366, h=2048)
    assert iup.larger(1328, 1328) == iup.Dims(w=2048, h=2048)
    assert iup.larger(3000, 1000) == iup.Dims(w=2048, h=682)


def test_a_keyframe_at_the_delivery_size(client: TestClient, sent: list[Any]) -> None:
    kf_id = _shot(client, "1-04")["keyframe_product_id"]
    before = client.get(f"{V1}/products/{kf_id}").json()
    source = before["versions"][-1]
    base = next(f for f in source["files"] if f["role"] == "candidate" and f["idx"] == 1)
    product = _done(client, _upscale(client, source["id"], idx=1), kf_id)
    v = product["versions"][-1]
    assert v["origin"] == "upscale" and v["parent_version_id"] == source["id"]
    assert v["model_key"] == "comfy/seedvr2-img" and v["stage"] == "final"
    assert v["payload"]["iup"] == {"version_id": source["id"], "idx": 1, "from": base["sha256"]}
    assert product["adopted_version_id"] == before["adopted_version_id"]
    assert product["prompt"] == before["prompt"]
    assert _deps(client, v["id"]) == _deps(client, source["id"])
    (req,) = sent
    assert (req.params["width"], req.params["height"]) == (1080, 1920)  # the demo's delivery
    assert req.params["base_image"] == base["sha256"] and "refs" not in req.params
    assert v["intent"] == "放大，细节更清楚"


def test_a_view_and_a_reference_at_a_long_edge_of_2048(client: TestClient, sent: list[Any]) -> None:
    source = client.get(f"{V1}/products/{VIEWS}").json()["versions"][-1]
    product = _done(client, _upscale(client, source["id"], idx=3), VIEWS)
    v = product["versions"][-1]
    assert product["adopted_version_id"] == v["id"] and v["origin"] == "upscale"
    assert max(sent[0].params["width"], sent[0].params["height"]) == 2048

    up = client.post(f"{V1}/assets/band/upload", files={"file": ("band.png", _png(5))})
    assert up.status_code == 200, up.text
    band = client.get(f"{V1}/products/demo-p-asset-band").json()
    _done(client, _upscale(client, band["versions"][-1]["id"]), band["id"])
    assert (sent[1].params["width"], sent[1].params["height"]) == (1366, 2048)
    assert sent[1].params["aspect"] == "3:4"


def test_an_upscale_refuses(client: TestClient) -> None:
    kf = client.get(f"{V1}/products/{_shot(client, '1-04')['keyframe_product_id']}").json()
    assert _code(_upscale(client, kf["versions"][-1]["id"], idx=9)) == "file_not_found"
    locked = client.get(f"{V1}/products/{_shot(client, '1-01')['keyframe_product_id']}").json()
    assert _code(_upscale(client, locked["versions"][-1]["id"])) == "product_locked"
    listed = client.get(f"{V1}/products", params={"owner": "episode:demo-e1"}).json()
    script = next(p for p in listed if p["slot"] == "script" and p["versions"])
    assert _code(_upscale(client, script["versions"][-1]["id"])) == "upscale_not_supported"

    _scan(client, "mac")  # no CUDA: SeedVR2 cannot run, and there is no API model
    resp = _upscale(client, kf["versions"][-1]["id"])
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "upscale_unavailable"
    assert resp.json()["detail"]["params"]["reason"] == "machine_cuda"
