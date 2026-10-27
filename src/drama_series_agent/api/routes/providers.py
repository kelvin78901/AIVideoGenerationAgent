"""``/api/v1/providers``: writing-model providers, their sites, keys and "test connection".

Keys are write-only: responses only ever say whether a key is present and where it comes
from (keyring or environment), never the key itself. Media models that use a provider's key
(``account`` in providers.yaml: pictures, voices) are listed with it and tested with it.

A provider with a China and an international site (``sites``: separate accounts, separate keys)
is on one of them at a time (``provider_account.site``, default ``default_site``); switching
rebuilds its models' specs (address, key, prices) in the registry (M5 step 7a).
"""

from __future__ import annotations

import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from drama_series_agent.api.errors import ApiError
from drama_series_agent.api.state import StudioState, get_state, provider_accounts
from drama_series_agent.core import secrets
from drama_series_agent.core.config import LlmProvider, Site, get_config
from drama_series_agent.core.models_db import ProviderAccount, utcnow
from drama_series_agent.modelhub.adapters.base import ModelSpec
from drama_series_agent.modelhub.adapters.openai_compat import OpenAICompatAdapter
from drama_series_agent.modelhub.media_adapters import has_media_adapter, media_adapter

router = APIRouter(prefix="/providers", tags=["providers"])

State = Annotated[StudioState, Depends(get_state)]


class KeyBody(BaseModel):
    api_key: str = Field(min_length=1, max_length=4096)
    site: str | None = Field(default=None, max_length=16)  # None: the account's current site


class AccountBody(BaseModel):
    site: str | None = Field(default=None, max_length=16)


def _provider(provider_id: str) -> LlmProvider:
    provider = get_config().providers.provider(provider_id)
    if provider is None:
        raise ApiError(404, "provider_not_found", id=provider_id)
    return provider


async def _account(session: AsyncSession, provider_id: str) -> ProviderAccount:
    row = await session.get(ProviderAccount, provider_id)
    return row or ProviderAccount(provider_id=provider_id)


def _media_specs(state: StudioState, provider_id: str) -> list[ModelSpec]:
    """The media models with a real adapter that use this provider's key (as the registry has
    them: the account's current site)."""
    accounts = {m.key: m.account for m in get_config().providers.media_models}
    return [
        s
        for s in state.registry.specs()
        if accounts.get(s.key) == provider_id and has_media_adapter(s)
    ]


def _key_source(place: Site) -> str:
    return secrets.has_secret(place.key_name) if place.key_name else "none"


def _public(state: StudioState, provider: LlmProvider, account: ProviderAccount) -> dict[str, Any]:
    site, place = provider.site(account.site)
    source = _key_source(place)
    return {
        "id": provider.id,
        "name": provider.name,
        "where": provider.where,
        "site": site,
        "sites": [
            {
                "id": name,
                "base_url": other.base_url,
                "docs": other.docs,
                "has_key": _key_source(other) != "none",
            }
            for name, other in provider.sites.items()
        ],
        "base_url": account.base_url_override or place.base_url,
        "docs": place.docs,
        "verify": provider.verify,
        "needs_key": place.key_name is not None,
        "has_key": source != "none",
        "key_source": source,
        "enabled": account.enabled,
        "models": [
            {
                "key": m.key,
                "display": m.display,
                "model_id": m.model_id,
                "price": m.price.model_dump(by_alias=True) if m.price else None,
                "json_mode": m.json_mode,
            }
            for m in (row.on_site(site) for row in provider.models)
        ],
        "media": [{"key": s.key, "display": s.display} for s in _media_specs(state, provider.id)],
    }


def _place(provider: LlmProvider, site: str | None, account: ProviderAccount) -> Site:
    """The site a key call means: the one named, else the account's current one."""
    if site is not None and site not in provider.sites:
        raise ApiError(422, "unknown_site", id=provider.id, site=site)
    return provider.site(site or account.site)[1]


@router.get("")
async def list_providers(state: State) -> dict[str, Any]:
    cfg = get_config().providers
    async with state.db.session() as session:
        items = [_public(state, p, await _account(session, p.id)) for p in cfg.llm_providers]
    return {"providers": items, "llm_ui_order": cfg.llm_ui_order}


