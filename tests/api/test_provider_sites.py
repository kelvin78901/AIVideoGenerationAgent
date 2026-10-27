"""A provider's China / international site (M5 step 7a-1): config, per-site keys, switching
rebuilds the registry's specs, test connection on the current site. Never the network."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from drama_series_agent.api.app import create_app
from drama_series_agent.api.state import StudioState
from drama_series_agent.core import secrets
from drama_series_agent.core.config import LlmProvider, get_config
from drama_series_agent.modelhub.registry import Account, specs_from_config

LOCAL = "http://127.0.0.1"
V1 = "/api/v1/providers"
CN, INTL = "https://api.moonshot.cn/v1", "https://api.moonshot.ai/v1"


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(), base_url=LOCAL, headers={"X-Drama-Studio": "1"}) as c:
        yield c


def _state(client: TestClient) -> StudioState:
    state: StudioState = client.app.state.studio  # type: ignore[attr-defined]
    return state


def _provider(client: TestClient, provider_id: str) -> dict[str, Any]:
    data = client.get(V1).json()["providers"]
    found: dict[str, Any] = next(p for p in data if p["id"] == provider_id)
    return found


def test_one_site_or_two() -> None:
    one = LlmProvider.model_validate(
        {"id": "x", "name": "X", "base_url": "https://x/v1", "key_name": "X_KEY"}
    )
    assert list(one.sites) == ["main"] and one.default_site == "main"
    assert one.site("intl") == ("main", one.sites["main"])
    two = LlmProvider.model_validate(
        {
            "id": "y",
            "name": "Y",
            "default_site": "cn",
            "sites": {
                "intl": {"base_url": "https://y.ai/v1", "key_name": "Y_INTL_KEY"},
                "cn": {"base_url": "https://y.cn/v1", "key_name": "Y_KEY"},
            },
        }
    )
    # The flat fields mirror the default site (older code reads them).
    assert (two.base_url, two.key_name) == ("https://y.cn/v1", "Y_KEY")
    assert two.site("intl")[1].key_name == "Y_INTL_KEY" and two.site(None)[0] == "cn"


def test_specs_follow_the_account_site() -> None:
    cfg = get_config()
    by_key = {s.key: s for s in specs_from_config(cfg)}
    kimi, h3 = by_key["moonshot/kimi-k2.6"], by_key["minimax/h3-api"]
    # Default: the China sites.
    assert (kimi.base_url, kimi.key_name) == (CN, "MOONSHOT_API_KEY")
    assert kimi.pricing.currency == "CNY" and h3.pricing.currency == "CNY"
    accounts = {"moonshot": Account(site="intl"), "minimax_llm": Account(site="intl")}
    by_key = {s.key: s for s in specs_from_config(cfg, accounts)}
    kimi, h3 = by_key["moonshot/kimi-k2.6"], by_key["minimax/h3-api"]
    assert (kimi.base_url, kimi.key_name) == (INTL, "MOONSHOT_INTL_API_KEY")
    assert kimi.pricing.currency == "USD"
    assert (h3.base_url, h3.key_name) == ("https://api.minimax.io/v1", "MINIMAX_INTL_API_KEY")
    assert h3.pricing.currency == "USD" and h3.pricing.price_by_res == {"768p": 0.08, "2k": 0.13}
    # An address override (a proxy) wins over the site's.
    proxy = {"moonshot": Account(base_url="http://127.0.0.1:9999/v1")}
    kimi = {s.key: s for s in specs_from_config(cfg, proxy)}["moonshot/kimi-k2.6"]
    assert kimi.base_url == "http://127.0.0.1:9999/v1" and kimi.key_name == "MOONSHOT_API_KEY"


def test_switching_site_keeps_both_keys_and_rebuilds_specs(client: TestClient) -> None:
    kimi = _provider(client, "moonshot")
    assert kimi["site"] == "cn" and kimi["base_url"] == CN
    assert [s["id"] for s in kimi["sites"]] == ["cn", "intl"]
    resp = client.post(f"{V1}/moonshot/key", json={"api_key": "sk-china-0123456789"})
    assert resp.status_code == 200 and resp.json()["has_key"] is True
    assert secrets.get_secret("MOONSHOT_API_KEY") == "sk-china-0123456789"

    resp = client.patch(f"{V1}/moonshot", json={"site": "intl"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["site"] == "intl" and data["base_url"] == INTL and data["has_key"] is False
    assert {s["id"]: s["has_key"] for s in data["sites"]} == {"cn": True, "intl": False}
    spec = _state(client).registry.spec("moonshot/kimi-k2.6")
    assert (spec.base_url, spec.key_name) == (INTL, "MOONSHOT_INTL_API_KEY")
    # A key without a site goes to the current one; the China key stays.
    client.post(f"{V1}/moonshot/key", json={"api_key": "sk-intl-0123456789"}).raise_for_status()
    assert secrets.get_secret("MOONSHOT_INTL_API_KEY") == "sk-intl-0123456789"
    assert secrets.get_secret("MOONSHOT_API_KEY") == "sk-china-0123456789"
    client.delete(f"{V1}/moonshot/key", params={"site": "cn"}).raise_for_status()
    assert secrets.get_secret("MOONSHOT_API_KEY") is None

    # And back.
    client.patch(f"{V1}/moonshot", json={"site": "cn"}).raise_for_status()
    assert _state(client).registry.spec("moonshot/kimi-k2.6").base_url == CN


def test_site_errors(client: TestClient) -> None:
    resp = client.patch(f"{V1}/moonshot", json={"site": "mars"})
    assert resp.status_code == 422 and resp.json()["detail"]["code"] == "unknown_site"
    resp = client.post(f"{V1}/moonshot/key", json={"api_key": "sk-x-0123456789", "site": "mars"})
    assert resp.status_code == 422
    # A provider with one site has no other to switch to.
    assert client.patch(f"{V1}/deepseek", json={"site": "intl"}).status_code == 422
    assert client.patch(f"{V1}/nope", json={"site": "cn"}).status_code == 404


def test_connection_uses_the_current_site(client: TestClient, respx_mock: respx.MockRouter) -> None:
    """The case that started it: a China key is refused abroad and works at home."""
    client.post(f"{V1}/moonshot/key", json={"api_key": "sk-china-0123456789"}).raise_for_status()
    respx_mock.get(f"{CN}/models").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "kimi-k3.1-pro"}]})
    )
    respx_mock.get(f"{INTL}/models").mock(
        return_value=httpx.Response(401, json={"error": {"message": "Invalid Authentication"}})
    )
    data = client.post(f"{V1}/moonshot/test").json()
    assert data["ok"] is True and data["site"] == "cn" and data["models"] == ["kimi-k3.1-pro"]
    client.patch(f"{V1}/moonshot", json={"site": "intl"}).raise_for_status()
    client.post(f"{V1}/moonshot/key", json={"api_key": "sk-china-0123456789"}).raise_for_status()
    data = client.post(f"{V1}/moonshot/test").json()
    assert data["ok"] is False and data["site"] == "intl" and data["detail"] == "auth_failed"
