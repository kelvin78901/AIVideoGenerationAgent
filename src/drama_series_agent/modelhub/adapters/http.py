"""What the HTTP adapters share: error codes by status, and one request with retries.

Retried: timeouts, network errors and ``RETRY_STATUSES`` (rate limits, 5xx), with exponential
backoff or the provider's ``Retry-After``, unless the error mapper calls it final (a 429 that
is out of quota, or a 402, ``quota_exceeded``). Anything else fails at once with a stable code.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import httpx

from drama_series_agent.modelhub.adapters.base import ModelError

RETRY_STATUSES = frozenset({408, 409, 425, 429, 500, 502, 503, 504, 529})
# A 429 that is out of quota rather than too fast, so retrying will not help: Gemini's free
# tier has no quota for some models at all ("limit: 0", billing not enabled), OpenAI's
# ``insufficient_quota`` (no credit).
QUOTA_MARKERS = ("limit: 0", "insufficient_quota")
KeyGetter = Callable[[str], str | None]
ErrorMapper = Callable[[int, str], ModelError]


def error_for(status: int, body: str) -> ModelError:
    snippet = body[:300]
    if status in (401, 403):
        return ModelError("auth_failed", snippet, status=status)
    if status == 404:
        return ModelError("model_not_found", snippet, status=status)
    if status == 402:  # Payment Required: Gemini's prepaid credits used up (M4 live smoke)
        return ModelError("quota_exceeded", snippet, status=status)
    if status == 429:
        if any(marker in body for marker in QUOTA_MARKERS):
            return ModelError("quota_exceeded", snippet, status=status)
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
            # The mapper has the last word: a 429 that is out of quota is not retried.
            if resp.status_code not in RETRY_STATUSES or not error.retryable:
                raise error
        attempt += 1
        if attempt > max_retries:
            raise error
        await asyncio.sleep(retry_delay(attempt, resp, backoff_s))
