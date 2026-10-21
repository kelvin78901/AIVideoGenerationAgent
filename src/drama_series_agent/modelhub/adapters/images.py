"""What the picture adapters share (plan M3 「图像适配器」).

- **Request**: ``ModelRequest(kind="image", prompt, seed, params={n, width, height, aspect,
  refs, task})``. Width and height are the output-spec frame (hard rule 10); each adapter maps
  them to the nearest size its model takes (``fit_size``) and records the pixels it got back.
- **References** are sha256s of pictures in the blob store (``load_refs``).
- **n pictures** from a model that makes one per request are n requests at once
  (``one_per_request``); the pictures that came back are what was made and billed.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import math
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

import httpx

from drama_series_agent.core.storage import BlobStore
from drama_series_agent.media.image import NotAnImage, image_info
from drama_series_agent.modelhub.adapters.base import (
    CallContext,
    Estimate,
    Health,
    ModelError,
    ModelRequest,
    ModelResult,
    ModelSpec,
    OutputFile,
    Usage,
)
from drama_series_agent.modelhub.adapters.http import KeyGetter
from drama_series_agent.modelhub.pricing import cost_usd
from drama_series_agent.utils.llm_client import normalize_base_url


def fit_size(
    w: int,
    h: int,
    *,
    multiple: int = 16,
    min_pixels: int = 0,
    max_pixels: int | None = None,
    max_edge: int | None = None,
) -> tuple[int, int]:
    """The frame's aspect at the closest size the model takes: scaled into the pixel range and
    under the longest edge, both edges a ``multiple`` (rounded up, down when that overflows)."""
    scale = 1.0
    pixels = w * h
    if pixels < min_pixels:
        scale = math.sqrt(min_pixels / pixels)
    if max_pixels and pixels * scale * scale > max_pixels:
        scale = math.sqrt(max_pixels / pixels)
    if max_edge and max(w, h) * scale > max_edge:
        scale = max_edge / max(w, h)

    def rounded(up: bool) -> tuple[int, int]:
        step = math.ceil if up else math.floor
        return (
            max(multiple, step(w * scale / multiple) * multiple),
            max(multiple, step(h * scale / multiple) * multiple),
        )

    nw, nh = rounded(up=True)
    if (max_pixels and nw * nh > max_pixels) or (max_edge and max(nw, nh) > max_edge):
        nw, nh = rounded(up=False)
    return nw, nh


def load_refs(store: BlobStore, shas: Sequence[str], limit: int | None) -> list[tuple[bytes, str]]:
    """The reference pictures (bytes, mime), the first ``limit`` of them: a draft being
    finished comes first, then the locked characters."""
    out: list[tuple[bytes, str]] = []
    for sha in list(shas)[:limit]:
        try:
            data = store.path_for(sha).read_bytes()
            out.append((data, image_info(data).mime))
        except (OSError, ValueError) as exc:  # missing blob, bad sha, not a picture
            raise ModelError("ref_unreadable", f"{sha[:12]}: {exc}") from exc
    return out


def data_uri(data: bytes, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def picture(b64: str) -> OutputFile:
    """A returned picture (base64) as a file with its real type and size."""
    try:
        data = base64.b64decode(b64, validate=True)
        info = image_info(data)
    except (binascii.Error, ValueError, NotAnImage) as exc:
        raise ModelError("invalid_response", f"not a picture: {exc}") from exc
    return OutputFile(role="image", mime=info.mime, data=data, w=info.w, h=info.h)


def add_tokens(*parts: dict[str, int] | None) -> dict[str, int] | None:
    total: dict[str, int] = {}
    for part in parts:
        for kind, n in (part or {}).items():
            total[kind] = total.get(kind, 0) + n
    return total or None


async def one_per_request(n: int, make: Callable[[int], Awaitable[ModelResult]]) -> ModelResult:
    """``make(i)`` n times at once, merged. Some may fail: the pictures that came back are
    recorded with their usage (partial success is billed as such); all failing raises the
    first error."""
    results = await asyncio.gather(*(make(i) for i in range(n)), return_exceptions=True)
    done = [r for r in results if isinstance(r, ModelResult)]
    errors = [r for r in results if isinstance(r, BaseException)]
    for err in errors:
        if not isinstance(err, ModelError):
            raise err  # a cancellation or a bug, not a failed picture
    if not done:
        raise errors[0]
    usage = Usage(
        images=sum(r.usage.images or 0 for r in done),
        tokens_in=sum(r.usage.tokens_in or 0 for r in done) or None,
        tokens_out=sum(r.usage.tokens_out or 0 for r in done) or None,
        tokens=add_tokens(*(r.usage.tokens for r in done)),
    )
    raw: dict[str, Any] = {"requests": n}
    if errors:
        raw["failed"] = [e.code for e in errors if isinstance(e, ModelError)]
    return ModelResult(files=[f for r in done for f in r.files], usage=usage, raw=raw)


class ImageApiAdapter:
    """An image model behind an HTTP API: key, client, retries, estimate per picture."""

    def __init__(
        self,
        spec: ModelSpec,
        *,
        get_key: KeyGetter,
        store: BlobStore,
        transport: httpx.AsyncBaseTransport | None = None,
        max_retries: int = 2,
        backoff_s: float = 2.0,
        request_timeout_s: float = 300.0,
    ) -> None:
        self.spec = spec
        self._get_key = get_key
        self._store = store
        self._base_url = normalize_base_url(spec.base_url or "")
        self._transport = transport
        self.max_retries = max_retries
        self.backoff_s = backoff_s
        self.request_timeout_s = request_timeout_s

    @property
    def key(self) -> str:
        return self.spec.key

    async def run(self, req: ModelRequest, ctx: CallContext) -> ModelResult:
        raise NotImplementedError

    async def health(self) -> Health:
        raise NotImplementedError

    def estimate(self, req: ModelRequest) -> Estimate:
        usage = Usage(images=int(req.params.get("n", 1)))
        return Estimate(
            cost_usd=cost_usd(self.spec.pricing, usage),
            seconds=40.0,
            priced=self.spec.pricing.known,
        )

    def _client(self) -> httpx.AsyncClient:
        if not self._base_url:
            raise ModelError("base_url_missing", self.key)
        return httpx.AsyncClient(
            base_url=self._base_url, timeout=self.request_timeout_s, transport=self._transport
        )

    def _api_key(self) -> str:
        name = self.spec.key_name
        api_key = self._get_key(name) if name else None
        if not api_key:
            raise ModelError("missing_key", name or self.key)
        return api_key

    def _model_id(self) -> str:
        if not self.spec.model_id:
            raise ModelError("model_id_missing", f"{self.key}: fill model_id in providers.yaml")
        return self.spec.model_id

    def _refs(self, req: ModelRequest) -> list[tuple[bytes, str]]:
        return load_refs(self._store, req.params.get("refs") or [], self.spec.caps.max_refs)

    def _request_fields(self) -> dict[str, Any]:
        """``caps.request`` in providers.yaml: fields every request carries (GPT Image's
        quality)."""
        return dict((self.spec.caps.model_extra or {}).get("request") or {})
