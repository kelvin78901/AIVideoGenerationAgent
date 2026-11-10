"""A provider's China / international site (M5 step 7a-1): config, per-site keys, switching
rebuilds the registry's specs, test connection on the current site. Never the network."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlmodel import select

from drama_series_agent.api.app import create_app
from drama_series_agent.api.state import StudioState
from drama_series_agent.core import secrets
from drama_series_agent.core.config import (
    Accounts,
    AccountState,
    LlmProvider,
    ModelSetting,
    get_config,
    set_accounts,
)
from drama_series_agent.core.models_db import ModelCall
from drama_series_agent.modelhub.adapters.base import CallContext, ModelRequest
from drama_series_agent.modelhub.registry import specs_from_config

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
    intl = AccountState(site="intl")
    set_accounts(Accounts(providers={"moonshot": intl, "minimax_llm": intl}))
    by_key = {s.key: s for s in specs_from_config(get_config())}
    kimi, h3 = by_key["moonshot/kimi-k2.6"], by_key["minimax/h3-api"]
    assert (kimi.base_url, kimi.key_name) == (INTL, "MOONSHOT_INTL_API_KEY")
    assert kimi.pricing.currency == "USD"
    assert (h3.base_url, h3.key_name) == ("https://api.minimax.io/v1", "MINIMAX_INTL_API_KEY")
    assert h3.pricing.currency == "USD" and h3.pricing.price_by_res == {"768p": 0.08, "2k": 0.13}
    # An address override (a proxy) wins over the site's.
    set_accounts(
        Accounts(providers={"moonshot": AccountState(base_url="http://127.0.0.1:9999/v1")})
    )
    kimi = {s.key: s for s in specs_from_config(get_config())}["moonshot/kimi-k2.6"]
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


# ---------------------------------------------------------------------- 7a-2: model lists


def test_the_overlay_turns_picks_into_models() -> None:
    from drama_series_agent.core.config import Accounts, AccountState, set_accounts

    picks = ("kimi-k3.1-pro", "kimi-k2.7-code")
    set_accounts(
        Accounts(
            providers={"moonshot": AccountState(listed=(*picks, "kimi-k2.6"), enabled=picks)},
            settings={
                "moonshot/kimi-k2.7-code": ModelSetting(
                    price={"in": 4, "out": 16, "currency": "CNY"}
                )
            },
        )
    )
    cfg = get_config()
    kimi = cfg.providers.provider("moonshot")
    assert kimi is not None
    assert [m.key for m in kimi.models] == ["moonshot/kimi-k3.1-pro", "moonshot/kimi-k2.7-code"]
    listed = kimi.models[1]
    # Not in the table: the provider's defaults, the user's price.
    assert listed.display == "kimi-k2.7-code" and listed.json_mode is True
    assert listed.price is not None and (listed.price.in_, listed.price.currency) == (4, "CNY")
    assert len(kimi.table) == 2  # the whole reference table stays known
    api = cfg.components.component("script").api
    assert "moonshot/kimi-k2.7-code" in api and "moonshot/kimi-k2.6" not in api
    assert "deepseek/v4-pro" in api  # never listed: its reference table stands


def test_a_listed_model_is_picked_priced_and_called(
    client: TestClient, respx_mock: respx.MockRouter
) -> None:

    from drama_series_agent.core.models_db import ModelCall

    respx_mock.route(host="127.0.0.1").pass_through()
    client.post(f"{V1}/moonshot/key", json={"api_key": "sk-china-0123456789"}).raise_for_status()
    ids = ["kimi-k2.6", "kimi-k2.7-code", "kimi-k3.1-pro"]
    respx_mock.get(f"{CN}/models").mock(
        return_value=httpx.Response(200, json={"data": [{"id": i} for i in ids]})
    )
    client.post(f"{V1}/moonshot/test").raise_for_status()
    listed = _provider(client, "moonshot")["listed"]
    rows = {r["model_id"]: r for r in listed["models"]}
    # First fetch: the models the reference table knows are picked.
    assert {m for m, r in rows.items() if r["enabled"]} == {"kimi-k2.6", "kimi-k3.1-pro"}
    assert rows["kimi-k3.1-pro"]["price"] == {"in": 13.0, "out": 68.0, "currency": "CNY"}
    assert (
        rows["kimi-k2.7-code"]["price"] is None and rows["kimi-k2.7-code"]["price_source"] is None
    )
    registry = _state(client).registry
    assert "moonshot/kimi-k2.7-code" not in {s.key for s in registry.specs()}

    body = {"enabled": ["kimi-k3.1-pro", "kimi-k2.7-code"]}
    client.put(f"{V1}/moonshot/models", json=body).raise_for_status()
    spec = registry.spec("moonshot/kimi-k2.7-code")
    assert spec.model_id == "kimi-k2.7-code" and spec.base_url == CN and not spec.pricing.known
    assert "moonshot/kimi-k2.6" not in {s.key for s in registry.specs()}  # unpicked
    catalog = client.get("/api/v1/config/components").json()
    script = next(c for c in catalog["components"] if c["id"] == "script")
    assert "moonshot/kimi-k2.7-code" in script["api_models"]

    # A price of one's own, then a Mock call is recorded at it.
    price = {"in": 4, "out": 16, "currency": "CNY"}
    resp = client.put(f"{V1}/settings/moonshot/kimi-k2.7-code", json={"price": price})
    assert resp.status_code == 200, resp.text
    assert registry.spec("moonshot/kimi-k2.7-code").pricing.known

    async def call() -> list[ModelCall]:
        state = _state(client)
        req = ModelRequest(kind="llm", prompt="林晚推门。")
        await state.router.call("script", req, CallContext(), model="moonshot/kimi-k2.7-code")
        async with state.db.session() as s:
            return list((await s.exec(select(ModelCall))).all())

    (row,) = client.portal.call(call)  # type: ignore[union-attr]
    assert row.model_key == "moonshot/kimi-k2.7-code" and row.cost_usd > 0
    assert _provider(client, "moonshot")["listed"]["models"][1]["price_source"] == "user"

    assert client.put(f"{V1}/moonshot/models", json={"enabled": ["gpt-9"]}).status_code == 422
    assert client.put(f"{V1}/deepseek/models", json={"enabled": []}).status_code == 409
    assert client.put(f"{V1}/settings/no/such", json={}).status_code == 404
    client.delete(f"{V1}/settings/moonshot/kimi-k2.7-code").raise_for_status()
    assert not registry.spec("moonshot/kimi-k2.7-code").pricing.known

    # Another site is another account: its list starts over.
    client.patch(f"{V1}/moonshot", json={"site": "intl"}).raise_for_status()
    assert _provider(client, "moonshot")["listed"] is None
    assert "moonshot/kimi-k2.6" in {s.key for s in registry.specs()}  # the table again


def test_pickers_flag_models_without_a_price_and_media_ids_can_change(client: TestClient) -> None:
    catalog = client.get("/api/v1/config/components").json()
    priced = {m["key"]: m["priced"] for m in catalog["models"]}
    assert priced["deepseek/v4-pro"] and priced["local/qwen3.6-27b"]
    assert not priced["openrouter/any"] and not priced["kling/kling-3.0"]

    media = _provider(client, "minimax_llm")["media"]
    h3 = next(m for m in media if m["key"] == "minimax/h3-api")
    assert h3["model_id"] and h3["custom_model_id"] is False
    resp = client.put(f"{V1}/settings/minimax/h3-api", json={"model_id": "MiniMax-H3.1"})
    assert resp.status_code == 200, resp.text
    h3 = next(m for m in _provider(client, "minimax_llm")["media"] if m["key"] == "minimax/h3-api")
    assert (h3["model_id"], h3["custom_model_id"]) == ("MiniMax-H3.1", True)
    assert _state(client).registry.spec("minimax/h3-api").model_id == "MiniMax-H3.1"
    client.delete(f"{V1}/settings/minimax/h3-api").raise_for_status()
    h3 = next(m for m in _provider(client, "minimax_llm")["media"] if m["key"] == "minimax/h3-api")
    assert h3["custom_model_id"] is False and h3["model_id"] != "MiniMax-H3.1"
