import uuid
from datetime import timedelta

from fastapi import FastAPI, Request

from .config import settings

COOKIE_NAME = "uid"
COOKIE_MAX_AGE = int(timedelta(days=365).total_seconds())

# The Android app is a Trusted Web Activity: its first navigation arrives with a
# Referer of `android-app://<package>`. We latch that into a cookie so every
# later (same-origin) page also knows it's running inside the app. A normal
# browser never sees that referer, and the TWA has its own cookie jar.
APP_COOKIE_NAME = "app"
ANDROID_APP_REFERER_PREFIX = "android-app://"


def current_user_id(request: Request) -> uuid.UUID:
    """Dependency: the anonymous user id set by the session middleware."""
    return request.state.user_id


def register_session_middleware(app: FastAPI) -> None:
    """Issue/refresh an anonymous `uid` cookie and keep users.last_seen current.

    Skips static assets and the health check so they don't touch the database.
    """

    @app.middleware("http")
    async def user_session(request: Request, call_next):
        path = request.url.path
        if path.startswith("/static") or path == "/health":
            return await call_next(request)

        pool = request.app.state.pool
        raw = request.cookies.get(COOKIE_NAME)
        user_id = None
        async with pool.acquire() as conn:
            if raw:
                try:
                    parsed = uuid.UUID(raw)
                except ValueError:
                    parsed = None
                if parsed is not None:
                    user_id = await conn.fetchval(
                        "UPDATE users SET last_seen = now() WHERE id = $1 RETURNING id",
                        parsed,
                    )
            if user_id is None:
                user_id = await conn.fetchval(
                    "INSERT INTO users DEFAULT VALUES RETURNING id"
                )

        request.state.user_id = user_id

        # Detect (and remember) that we're running inside the Android TWA.
        is_app = request.cookies.get(APP_COOKIE_NAME) == "1" or request.headers.get(
            "referer", ""
        ).startswith(ANDROID_APP_REFERER_PREFIX)
        request.state.is_app = is_app

        response = await call_next(request)
        response.set_cookie(
            COOKIE_NAME,
            str(user_id),
            max_age=COOKIE_MAX_AGE,
            httponly=True,
            samesite="lax",
            secure=settings.cookie_secure,
        )
        if is_app and request.cookies.get(APP_COOKIE_NAME) != "1":
            response.set_cookie(
                APP_COOKIE_NAME,
                "1",
                max_age=COOKIE_MAX_AGE,
                httponly=True,
                samesite="lax",
                secure=settings.cookie_secure,
            )
        return response
