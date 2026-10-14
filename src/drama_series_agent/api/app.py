"""FastAPI application factory for AI Drama Studio.

Mounts the upstream drama-series-agent routes under ``/api`` unchanged and the studio
routes under ``/api/v1``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from drama_series_agent import __version__
from drama_series_agent.api import sse
from drama_series_agent.api.state import StudioState

# The Vite dev server is the only browser origin allowed to call the backend.
ALLOWED_ORIGINS = ["http://127.0.0.1:5173", "http://localhost:5173"]


def _v1_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    @router.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    router.include_router(sse.router)
    return router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    state = await StudioState.start()
    app.state.studio = state
    try:
        yield
    finally:
        await state.stop()


def create_app() -> FastAPI:
    from drama_series_agent.api.routers.series import router as upstream_router

    app = FastAPI(title="AI Drama Studio", version=__version__, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(upstream_router, prefix="/api")
    app.include_router(_v1_router())
    return app
