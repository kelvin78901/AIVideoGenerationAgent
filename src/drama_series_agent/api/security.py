"""Local-only request guard: stops other web pages from driving the backend.

The backend listens on 127.0.0.1, but a page open in the user's browser can still try to
reach it. Two checks close that:

* **Host header** must be ``127.0.0.1`` / ``localhost`` / ``[::1]`` (any port). A DNS
  rebinding attack resolves ``evil.example`` to 127.0.0.1, but the browser still sends
  ``Host: evil.example``.
* **Every non-GET request** must carry ``X-Drama-Studio: 1``. A cross-site page cannot add
  a custom header without a CORS preflight, and CORS only allows our own front end. If an
  ``Origin`` header is present it must also be one of the allowed origins. Non-browser
  clients (scripts, the ComfyUI node pack) send no Origin and just add the header.
"""

from __future__ import annotations

import json
from collections.abc import Iterable

from starlette.types import ASGIApp, Receive, Scope, Send

CLIENT_HEADER = "x-drama-studio"
CLIENT_HEADER_VALUE = "1"
ALLOWED_HOSTS = frozenset({"127.0.0.1", "localhost", "[::1]"})
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def _hostname(host_header: str) -> str:
    host = host_header.strip().lower()
    if host.startswith("["):  # IPv6 literal, e.g. [::1]:8000
        end = host.find("]")
        return host[: end + 1] if end != -1 else host
    return host.rsplit(":", 1)[0] if ":" in host else host


class LocalOnlyGuard:
    def __init__(
        self,
        app: ASGIApp,
        *,
        allowed_origins: Iterable[str],
        allowed_hosts: Iterable[str] = ALLOWED_HOSTS,
    ) -> None:
        self.app = app
        self.allowed_origins = frozenset(o.rstrip("/") for o in allowed_origins)
        self.allowed_hosts = frozenset(allowed_hosts)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        method = scope.get("method", "GET")

        if _hostname(headers.get("host", "")) not in self.allowed_hosts:
            await self._reject(send, 421, "host_not_allowed")
            return
        if scope["type"] == "http" and method not in SAFE_METHODS:
            origin = headers.get("origin")
            if origin is not None and origin.rstrip("/") not in self.allowed_origins:
                await self._reject(send, 403, "origin_not_allowed")
                return
            if headers.get(CLIENT_HEADER) != CLIENT_HEADER_VALUE:
                await self._reject(send, 403, "missing_client_header")
                return
        await self.app(scope, receive, send)

    @staticmethod
    async def _reject(send: Send, status: int, code: str) -> None:
        body = json.dumps({"detail": {"code": code, "params": {}}}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
