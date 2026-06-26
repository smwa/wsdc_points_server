from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from .config import settings
from .db import create_pool
from .routers import favorites, health, pages
from .session import register_session_middleware

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Open the database pool on startup, close it on shutdown."""
    app.state.pool = await create_pool()
    try:
        yield
    finally:
        await app.state.pool.close()


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    register_session_middleware(app)
    # Compress responses (the /dancers page embeds the full ~26k dancer list).
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.include_router(health.router)
    app.include_router(pages.router)
    app.include_router(favorites.router)
    return app


app = create_app()
