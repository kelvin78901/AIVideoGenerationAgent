"""``/series/{id}``, ``/series/{id}/spec`` and ``/spec/presets`` against the seeded demo series."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from drama_series_agent.api.app import create_app

LOCAL = "http://127.0.0.1"
CLIENT_HEADERS = {"X-Drama-Studio": "1"}
SPEC = "/api/v1/series/demo/spec"


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(), base_url=LOCAL, headers=CLIENT_HEADERS) as c:
        yield c


def _code(resp: object) -> str:
    return resp.json()["detail"]["code"]  # type: ignore[attr-defined,no-any-return]


def test_get_series(client: TestClient) -> None:
    data = client.get("/api/v1/series/demo").json()
    assert data == {
        "id": "demo",
        "slug": "rain-stops",
        "title": "雨停之前",
        "ui_lang": "zh-CN",
        "created_at": "2026-10-14T01:20:00Z",
    }
    resp = client.get("/api/v1/series/nope")
    assert resp.status_code == 404 and _code(resp) == "series_not_found"


def test_get_spec(client: TestClient) -> None:
    data = client.get(SPEC).json()
    assert data["platform"] == "cn" and data["aspect"] == "9:16" and data["fps"] == 24
    assert data["audio"] == {"sample_rate": 48000, "lufs": -14, "peak_dbtp": -1}
    assert data["derive"] is None and data["locked_at"] == "2026-10-14T03:02:00Z"
    assert data["dims"] == {"delivery": {"w": 1080, "h": 1920}, "draft": {"w": 768, "h": 1366}}
    resp = client.get("/api/v1/series/nope/spec")
    assert resp.status_code == 404 and _code(resp) == "series_not_found"


def test_put_spec_fields_and_dims(client: TestClient) -> None:
    resp = client.put(SPEC, json={"delivery": "2k", "fps": 25, "derive": "16:9"})
    assert resp.status_code == 200
    data = resp.json()
    assert (data["delivery"], data["fps"], data["derive"]) == ("2k", 25, "16:9")
    assert data["dims"]["delivery"] == {"w": 1440, "h": 2560}
    # Persisted; derive can be cleared again.
    assert client.get(SPEC).json()["fps"] == 25
    assert client.put(SPEC, json={"derive": None}).json()["derive"] is None
    # Same aspect as now is not a change, even when locked.
    assert client.put(SPEC, json={"aspect": "9:16"}).status_code == 200


def test_put_spec_invalid(client: TestClient) -> None:
    assert client.put(SPEC, json={"fps": 60}).status_code == 422
    assert client.put(SPEC, json={"aspect": "4:3"}).status_code == 422
    assert client.put(SPEC, json={"codec": "hevc"}).status_code == 422  # not editable here
    resp = client.put("/api/v1/series/nope/spec", json={"fps": 24})
    assert resp.status_code == 404 and _code(resp) == "series_not_found"


def test_locked_aspect_change_needs_confirmed_impact(client: TestClient) -> None:
    resp = client.put(SPEC, json={"aspect": "16:9", "platform": "wide"})
    assert resp.status_code == 409 and _code(resp) == "spec_locked"
    assert resp.json()["detail"]["params"] == {"aspect": "9:16"}
    assert client.get(SPEC).json()["aspect"] == "9:16"  # nothing written

    wide = {"aspect": "16:9", "platform": "wide"}
    # An id that is no applied 改画幅 preview of this series to this aspect is refused like none.
    assert client.put(f"{SPEC}?confirmed_impact=imp_1", json=wide).status_code == 409
    change = {"kind": "spec_aspect", "target_id": "demo", "patch": wide}
    impact = client.post("/api/v1/impact/preview", json=change).json()["id"]
    assert client.put(f"{SPEC}?confirmed_impact={impact}", json=wide).status_code == 409

    # Applying it writes the spec; saving the same aspect with it afterwards changes nothing.
    resp = client.post("/api/v1/impact/apply", json={"impact_id": impact, "action": "mark"})
    assert resp.status_code == 200
    resp = client.put(f"{SPEC}?confirmed_impact={impact}", json=wide)
    assert resp.status_code == 200
    data = resp.json()
    assert (data["aspect"], data["platform"]) == ("16:9", "wide")
    assert data["dims"] == {"delivery": {"w": 1920, "h": 1080}, "draft": {"w": 1366, "h": 768}}
    assert data["locked_at"] is not None  # still locked
    # Not for another aspect.
    resp = client.put(f"{SPEC}?confirmed_impact={impact}", json={"aspect": "1:1"})
    assert resp.status_code == 409 and _code(resp) == "spec_locked"


def test_presets(client: TestClient) -> None:
    data = client.get("/api/v1/spec/presets").json()
    assert data["platforms"] == [
        {"id": "cn", "aspect": "9:16", "delivery": "1080p"},
        {"id": "intl", "aspect": "9:16", "delivery": "1080p"},
        {"id": "wide", "aspect": "16:9", "delivery": "1080p"},
        {"id": "custom", "aspect": None, "delivery": None},
    ]
    assert list(data["dims"]) == ["9:16", "16:9", "3:4", "1:1", "21:9"]
    assert data["dims"]["21:9"]["2k"] == {"w": 2976, "h": 1248}
    assert set(data["safe_areas"]) == {"vertical_app", "vertical_player", "horizontal"}


def test_compat(client: TestClient) -> None:
    data = client.get(f"{SPEC}/compat").json()
    assert data["aspect"] == "9:16" and len(data["rows"]) == 7
    assert data["rows"][0] == {
        "stage": "keyframe",
        "model_keys": ["google/nano-banana-2.1"],
        "status": "native",
        "how": {"code": "native_4k", "params": {}},
    }
    data = client.get(f"{SPEC}/compat", params={"aspect": "21:9"}).json()
    assert data["aspect"] == "21:9"
    assert data["rows"][0]["status"] == "native"  # Nano Banana Pro makes 21:9 itself
    assert data["rows"][5]["how"]["code"] == "upscale_from_720p"  # Seedance
    assert client.get(f"{SPEC}/compat", params={"aspect": "4:3"}).status_code == 422
    resp = client.get("/api/v1/series/nope/spec/compat")
    assert resp.status_code == 404 and _code(resp) == "series_not_found"