async def _save_has_key(state: StudioState, provider: LlmProvider) -> dict[str, Any]:
    async with state.db.session() as session:
        account = await _account(session, provider.id)
        place = provider.site(account.site)[1]
        account.has_key = _key_source(place) != "none"
        account.key_ref = f"{secrets.SERVICE}:{place.key_name}" if account.has_key else None
        account.updated_at = utcnow()
        session.add(account)
        await session.commit()
        await session.refresh(account)
        return _public(state, provider, account)


@router.patch("/{provider_id}")
async def update_account(provider_id: str, body: AccountBody, state: State) -> dict[str, Any]:
    """Switch the provider to another of its sites: its models (and the media models on its
    key) are called there from now on, with that site's key and prices."""
    provider = _provider(provider_id)
    if body.site is not None and body.site not in provider.sites:
        raise ApiError(422, "unknown_site", id=provider.id, site=body.site)
    async with state.db.session() as session:
        account = await _account(session, provider.id)
        if body.site is not None:
            account.site = body.site
        account.updated_at = utcnow()
        session.add(account)
        await session.commit()
    state.registry.set_account(get_config(), provider.id, await provider_accounts(state.db))
    return await _save_has_key(state, provider)


@router.post("/{provider_id}/key")
async def set_key(provider_id: str, body: KeyBody, state: State) -> dict[str, Any]:
    provider = _provider(provider_id)
    async with state.db.session() as session:
        place = _place(provider, body.site, await _account(session, provider.id))
    if place.key_name is None:
        raise ApiError(400, "provider_needs_no_key", id=provider_id)
    try:
        secrets.set_secret(place.key_name, body.api_key)
    except secrets.SecretStoreError as exc:
        raise ApiError(503, "keyring_unavailable", reason=str(exc)) from None
    except ValueError:
        raise ApiError(422, "empty_key") from None
    return await _save_has_key(state, provider)


@router.delete("/{provider_id}/key")
async def delete_key(
    provider_id: str,
    state: State,
    site: Annotated[str | None, Query(max_length=16)] = None,
) -> dict[str, Any]:
    provider = _provider(provider_id)
    async with state.db.session() as session:
        place = _place(provider, site, await _account(session, provider.id))
    if place.key_name is None:
        raise ApiError(400, "provider_needs_no_key", id=provider_id)
    try:
        secrets.delete_secret(place.key_name)
    except secrets.SecretStoreError as exc:
        raise ApiError(503, "keyring_unavailable", reason=str(exc)) from None
    return await _save_has_key(state, provider)


@router.post("/{provider_id}/test")
async def test_connection(provider_id: str, state: State) -> dict[str, Any]:
    """``GET /models`` on the account's current site with that site's key: checks the key and
    lists real model ids; then each media model on this key checks its own model id (free
    calls only, never a generation)."""
    provider = _provider(provider_id)
    async with state.db.session() as session:
        account = await _account(session, provider.id)
    site, place = provider.site(account.site)
    base_url = account.base_url_override or place.base_url
    if not base_url:
        raise ApiError(400, "base_url_missing", id=provider_id)
    spec = ModelSpec(
        key=f"{provider.id}/*",
        kind="llm",
        where=provider.where,
        display=provider.name,
        provider_id=provider.id,
        base_url=base_url,
        key_name=place.key_name,
    )
    adapter = OpenAICompatAdapter(spec, get_key=secrets.get_secret, transport=state.http_transport)
    media = _media_specs(state, provider.id)
    health, *checks = await asyncio.gather(
        adapter.health(),
        *(
            media_adapter(
                m, get_key=secrets.get_secret, store=state.store, transport=state.http_transport
            ).health()
            for m in media
        ),
    )
    return {
        "ok": health.ok,
        "detail": health.detail,
        "site": site,
        "models": health.models,
        "media": [
            {"key": m.key, "display": m.display, "ok": h.ok, "detail": h.detail}
            for m, h in zip(media, checks, strict=True)
        ],
    }
