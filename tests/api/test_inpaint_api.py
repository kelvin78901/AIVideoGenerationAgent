"""局部修复 (M5.5 step 14, component ``inpaint``), in Mock mode.

``POST /versions/{id}/inpaint`` (multipart: ``mask``, ``idx``, ``prompt``) queues a run of
``inpaint`` on that version's product, as a redraw does: a keyframe or reference picture gets a
new version with one candidate (not adopted), a views set gets that view replaced. The mask is
made the picture's size when the request comes in and stored in both forms (grayscale for
ComfyUI, RGBA for OpenAI); locally FLUX 3 Klein inpaints, on the API GPT Image 2 gets the
picture and the RGBA mask.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_asset_more_api import V1, _code, _png, _prompt, _shot, _state, client
from test_redraw_api import VIEWS, _deps, _done

from drama_series_agent.media.image import image_info, png
from drama_series_agent.pipeline.components import inpaint, redraw

__all__ = ["client"]


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """The requests the inpaint component sends."""
    seen: list[Any] = []
    real = redraw.RedrawComponent.media_call

    async def spy(self: Any, ctx: Any, req: Any, *args: Any, **kwargs: Any) -> Any:
        seen.append(req)
        return await real(self, ctx, req, *args, **kwargs)

    monkeypatch.setattr(inpaint.InpaintComponent, "media_call", spy)
    return seen


def _mask(w: int, h: int, painted_rows: int | None = None) -> bytes:
    """Light over the top ``painted_rows`` (a quarter by default), black below."""
    top = h // 4 if painted_rows is None else painted_rows
    return png(b"\xff" * (w * top) + b"\x00" * (w * (h - top)), w, h, channels=1)


def _inpaint(client: TestClient, version_id: str, mask: bytes, **form: Any) -> Any:
    return client.post(
        f"{V1}/versions/{version_id}/inpaint",
        files={"mask": ("mask.png", mask, "image/png")},
        data={k: str(v) for k, v in form.items()},
    )


def _size(client: TestClient, sha: str) -> tuple[int, int]:
    info = image_info(client.get(f"{V1}/files/{sha}").content)
    return info.w, info.h


def test_a_keyframe_candidate_painted_over_locally(client: TestClient, sent: list[Any]) -> None:
    kf_id = _shot(client, "1-04")["keyframe_product_id"]
    before = client.get(f"{V1}/products/{kf_id}").json()
    source = before["versions"][-1]
    base = next(f for f in source["files"] if f["role"] == "candidate" and f["idx"] == 1)
    w, h = _size(client, base["sha256"])
    resp = _inpaint(client, source["id"], _mask(w // 2, h // 2), idx=1, prompt="伞换成深蓝色")
    product = _done(client, resp, kf_id)
    v = product["versions"][-1]
    assert v["origin"] == "inpaint" and v["parent_version_id"] == source["id"]
    assert v["model_key"] == "comfy/klein-inpaint" and v["stage"] == "draft"
    assert [f["role"] for f in v["files"] if f["role"] != "prompt"] == ["candidate"]
    record = v["payload"]["inpaint"]
    assert record["version_id"] == source["id"] and record["idx"] == 1
    assert record["from"] == base["sha256"] and record["share"] == pytest.approx(0.25, abs=0.01)
    assert product["adopted_version_id"] == before["adopted_version_id"]
    assert product["prompt"] == before["prompt"]
    assert _deps(client, v["id"]) == _deps(client, source["id"])
    (req,) = sent
    # The demo's pictures are PNG: sent as they are, with the mask at their size.
    assert req.params["base_image"] == base["sha256"] and req.params["refs"] == [base["sha256"]]
    assert req.params["mask"] == record["mask"] and "denoise" not in req.params
    assert _size(client, req.params["mask"]) == (w, h)
    assert _size(client, req.params["mask_alpha"]) == (w, h)
    text = _prompt(client, v)
    assert "伞换成深蓝色" in text and "[范围]\n" + inpaint.AREA in text


def test_on_the_api_gpt_image_2_gets_the_alpha_mask(client: TestClient, sent: list[Any]) -> None:
    kf_id = _shot(client, "1-05")["keyframe_product_id"]
    source = client.get(f"{V1}/products/{kf_id}").json()["versions"][-1]
    f = next(x for x in source["files"] if x["role"] == "candidate")
    w, h = _size(client, f["sha256"])
    product = _done(client, _inpaint(client, source["id"], _mask(w, h), where="api"), kf_id)
    v = product["versions"][-1]
    assert v["model_key"] == "openai/gpt-image-2" and v["where"] == "api"
    assert v["stage"] is None and v["origin"] == "inpaint"
    assert v["intent"] == "把涂抹的地方自然地补好，和周围接得上"  # no instruction: the default
    assert sent[0].params["mask_alpha"]


def test_one_view_painted_over(client: TestClient) -> None:
    source = client.get(f"{V1}/products/{VIEWS}").json()["versions"][-1]
    view = next(f for f in source["files"] if f["role"] == "view" and f["idx"] == 2)
    w, h = _size(client, view["sha256"])
    product = _done(client, _inpaint(client, source["id"], _mask(w, h), idx=2), VIEWS)
    v = product["versions"][-1]
    assert product["adopted_version_id"] == v["id"] and v["origin"] == "inpaint"
    old = {f["view"]: f["sha256"] for f in source["files"] if f["role"] == "view"}
    new = {f["view"]: f["sha256"] for f in v["files"] if f["role"] == "view"}
    assert [k for k in old if old[k] != new[k]] == [view["view"]]


def test_a_reference_picture_keeps_its_size(client: TestClient, sent: list[Any]) -> None:
    """The mask is made the picture's size (40 × 60), whatever size it was painted at; a
    picture that is not PNG would be sent as one (``test_image_mask.py``)."""
    up = client.post(f"{V1}/assets/band/upload", files={"file": ("band.png", _png(5))})
    assert up.status_code == 200, up.text
    band = client.get(f"{V1}/products/demo-p-asset-band").json()
    source = band["versions"][-1]
    product = _done(client, _inpaint(client, source["id"], _mask(20, 30)), band["id"])
    v = product["versions"][-1]
    assert v["origin"] == "inpaint" and v["payload"]["candidates"] == [{}]
    assert (sent[0].params["width"], sent[0].params["height"]) == (40, 60)
    assert _size(client, sent[0].params["mask"]) == (40, 60)
    assert sent[0].params["base_image"] == v["payload"]["inpaint"]["from"]
    assert _state(client).store.exists(sent[0].params["mask_alpha"])


def test_an_inpaint_refuses(client: TestClient) -> None:
    kf = client.get(f"{V1}/products/{_shot(client, '1-04')['keyframe_product_id']}").json()
    vid = kf["versions"][-1]["id"]
    f = next(x for x in kf["versions"][-1]["files"] if x["role"] == "candidate")
    w, h = _size(client, f["sha256"])
    assert _code(_inpaint(client, vid, _mask(w, h, painted_rows=0))) == "bad_mask"
    assert _code(_inpaint(client, vid, _mask(w, w))) == "bad_mask"  # another shape
    assert _code(_inpaint(client, vid, b"not a picture")) == "not_an_image"
    assert _code(_inpaint(client, vid, _mask(w, h), idx=9)) == "file_not_found"
    locked = client.get(f"{V1}/products/{_shot(client, '1-01')['keyframe_product_id']}").json()
    assert _code(_inpaint(client, locked["versions"][-1]["id"], _mask(w, h))) == "product_locked"
    listed = client.get(f"{V1}/products", params={"owner": "episode:demo-e1"}).json()
    script = next(p for p in listed if p["slot"] == "script" and p["versions"])
    resp = _inpaint(client, script["versions"][-1]["id"], _mask(w, h))
    assert _code(resp) == "inpaint_not_supported"
