"""``/config/components|resolve|override|defaults`` (SPEC 7.1–7.3, 9.1)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from drama_series_agent.api.app import create_app
from drama_series_agent.core.capabilities import Capabilities
from drama_series_agent.core.config import get_config
from drama_series_agent.modelhub.catalog import catalog

LOCAL = "http://127.0.0.1"
CLIENT_HEADERS = {"X-Drama-Studio": "1"}
V1 = "/api/v1/config"


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(), base_url=LOCAL, headers=CLIENT_HEADERS) as c:
        yield c


def _code(resp: object) -> str:
    return resp.json()["detail"]["code"]  # type: ignore[attr-defined,no-any-return]


def test_components_catalog(client: TestClient) -> None:
    data = client.get(f"{V1}/components").json()
    ids = [c["id"] for c in data["components"]]
    assert ids[:4] == ["extract", "enrich", "split", "script"] and "sfx" in ids
    enrich = next(c for c in data["components"] if c["id"] == "enrich")
    assert enrich["api_models"][0] == "deepseek/v4-pro"
    assert "custom" not in enrich["api_models"]  # custom models come later
    assert enrich["local_models"] == ["local/qwen3.6-27b", "local/qwen3-30b-a3b"]
    assert enrich["unavailable"] == {}  # never scanned: nothing filtered
    prices = {m["key"]: m["price"] for m in data["models"]}
    assert prices["deepseek/v4-pro"] == {"unit": "mtok", "in": 1.32, "out": 3.96, "currency": "USD"}
    assert prices["google/nano-banana-pro"] == {"unit": "image", "amount": 0.14, "currency": "USD"}
    assert prices["minimax/h3-api"]["amount"] == 0.08  # from the draft tier
    assert prices["volc/seedance-2.5"]["unit"] == "second"
    assert prices["minimax/speech-2.8-hd"] == {"unit": "mchar", "amount": 100.0, "currency": "USD"}
    assert prices["elevenlabs/music"] is None  # a subscription
    assert prices["local/qwen3.6-27b"] is None
    assert data["local_runtime_ok"] is True


def test_machine_reasons() -> None:
    cfg = get_config()
    bare = Capabilities.of(cuda=False, found=set())
    defs = {d.id: d for d in catalog(cfg, bare).components}
    assert defs["vid"].unavailable["local"].code == "machine_cuda"
    assert set(defs["vid"].unavailable) == {"local", "hybrid"}
    assert defs["img"].unavailable["local"].code == "machine_missing"
    assert defs["img"].unavailable["local"].params == {"count": 1}  # FLUX.2 only needs ComfyUI
    pc = Capabilities.of(cuda=True, found={"comfy", "w_img"})
    assert catalog(cfg, pc).components[5].unavailable == {}


def test_resolve(client: TestClient) -> None:
    data = client.get(f"{V1}/resolve", params={"component": "script"}).json()
    assert data["component_id"] == "script" and data["item"] is None
    assert data["values"]["api_model"] == "deepseek/v4-pro"
    assert data["values"]["fallback"]["timeout_s"] == 600
    assert set(data["sources"].values()) == {"preset"}
    assert set(data["sources"]) == {
        "mode", "api_model", "local_model", "fallback", "alt_order", "per_call_cap_usd"
    }  # fmt: skip
    resp = client.get(f"{V1}/resolve", params={"component": "nope"})
    assert resp.status_code == 404 and _code(resp) == "unknown_component"


def test_override_levels(client: TestClient) -> None:
    body = {"scope": "component", "scope_id": None, "component_id": "enrich"}
    data = client.put(f"{V1}/override", json={**body, "data": {"api_model": "qwen/qwen3.8-max"}})
    assert data.json()["sources"]["api_model"] == "component"
    # One field at a time; earlier fields stay.
    data = client.put(f"{V1}/override", json={**body, "data": {"per_call_cap_usd": 0.9}}).json()
    assert data["values"]["api_model"] == "qwen/qwen3.8-max"
    assert data["values"]["per_call_cap_usd"] == 0.9

    item = {"scope": "item", "scope_id": "shot:1-05", "component_id": "enrich"}
    data = client.put(f"{V1}/override", json={**item, "data": {"mode": "hybrid"}}).json()
    assert data["item"] == "shot:1-05" and data["sources"]["mode"] == "item"
    plain = client.get(f"{V1}/resolve", params={"component": "enrich"}).json()
    assert plain["values"]["mode"] == "api"

    # A project-level value applies to every component.
    project = {"scope": "project", "scope_id": None, "component_id": "enrich"}
    client.put(f"{V1}/override", json={**project, "data": {"per_call_cap_usd": 2}})
    split = client.get(f"{V1}/resolve", params={"component": "split"}).json()
    assert (
        split["values"]["per_call_cap_usd"] == 2
        and split["sources"]["per_call_cap_usd"] == "project"
    )

    resp = client.put(f"{V1}/override", json={**body, "data": {"api_model": "no/such"}})
    assert resp.status_code == 422 and _code(resp) == "unknown_model"
    resp = client.put(f"{V1}/override", json={**item, "scope_id": None, "data": {"mode": "api"}})
    assert resp.status_code == 422 and _code(resp) == "scope_id_required"
    resp = client.put(f"{V1}/override", json={**body, "component_id": "nope", "data": {}})
    assert resp.status_code == 404


def test_reset_override(client: TestClient) -> None:
    body = {"scope": "component", "scope_id": None, "component_id": "vid"}
    fallback = {
        "enabled": True,
        "on": ["error"],
        "qa_fail_n": 3,
        "timeout_s": 300,
        "to": "volc/seedance-2.5",
        "notify": "ask",
    }
    data = client.put(f"{V1}/override", json={**body, "data": {"fallback": fallback}}).json()
    assert data["values"]["fallback"] == fallback and data["sources"]["fallback"] == "component"
    data = client.delete(f"{V1}/override", params={"scope": "component", "component_id": "vid"})
    assert data.json()["sources"]["fallback"] == "preset"
    resp = client.delete(f"{V1}/override", params={"scope": "component", "component_id": "x"})
    assert resp.status_code == 404


def test_defaults(client: TestClient) -> None:
    assert client.get(f"{V1}/defaults").json() == {"preset": "balanced", "fallback_notify": "after"}
    body = {"scope": "component", "scope_id": None, "component_id": "split"}
    client.put(f"{V1}/override", json={**body, "data": {"api_model": "qwen/qwen3.8-max"}})
    data = client.put(f"{V1}/defaults", json={"preset": "cheap"}).json()
    assert data == {"preset": "cheap", "fallback_notify": "after"}
    enrich = client.get(f"{V1}/resolve", params={"component": "enrich"}).json()
    assert enrich["values"]["mode"] == "local" and enrich["sources"]["mode"] == "preset"
    # A component changed by hand keeps its value (SPEC 7.2).
    split = client.get(f"{V1}/resolve", params={"component": "split"}).json()
    assert split["values"]["api_model"] == "qwen/qwen3.8-max"
    data = client.put(f"{V1}/defaults", json={"fallback_notify": "ask"}).json()
    assert data == {"preset": "cheap", "fallback_notify": "ask"}
    resp = client.put(f"{V1}/defaults", json={"preset": "fastest"})
    assert resp.status_code == 422
