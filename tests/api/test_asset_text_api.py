"""画面文字 (SPEC 5 ``text``; M3 step 5): candidates checked by OCR, in Mock mode.

The demo's 便利贴手写 (txt1) is drawn by the model, its B and D read differently by OCR; 手机锁屏
时间 (txt2) is composited in post, its candidates blank bases.
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
from drama_series_agent.core.models_db import GateDecision, ModelCall
from drama_series_agent.modelhub.adapters.mock import MOCK_TEXT_KEY, gradient_png, png_texts

LOCAL = "http://127.0.0.1"
V1 = "/api/v1"
NOTE = "楼下便利店，等你到十二点。"


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


def _detail(resp: Any) -> dict[str, Any]:
    detail: dict[str, Any] = resp.json()["detail"]
    return detail


def _product(client: TestClient, asset_id: str) -> dict[str, Any]:
    product: dict[str, Any] = client.get(f"{V1}/products/demo-p-asset-{asset_id}").json()
    return product


def _latest(client: TestClient, asset_id: str) -> dict[str, Any]:
    version: dict[str, Any] = _product(client, asset_id)["versions"][-1]
    return version


def _run(client: TestClient, asset_id: str, **body: Any) -> dict[str, Any]:
    resp = client.post(f"{V1}/products/demo-p-asset-{asset_id}/run", json={"mode": "run", **body})
    assert resp.status_code == 200, resp.text
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        job: dict[str, Any] = client.get(f"{V1}/jobs/{resp.json()['id']}").json()
        if job["state"] in ("succeeded", "failed", "canceled"):
            assert job["state"] == "succeeded", job
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def _picture_texts(client: TestClient, version: dict[str, Any]) -> list[dict[str, str]]:
    """What each candidate picture carries (the Mock writes drawn text into it)."""
    out = []
    for f in version["files"]:
        if f["role"] == "candidate":
            out.append(png_texts(client.get(f"{V1}/files/{f['sha256']}").content))
    return out


def _ok(read: str | None, ok: bool | None = True, issue: str | None = None) -> dict[str, Any]:
    return {"ocr": read, "ocr_ok": ok, "ocr_issue": issue}


def test_the_demo_candidates_carry_their_ocr(client: TestClient) -> None:
    (v1,) = _product(client, "txt1")["versions"]
    assert v1["payload"]["text"] == {"exact": NOTE, "method": "model", "style": "handwritten"}
    assert v1["payload"]["candidates"] == [
        _ok(NOTE),
        _ok(NOTE.replace("点", "占"), False, "wrong"),
        _ok(NOTE),
        _ok(NOTE[:-1], False, "missing"),
    ]
    txt2 = _product(client, "txt2")
    first = txt2["versions"][0]
    assert first["payload"]["candidates"] == [_ok("")] * 4
    assert _picture_texts(client, first) == [{}] * 4  # blank bases
    assert txt2["locked_hash"]


def test_drawn_text_is_read_back_from_every_candidate(client: TestClient) -> None:
    job = _run(client, "txt1")
    assert job["queue"] == "gpu"  # hybrid: the draft is local
    draft = _latest(client, "txt1")
    assert (draft["stage"], draft["model_key"]) == ("draft", "comfy/qwen-image")
    assert draft["payload"]["candidates"] == [_ok(NOTE)] * 4
    assert _picture_texts(client, draft) == [{MOCK_TEXT_KEY: NOTE}] * 4
    assert "[文字，必须逐字一致]\n" + NOTE in _prompt(client, draft)
    calls = [c for c in _rows(client, ModelCall) if c.component_id == "ocr"]
    assert len(calls) == 4
    assert {(c.model_key, c.where, c.cost_usd, c.status) for c in calls} == {
        ("local/rapidocr", "local", 0.0, "success")
    }
    assert {c.product_id for c in calls} == {"demo-p-asset-txt1"}
    assert {c.job_id for c in calls} == {job["id"]}

    # The API final from candidate C is read too.
    params = {"source_version_id": draft["id"], "source_idx": 2}
    job = _run(client, "txt1", where="api", params=params)
    assert job["queue"] == "api:openai"
    final = _latest(client, "txt1")
    assert (final["stage"], final["parent_version_id"]) == ("final", draft["id"])
    assert final["model_key"] == "openai/gpt-image-2"
    assert final["payload"]["candidates"] == [_ok(NOTE)]
    assert len([c for c in _rows(client, ModelCall) if c.component_id == "ocr"]) == 5


def _prompt(client: TestClient, version: dict[str, Any]) -> str:
    f = next(f for f in version["files"] if f["role"] == "prompt")
    return client.get(f"{V1}/files/{f['sha256']}").content.decode("utf-8")


def test_a_mismatch_locks_only_with_force(client: TestClient) -> None:
    # The demo: B reads 占 for 点.
    resp = client.post(f"{V1}/assets/txt1/lock", json={"idx": 1})
    assert resp.status_code == 409
    assert _detail(resp) == {
        "code": "ocr_mismatch",
        "params": {
            "id": "txt1",
            "idx": 1,
            "read": NOTE.replace("点", "占"),
            "exact": NOTE,
            "issue": "wrong",
        },
    }
    assert _product(client, "txt1")["locked_hash"] is None

    # Every candidate of a run misses the full stop.
    _state(client).registry.mock_settings.ocr_mismatch = True
    _run(client, "txt1")
    draft = _latest(client, "txt1")
    assert draft["payload"]["candidates"] == [_ok(NOTE[:-1], False, "missing")] * 4
    assert _detail(client.post(f"{V1}/assets/txt1/lock"))["code"] == "ocr_mismatch"
    resp = client.post(f"{V1}/assets/txt1/lock", json={"force": True})
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "locked"
    gates = [g for g in _rows(client, GateDecision) if g.gate == "assets" and g.scope_id == "txt1"]
    assert [g.action for g in gates] == ["confirm"]


def test_a_matching_candidate_locks(client: TestClient) -> None:
    resp = client.post(f"{V1}/assets/txt1/lock", json={"idx": 2})
    assert resp.status_code == 200, resp.text
    product = _product(client, "txt1")
    pick = next(v for v in product["versions"] if v["id"] == product["adopted_version_id"])
    assert pick["payload"] == {"candidate": _ok(NOTE)}


def test_compositing_draws_a_blank_base(client: TestClient) -> None:
    resp = client.patch(f"{V1}/assets/txt1", json={"text": {"method": "composite"}})
    assert resp.json()["text"] == {"exact": NOTE, "method": "composite", "style": "handwritten"}
    _run(client, "txt1")
    base = _latest(client, "txt1")
    assert base["payload"]["text"]["method"] == "composite"
    assert base["payload"]["candidates"] == [_ok("")] * 4
    assert _picture_texts(client, base) == [{}] * 4
    prompt = _prompt(client, base)
    assert "[后期贴字]\n画面里不要出现任何文字、数字或符号。" in prompt
    assert f"留出一块干净的位置，后期会把「{NOTE}」写在纸面上。" in prompt
    assert "[文字，必须逐字一致]" not in prompt


def test_without_ocr_the_candidates_are_not_checked(client: TestClient) -> None:
    _state(client).registry.mock_settings.fail_keys.add("local/rapidocr")
    _run(client, "txt1")
    draft = _latest(client, "txt1")
    assert draft["payload"]["candidates"] == [_ok(None, None)] * 4
    assert client.post(f"{V1}/assets/txt1/lock").status_code == 200  # 未检查 never blocks


def test_an_uploaded_picture_is_read(client: TestClient) -> None:
    def upload(png: bytes) -> dict[str, Any]:
        resp = client.post(f"{V1}/assets/txt1/upload", files={"file": ("note.png", png)})
        assert resp.status_code == 200, resp.text
        return _latest(client, "txt1")

    drawn = upload(gradient_png(8, 8, (240, 230, 160), texts={MOCK_TEXT_KEY: NOTE}))
    assert drawn["origin"] == "upload"
    assert drawn["payload"] == {
        "candidates": [_ok(NOTE)],
        "text": {"exact": NOTE, "method": "model", "style": "handwritten"},
    }
    blank = upload(gradient_png(8, 8, (240, 230, 160)))
    assert blank["payload"]["candidates"] == [_ok("", False, "missing")]
    assert _detail(client.post(f"{V1}/assets/txt1/lock"))["code"] == "ocr_mismatch"
