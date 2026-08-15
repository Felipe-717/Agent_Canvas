from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agentcanvas import __version__
from agentcanvas.bootstrap.container import Container, build_container
from agentcanvas.infrastructure.web.errors import register_error_handlers
from agentcanvas.infrastructure.web.routers import chat, dashboards, datasets

# El frontend de desarrollo (Vite) vive en otro puerto.
DEV_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")


def create_app(container: Container | None = None) -> FastAPI:
    """`container` se inyecta en los tests; en produccion se construye solo."""
    resolved = container or build_container()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        await resolved.engine.dispose()

    app = FastAPI(
        title="AgentCanvas AI",
        version=__version__,
        summary="Automatizacion de datos y BI generativo mediante agentes",
        lifespan=lifespan,
    )
    app.state.container = resolved
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(DEV_ORIGINS),
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)
    app.include_router(dashboards.router)
    app.include_router(chat.router)
    app.include_router(datasets.router)

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, object]:
        return {
            "status": "ok",
            "version": __version__,
            "model": resolved.settings.llm_model,
            # Sin esto, el primer sintoma de una clave ausente es un 503 raro
            # en mitad de una peticion del usuario.
            "llm_configured": bool(resolved.settings.llm_api_key.get_secret_value()),
        }

    return app
