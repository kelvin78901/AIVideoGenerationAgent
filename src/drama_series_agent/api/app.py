"""FastAPI application factory for AI Drama Studio.

Mounts the upstream drama-series-agent routes under ``/api`` unchanged and the studio
routes under ``/api/v1``.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from drama_series_agent import __version__
from drama_series_agent.api import sse
from drama_series_agent.api.routes import (
    bible,
    comfy,
    config,
    dev,
    jobs,
    novel,
    products,
    providers,
    series,
    setup,
    spec,
)
from drama_series_agent.api.security import CLIENT_HEADER, LocalOnlyGuard
from drama_series_agent.api.state import StudioState, get_state
from drama_series_agent.core.secrets import install_log_redaction
from drama_series_agent.pipeline.errors import PipelineError

# The Vite dev server is the only browser origin allowed to call the backend.
ALLOWED_ORIGINS = ["http://127.0.0.1:5173", "http://localhost:5173"]
_LOOPBACK = {"127.0.0.1", "localhost"}


def allowed_origins() -> list[str]:
    """``ALLOWED_ORIGINS`` plus ``DRAMA_WEB_ORIGINS`` (comma-separated, loopback http only).

    The extra origins are for a second front end on another port, e.g. the Playwright
    tests' own Vite server; anything that is not ``http://127.0.0.1:<port>`` or
    ``http://localhost:<port>`` is refused so the setting cannot open the API to other sites.
    """
    extra = [o.strip().rstrip("/") for o in os.environ.get("DRAMA_WEB_ORIGINS", "").split(",")]
    origins = list(ALLOWED_ORIGINS)
    for origin in filter(None, extra):
        parts = urlsplit(origin)
        if parts.scheme != "http" or parts.hostname not in _LOOPBACK or parts.path:
            raise ValueError(f"DRAMA_WEB_ORIGINS: {origin!r} is not a loopback http origin")
        if origin not in origins:
            origins.append(origin)
    return origins


def _v1_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    @router.get("/health")
    async def health(state: Annotated[StudioState, Depends(get_state)]) -> dict[str, Any]:
        # `mock` drives the front end's "Mock 模式" badge.
        return {"status": "ok", "version": __version__, "mock": state.registry.mock}

    router.include_router(sse.router)
    router.include_router(jobs.router)
    router.include_router(dev.router)
    router.include_router(providers.router)
    router.include_router(series.router)
    router.include_router(novel.router)
    router.include_router(bible.router)
    router.include_router(spec.router)
    router.include_router(setup.router)
    router.include_router(comfy.router)
    router.include_router(products.router)
    router.include_router(config.router)
    return router


async def _pipeline_error(request: Request, exc: Exception) -> JSONResponse:
    """Pipeline services raise ``PipelineError``; it reads like ``ApiError`` on the wire."""
    assert isinstance(exc, PipelineError)
    return JSONResponse(
        status_code=exc.status, content={"detail": {"code": exc.code, "params": exc.params}}
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    install_log_redaction()
    state = await StudioState.start()
    app.state.studio = state
    await state.run()
    try:
        yield
    finally:
        await state.stop()


def create_app() -> FastAPI:
    from drama_series_agent.api.routers.series import router as upstream_router

    app = FastAPI(title="AI Drama Studio", version=__version__, lifespan=lifespan)
    origins = allowed_origins()
    # Added first = runs inside CORS, so preflight requests are answered by CORS untouched.
    app.add_middleware(LocalOnlyGuard, allowed_origins=origins)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["content-type", CLIENT_HEADER, "last-event-id"],
    )
    app.add_exception_handler(PipelineError, _pipeline_error)
    app.include_router(upstream_router, prefix="/api")
    app.include_router(_v1_router())
    return app
