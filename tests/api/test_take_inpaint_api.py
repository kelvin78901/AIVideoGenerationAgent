"""视频局部修复 of a take (M6 step 8b, component ``vinpaint``), in Mock mode.

``POST /versions/{id}/inpaint`` on a take (the picture 局部修复's route, M5.5) queues
``vinpaint`` on the shot's video product: one version (origin ``inpaint``, parent = the take,
the take's stage) with the painted part drawn again over the whole take, its sound kept as it
is, QA'd like every take and adopted as 2K 精修 is. The mask is made the take's size; the model
gets the take's frames and its size in multiples of 16. Only locally: a machine that cannot run
Wan VACE is refused with the reason.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_capabilities_api import _scan
from test_inpaint_api import _mask, _size
from test_qa_api import V1, _confirm_storyboard, _qa_settled, _rows, _state, _take, _wait, client
from test_take_upscale_api import _bytes, _deps, _product, _sound, _video

from drama_series_agent.core.models_db import ModelCall
from drama_series_agent.media.video import frame_count
from drama_series_agent.pipeline.components import vinpaint

__all__ = ["client"]


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    seen: list[Any] = []
    real = vinpaint.VinpaintComponent.media_call

    async def spy(self: Any, ctx: Any, req: Any, *args: Any, **kwargs: Any) -> Any:
        seen.append(req)
        return await real(self, ctx, req, *args, **kwargs)

    monkeypatch.setattr(vinpaint.VinpaintComponent, "media_call", spy)
    return seen


def _inpaint(client: TestClient, version_id: str, mask: bytes, **form: Any) -> Any:
    return client.post(
        f"{V1}/versions/{version_id}/inpaint",
        files={"mask": ("mask.png", mask, "image/png")},
        data={k: str(v) for k, v in form.items()},
    )


def _done(client: TestClient, resp: Any, label: str) -> dict[str, Any]:
    assert resp.status_code == 200, resp.text
    job = resp.json()
    assert job["component_id"] == "vinpaint"
    _wait(client, job["id"])
    _qa_settled(client)
    return _product(client, label)


def test_an_adopted_take_painted_over_is_adopted_after_qa(
    client: TestClient, sent: list[Any]
) -> None:
    _confirm_storyboard(client)
    take = _take(client, "1-04")
    client.post(f"{V1}/versions/{take['id']}/adopt").raise_for_status()
    before = _product(client, "1-04")

    # The menu's time: Wan VACE locally (Mock, nothing scanned), free but QA.
    finishing = before["estimate"]["finishing"]["vinpaint"]
    assert (finishing["model_key"], finishing["where"]) == ("comfy/vace-inpaint", "local")
    assert finishing["cost_usd"] < 0.01 and finishing["seconds"] is not None

    src = _video(take)
    w, h = int(src["w"]), int(src["h"])
    # Painted at half the size: made the take's.
    resp = _inpaint(client, take["id"], _mask(w // 2, h // 2), prompt="空白的墙")
    product = _done(client, resp, "1-04")
    v = product["versions"][-1]
    assert (v["origin"], v["parent_version_id"], v["stage"]) == ("inpaint", take["id"], "draft")
    assert v["model_key"] == "comfy/vace-inpaint"
    assert v["params"]["finish"] == {"kind": "inpaint", "version_id": take["id"]}
    assert product["prompt"] == before["prompt"] and v["intent"] == "空白的墙"
    assert _deps(client, v["id"]) == _deps(client, take["id"])

    # The take as stored, every one of its frames, at its size in multiples of 16.
    (req,) = sent
    assert (req.kind, req.prompt, req.params["video_in"]) == ("vinpaint", "空白的墙", src["sha256"])
    assert (req.params["width"], req.params["height"]) == (w // 16 * 16, h // 16 * 16)
    path = _state(client).store.path_for(src["sha256"])
    assert req.params["frames"] == client.portal.call(frame_count, path)  # type: ignore[union-attr]
    assert _size(client, req.params["mask"]) == (w, h)
    record = v["payload"]["inpaint"]
    assert record["mask"] == req.params["mask"] and abs(record["share"] - 0.25) < 0.01

    # Its sound is the take's as it was.
    assert _sound(_bytes(client, _video(v))) == _sound(_bytes(client, src))

    # Checked like a take, scores on its call; then adopted.
    assert v["qa_pass"] is True
    (call,) = _rows(client, ModelCall, ModelCall.id == v["params"]["call_id"])
    assert call.component_id == "vinpaint" and call.qa_pass is True
    assert product["adopted_version_id"] == v["id"]


def test_without_an_instruction_the_part_is_filled_from_around_it(
    client: TestClient, sent: list[Any]
) -> None:
    _confirm_storyboard(client)
    take = _take(client, "1-04")
    src = _video(take)
    product = _done(client, _inpaint(client, take["id"], _mask(src["w"], src["h"])), "1-04")
    (req,) = sent
    assert req.prompt == ""
    # Nothing adopted before: one more take to pick from.
    assert product["adopted_version_id"] is None


def test_what_is_refused(client: TestClient) -> None:
    _confirm_storyboard(client)
    take = _take(client, "1-04")
    src = _video(take)
    # Nothing painted.
    resp = _inpaint(client, take["id"], _mask(src["w"], src["h"], painted_rows=0))
    assert (resp.status_code, resp.json()["detail"]["code"]) == (422, "bad_mask")
    # Another shape than the take's.
    resp = _inpaint(client, take["id"], _mask(src["h"], src["w"]))
    assert (resp.status_code, resp.json()["detail"]["code"]) == (422, "bad_mask")

    _scan(client, "mac")  # no CUDA: Wan VACE cannot run, and there is no API model
    resp = _inpaint(client, take["id"], _mask(src["w"], src["h"]))
    detail = resp.json()["detail"]
    assert (resp.status_code, detail["code"]) == (409, "inpaint_unavailable")
    assert detail["params"]["reason"] == "machine_cuda"
