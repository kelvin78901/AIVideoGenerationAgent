"""FastAPI application factory for AI Drama Studio.

Mounts the upstream drama-series-agent routes under ``/api`` unchanged and the studio
routes under ``/api/v1``.
"""

from __future__ import annotations

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from drama_series_agent import __version__

# The Vite dev server is the only browser origin allowed to call the backend.
ALLOWED_ORIGINS = ["http://127.0.0.1:5173", "http://localhost:5173"]


def _v1_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    @router.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    return router


def create_app() -> FastAPI:
    from drama_series_agent.api.routers.series import router as upstream_router

    app = FastAPI(title="AI Drama Studio", version=__version__)
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
