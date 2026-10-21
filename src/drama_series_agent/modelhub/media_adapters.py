"""Real adapters for media models, chosen by ``adapter`` in ``providers.yaml`` (hard rule 7:
a new model of a known kind is a config row; a new API is a new entry here)."""

from __future__ import annotations

import httpx

from drama_series_agent.core.storage import BlobStore
from drama_series_agent.modelhub.adapters.base import ModelAdapter, ModelSpec
from drama_series_agent.modelhub.adapters.google import GeminiImageAdapter
from drama_series_agent.modelhub.adapters.http import KeyGetter
from drama_series_agent.modelhub.adapters.images import ImageApiAdapter
from drama_series_agent.modelhub.adapters.openai_images import OpenAIImageAdapter
from drama_series_agent.modelhub.adapters.volcengine import SeedreamAdapter

MEDIA_ADAPTERS: dict[str, type[ImageApiAdapter]] = {
    "gemini_image": GeminiImageAdapter,
    "openai_images": OpenAIImageAdapter,
    "seedream": SeedreamAdapter,
}


def has_media_adapter(spec: ModelSpec) -> bool:
    return spec.where == "api" and spec.adapter in MEDIA_ADAPTERS


def media_adapter(
    spec: ModelSpec,
    *,
    get_key: KeyGetter,
    store: BlobStore,
    transport: httpx.AsyncBaseTransport | None = None,
) -> ModelAdapter:
    cls = MEDIA_ADAPTERS[spec.adapter or ""]
    return cls(spec, get_key=get_key, store=store, transport=transport)
