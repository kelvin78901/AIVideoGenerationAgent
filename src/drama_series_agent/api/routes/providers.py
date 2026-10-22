"""``/api/v1/providers``: writing-model providers, their keys and "test connection".

Keys are write-only: responses only ever say whether a key is present and where it comes
from (keyring or environment), never the key itself. Media models that use a provider's key
(``account`` in providers.yaml: pictures, voices) are listed with it and tested with it.
"""

from __future__ import annotations

import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from drama_series_agent.api.errors import ApiError
from drama_series_agent.api.state import StudioState, get_state
from drama_series_agent.core import secrets
from drama_series_agent.core.config import LlmProvider, get_config
from drama_series_agent.core.models_db import ProviderAccount, utcnow
from drama_series_agent.modelhub.adapters.base import ModelSpec
from drama_series_agent.modelhub.adapters.openai_compat import OpenAICompatAdapter
from drama_series_agent.modelhub.media_adapters import has_media_adapter, media_adapter
from drama_series_agent.modelhub.registry import specs_from_config

router = APIRouter(prefix="/providers", tags=["providers"])

State = Annotated[StudioState, Depends(get_state)]


class KeyBody(BaseModel):
    api_key: str = Field(min_length=1, max_length=4096)


def _provider(provider_id: str) -> LlmProvider:
    provider = get_config().providers.provider(provider_id)
    if provider is None:
        raise ApiError(404, "provider_not_found", id=provider_id)
    return provider


async def _account(session: AsyncSession, provider_id: str) -> ProviderAccount:
    row = await session.get(ProviderAccount, provider_id)
    return row or ProviderAccount(provider_id=provider_id)


def _media_specs(provider_id: str) -> list[ModelSpec]:
    """The media models with a real adapter that use this provider's key."""
    cfg = get_config()
    accounts = {m.key: m.account for m in cfg.providers.media_models}
    return [
        s
        for s in specs_from_config(cfg)
        if accounts.get(s.key) == provider_id and has_media_adapter(s)
    ]


def _public(provider: LlmProvider, account: ProviderAccount) -> dict[str, Any]:
    source = secrets.has_secret(provider.key_name) if provider.key_name else "none"
    return {
        "id": provider.id,
        "name": provider.name,
        "where": provider.where,
        "base_url": account.base_url_override or provider.base_url,
        "docs": provider.docs,
        "verify": provider.verify,
        "needs_key": provider.key_name is not None,
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
            for m in provider.models
        ],
        "media": [{"key": s.key, "display": s.display} for s in _media_specs(provider.id)],
    }


@router.get("")
async def list_providers(state: State) -> dict[str, Any]:
    cfg = get_config().providers
    async with state.db.session() as session:
        items = [_public(p, await _account(session, p.id)) for p in cfg.llm_providers]
    return {"providers": items, "llm_ui_order": cfg.llm_ui_order}


async def _save_has_key(state: StudioState, provider: LlmProvider) -> dict[str, Any]:
    async with state.db.session() as session:
        account = await _account(session, provider.id)
        account.has_key = secrets.has_secret(provider.key_name or "") != "none"
        account.key_ref = f"{secrets.SERVICE}:{provider.key_name}" if account.has_key else None
        account.updated_at = utcnow()
        session.add(account)
        await session.commit()
        await session.refresh(account)
        return _public(provider, account)


@router.post("/{provider_id}/key")
async def set_key(provider_id: str, body: KeyBody, state: State) -> dict[str, Any]:
    provider = _provider(provider_id)
    if provider.key_name is None:
        raise ApiError(400, "provider_needs_no_key", id=provider_id)
    try:
        secrets.set_secret(provider.key_name, body.api_key)
    except secrets.SecretStoreError as exc:
        raise ApiError(503, "keyring_unavailable", reason=str(exc)) from None
    except ValueError:
        raise ApiError(422, "empty_key") from None
    return await _save_has_key(state, provider)


@router.delete("/{provider_id}/key")
async def delete_key(provider_id: str, state: State) -> dict[str, Any]:
    provider = _provider(provider_id)
    if provider.key_name is None:
        raise ApiError(400, "provider_needs_no_key", id=provider_id)
    try:
        secrets.delete_secret(provider.key_name)
    except secrets.SecretStoreError as exc:
        raise ApiError(503, "keyring_unavailable", reason=str(exc)) from None
    return await _save_has_key(state, provider)


@router.post("/{provider_id}/test")
async def test_connection(provider_id: str, state: State) -> dict[str, Any]:
    """``GET /models`` with the stored key: checks the key and lists real model ids; then each
    media model on this key checks its own model id (free calls only, never a generation)."""
    provider = _provider(provider_id)
    async with state.db.session() as session:
        account = await _account(session, provider.id)
    base_url = account.base_url_override or provider.base_url
    if not base_url:
        raise ApiError(400, "base_url_missing", id=provider_id)
    spec = ModelSpec(
        key=f"{provider.id}/*",
        kind="llm",
        where=provider.where,
        display=provider.name,
        provider_id=provider.id,
        base_url=base_url,
        key_name=provider.key_name,
    )
    adapter = OpenAICompatAdapter(spec, get_key=secrets.get_secret, transport=state.http_transport)
    media = _media_specs(provider.id)
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
        "models": health.models,
        "media": [
            {"key": m.key, "display": m.display, "ok": h.ok, "detail": h.detail}
            for m, h in zip(media, checks, strict=True)
        ],
    }
