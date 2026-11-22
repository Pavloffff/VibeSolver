from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.adapter.config import get_settings
from app.handler.routes import (
    connectors,
    model_providers,
    search,
    solver,
    source_browser,
    sources,
    tickets,
    uploads,
)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="VibeSolver API")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(sources.router, prefix="/api/v1")
    app.include_router(source_browser.router, prefix="/api/v1")
    app.include_router(connectors.router, prefix="/api/v1")
    app.include_router(uploads.router, prefix="/api/v1")
    app.include_router(model_providers.router, prefix="/api/v1")
    app.include_router(search.router, prefix="/api/v1")
    app.include_router(tickets.router, prefix="/api/v1")
    app.include_router(solver.router, prefix="/api/v1")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
