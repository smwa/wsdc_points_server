import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import settings
from .db import create_pool
from .routers import favorites, health, pages
from .session import register_session_middleware
from .templates import templates

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"

# Resources are all same-origin; the only cross-origin call is the JS distance
# sort fetching geojs.io. External links (maps, play store) are navigations and
# don't need allow-listing.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "img-src 'self' data:; "
    "script-src 'self'; "
    "style-src 'self'; "
    "connect-src 'self' https://get.geojs.io; "
    "manifest-src 'self'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Open the database pool on startup, close it on shutdown."""
    app.state.pool = await create_pool()
    try:
        yield
    finally:
        await app.state.pool.close()


async def _render_error(request: Request, status_code: int, message: str):
    return templates.TemplateResponse(
        request,
        "error.html",
        {"status_code": status_code, "message": message},
        status_code=status_code,
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return await _render_error(request, exc.status_code, exc.detail or "Something went wrong.")


async def unhandled_exception_handler(request: Request, exc: Exception):
    log.exception("Unhandled error for %s", request.url.path)
    return await _render_error(request, 500, "Something went wrong on our end.")


def register_security_headers(app: FastAPI) -> None:
    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
        if settings.cookie_secure:  # production HTTPS
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )

        path = request.url.path
        if path.startswith("/static/img/"):
            response.headers.setdefault("Cache-Control", "public, max-age=2592000")  # 30d
        elif path.startswith("/static/"):
            response.headers.setdefault("Cache-Control", "public, max-age=3600")  # 1h
        return response


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    register_session_middleware(app)
    register_security_headers(app)
    # Compress responses (the /dancers page embeds the full ~26k dancer list).
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
    app.include_router(health.router)
    app.include_router(pages.router)
    app.include_router(favorites.router)
    return app


app = create_app()
