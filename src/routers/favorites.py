import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from ..session import current_user_id

router = APIRouter(prefix="/favorites", tags=["favorites"])


def _back(request: Request) -> str:
    """Redirect target after a form submit: the page we came from, or home."""
    return request.headers.get("referer") or "/"


@router.post("/{dancer_id}")
async def add_favorite(
    dancer_id: int,
    request: Request,
    user_id: uuid.UUID = Depends(current_user_id),
):
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO favorite_dancers (user_id, dancer_id) VALUES ($1, $2) "
            "ON CONFLICT DO NOTHING",
            user_id,
            dancer_id,
        )
    return RedirectResponse(_back(request), status_code=303)


@router.post("/{dancer_id}/delete")
async def remove_favorite(
    dancer_id: int,
    request: Request,
    user_id: uuid.UUID = Depends(current_user_id),
):
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM favorite_dancers WHERE user_id = $1 AND dancer_id = $2",
            user_id,
            dancer_id,
        )
    return RedirectResponse(_back(request), status_code=303)
