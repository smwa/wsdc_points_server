import asyncpg

from .config import settings


async def create_pool() -> asyncpg.Pool:
    """Create the asyncpg connection pool used for the app's lifetime."""
    return await asyncpg.create_pool(dsn=settings.database_url)
