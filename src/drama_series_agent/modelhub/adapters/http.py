"""What the HTTP adapters share: error codes by status, and one request with retries.

Retried: timeouts, network errors and ``RETRY_STATUSES`` (rate limits, 5xx), with exponential
backoff or the provider's ``Retry-After``. Anything else fails at once with a stable code.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import httpx

from drama_series_agent.modelhub.adapters.base import ModelError

RETRY_STATUSES = frozenset({408, 409, 425, 429, 500, 502, 503, 504})
KeyGetter = Callable[[str], str | None]
ErrorMapper = Callable[[int, str], ModelError]


def error_for(status: int, body: str) -> ModelError:
    snippet = body[:300]
    if status in (401, 403):
        return ModelError("auth_failed", snippet, status=status)
    if status == 404:
        return ModelError("model_not_found", snippet, status=status)
    if status == 429:
        return ModelError("rate_limited", snippet, status=status, retryable=True)
    if status >= 500:
        return ModelError("provider_error", snippet, status=status, retryable=True)
    return ModelError("bad_request", snippet, status=status)


def retry_delay(attempt: int, resp: httpx.Response | None, backoff_s: float) -> float:
    if resp is not None:
        retry_after = resp.headers.get("retry-after")
        if retry_after and retry_after.replace(".", "", 1).isdigit():
            return min(float(retry_after), 60.0)
    return float(backoff_s * 2 ** (attempt - 1))


async def send(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    max_retries: int,
    backoff_s: float,
    errors: ErrorMapper = error_for,
    **kwargs: Any,
) -> httpx.Response:
    """A 2xx response, or the ``ModelError`` of the last attempt."""
    attempt = 0
    while True:
        resp: httpx.Response | None = None
        try:
            resp = await client.request(method, url, **kwargs)
        except httpx.TimeoutException:
            error = ModelError("timeout", "provider request timed out", retryable=True)
        except httpx.HTTPError as exc:
            error = ModelError("network_error", type(exc).__name__, retryable=True)
        else:
            if resp.is_success:
                return resp
            error = errors(resp.status_code, resp.text)
            if resp.status_code not in RETRY_STATUSES:
                raise error
        attempt += 1
        if attempt > max_retries:
            raise error
        await asyncio.sleep(retry_delay(attempt, resp, backoff_s))
