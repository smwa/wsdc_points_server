from fastapi import APIRouter, Request

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(request: Request) -> dict:
    """Liveness check that also verifies database connectivity."""
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        await conn.execute("SELECT 1")
    return {"status": "ok"}
