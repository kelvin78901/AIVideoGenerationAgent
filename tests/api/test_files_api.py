"""``GET /files/{sha256}`` (M3): blobs by content hash, typed by their first bytes, seekable."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from drama_series_agent.api.app import create_app
from drama_series_agent.api.state import StudioState
from drama_series_agent.modelhub.adapters.mock import sine_wav, solid_png

V1 = "/api/v1"


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(), base_url="http://127.0.0.1") as c:
        yield c


def _store(client: TestClient, data: bytes) -> str:
    state: StudioState = client.app.state.studio  # type: ignore[attr-defined]
    return state.store.put_bytes(data)


def test_serves_a_blob_with_its_type(client: TestClient) -> None:
    png = solid_png(2, 2, (10, 20, 30))
    resp = client.get(f"{V1}/files/{_store(client, png)}")
    assert resp.status_code == 200 and resp.content == png
    assert resp.headers["content-type"] == "image/png"
    assert "immutable" in resp.headers["cache-control"]
    wav = sine_wav(0.1)
    resp = client.get(f"{V1}/files/{_store(client, wav)}")
    assert resp.headers["content-type"] == "audio/wav"


def test_range_requests_let_a_player_seek(client: TestClient) -> None:
    wav = sine_wav(0.2)
    resp = client.get(f"{V1}/files/{_store(client, wav)}", headers={"Range": "bytes=100-199"})
    assert resp.status_code == 206 and resp.content == wav[100:200]


def test_only_known_hashes(client: TestClient) -> None:
    for name in ["0" * 64, "../studio.db", "A" * 64, "x"]:
        resp = client.get(f"{V1}/files/{name}")
        assert resp.status_code == 404, name
