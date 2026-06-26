"""Entry point for the data importer.

It holds no dancer cache. It scans WSDC ids upward, fetching each dancer from
the API and upserting it in its own transaction, until enough consecutive ids
are missing to mark the end of the registry. That is one *pass*. By default it
loops passes forever, so every dancer is refreshed over and over; tune
``IMPORTER_REQUEST_DELAY_SECONDS`` to run a slow, WSDC-friendly loop.

    python -m src.importer            # forever loop (default)
    python -m src.importer --once     # one full pass, then exit

Set ``IMPORTER_OFFLINE=1`` to read the legacy raw cache files instead of hitting
WSDC (for local testing). Combine with ``--once``:

    IMPORTER_OFFLINE=1 python -m src.importer --once
"""

import asyncio
import logging
import sys

import asyncpg

from ..config import settings
from . import run, source
from .transform import transform_dancer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("importer")


async def _maybe_delay() -> None:
    if settings.importer_request_delay_seconds:
        await asyncio.sleep(settings.importer_request_delay_seconds)


async def _iter_dancers(pool):
    """Yield raw dancer responses for one pass.

    Offline: every dancer in the cache file, ordered by id. Live: re-fetch the
    prioritised set of ids already in the database (likely cohort first), then
    scan upward from the max id for brand-new dancers until
    ``importer_none_slide_limit`` consecutive ids are missing.
    """
    if settings.importer_offline:
        dancers = await asyncio.to_thread(
            source.load_raw_dancers, settings.raw_responses_path
        )
        for wsdc_id in sorted(dancers, key=int):
            yield dancers[wsdc_id]
        return

    async with pool.acquire() as conn:
        max_id = await run.max_dancer_id(conn)
        ids = await run.candidate_ids(
            conn,
            settings.importer_recent_years,
            settings.importer_unlikely_refresh_days,
        )
    log.info("Refreshing %s existing dancers, then scanning above id %s", len(ids), max_id)

    for wsdc_id in ids:
        datum = await asyncio.to_thread(source.fetch_dancer, wsdc_id)
        if datum is not None:
            yield datum
        await _maybe_delay()

    wsdc_id = max_id + 1
    none_slide = 0
    while none_slide < settings.importer_none_slide_limit:
        datum = await asyncio.to_thread(source.fetch_dancer, wsdc_id)
        if datum is None:
            none_slide += 1
        else:
            none_slide = 0
            yield datum
        wsdc_id += 1
        await _maybe_delay()


async def run_pass(pool, resolve_division, resolve_role) -> None:
    """One full pass: refresh events, then every dancer."""
    if settings.importer_offline:
        events = await asyncio.to_thread(source.load_events_page, settings.raw_events_path)
    else:
        events = await asyncio.to_thread(source.fetch_events_page)
    if events:
        async with pool.acquire() as conn:
            await run.refresh_upcoming_events(
                conn, events, settings.open_weather_map_api_key
            )

    imported = 0
    async for datum in _iter_dancers(pool):
        data = transform_dancer(datum, resolve_division, resolve_role)
        if data is not None:
            async with pool.acquire() as conn:
                await run.import_dancer(conn, data)
            imported += 1

    async with pool.acquire() as conn:
        await run.mark_refresh_complete(conn)
    log.info("Pass complete: imported/updated %s dancers", imported)


async def main(once: bool) -> None:
    # Offline mode reads a static file, so one pass is all there is to do.
    once = once or settings.importer_offline
    pool = await asyncpg.create_pool(settings.database_url, min_size=1, max_size=3)
    try:
        async with pool.acquire() as conn:
            resolve_division, resolve_role = await run.load_reference_maps(conn)
        while True:
            try:
                await run_pass(pool, resolve_division, resolve_role)
            except Exception:
                log.exception("Pass failed; continuing")
            if once:
                break
            if settings.importer_pass_delay_seconds:
                await asyncio.sleep(settings.importer_pass_delay_seconds)
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main("--once" in sys.argv))
