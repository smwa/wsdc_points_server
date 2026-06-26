"""Database writes for the importer: one transaction per dancer."""

import asyncio
import logging

from . import source
from .transform import DancerData

log = logging.getLogger(__name__)


async def max_dancer_id(conn) -> int:
    """Highest dancer id currently stored (0 if the table is empty)."""
    return await conn.fetchval("SELECT COALESCE(MAX(id), 0) FROM dancers")


async def candidate_ids(conn, recent_years: int, unlikely_days: int) -> list[int]:
    """Dancer ids to (re-)fetch this pass, likely cohort first.

    Likely = placed within ``recent_years`` (fetched every pass). Unlikely =
    everyone else, included only when their last import is older than
    ``unlikely_days`` (or never imported), so they rotate through over time.
    Ids not in the database are not probed here — only the new-id scan above the
    max id discovers new dancers.
    """
    rows = await conn.fetch(
        f"""
        WITH d AS (
            SELECT dancers.id, dancers.last_imported_at,
                   EXISTS (
                       SELECT 1 FROM placements p
                       JOIN event_occurrences eo ON eo.id = p.event_occurrence_id
                       WHERE p.dancer_id = dancers.id
                         AND eo.date >= CURRENT_DATE - INTERVAL '{int(recent_years)} years'
                   ) AS recent
            FROM dancers
        )
        SELECT id FROM d
        WHERE recent
           OR last_imported_at IS NULL
           OR last_imported_at < now() - INTERVAL '{int(unlikely_days)} days'
        ORDER BY recent DESC, last_imported_at ASC NULLS FIRST
        """
    )
    return [r["id"] for r in rows]


async def load_reference_maps(conn):
    """Build resolver callables for divisions and roles from the seeded data."""
    division_rows = await conn.fetch("SELECT id, name, abbreviation FROM divisions")
    role_rows = await conn.fetch("SELECT id, name FROM roles")

    by_name = {r["name"].lower(): r["id"] for r in division_rows}
    by_abbrev = {r["abbreviation"].lower(): r["id"] for r in division_rows}
    roles = {r["name"].lower(): r["id"] for r in role_rows}

    def resolve_division(div_obj):
        name = (div_obj.get("name") or "").lower()
        if name in by_name:
            return by_name[name]
        return by_abbrev.get((div_obj.get("abbreviation") or "").lower())

    def resolve_role(name):
        return roles.get((name or "").lower())

    return resolve_division, resolve_role


async def import_dancer(conn, data: DancerData) -> None:
    """Upsert one dancer and replace just their facts, in a single transaction.

    Dancers/events/occurrences are upserted (shared across dancers; recurring).
    Only this dancer's placements are deleted and reinserted. Tiers are owned by
    whoever placed first, so we upsert the tiers for this dancer's wins.
    """
    async with conn.transaction():
        first, last, is_pro, primary_role_id = data.dancer
        await conn.execute(
            """
            INSERT INTO dancers
                (id, first_name, last_name, is_pro, primary_role_id, last_imported_at)
            VALUES ($1, $2, $3, $4, $5, now())
            ON CONFLICT (id) DO UPDATE SET
                first_name = EXCLUDED.first_name,
                last_name = EXCLUDED.last_name,
                is_pro = EXCLUDED.is_pro,
                primary_role_id = EXCLUDED.primary_role_id,
                last_imported_at = now()
            """,
            data.dancer_id, first, last, is_pro, primary_role_id,
        )

        await conn.executemany(
            """
            INSERT INTO events (id, name, location, url)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                location = EXCLUDED.location,
                url = EXCLUDED.url
            """,
            [(eid, e["name"], e["location"], e["url"]) for eid, e in data.events.items()],
        )

        # Upsert occurrences and capture their ids (the no-op DO UPDATE makes
        # conflicting rows appear in RETURNING so we get ids for existing ones).
        occurrences = sorted(data.occurrences)
        occ_id_rows = await conn.fetch(
            """
            INSERT INTO event_occurrences (event_id, date)
            SELECT * FROM unnest($1::int[], $2::date[])
            ON CONFLICT (event_id, date) DO UPDATE SET event_id = EXCLUDED.event_id
            RETURNING id, event_id, date
            """,
            [o[0] for o in occurrences],
            [o[1] for o in occurrences],
        )
        occ_map = {(r["event_id"], r["date"]): r["id"] for r in occ_id_rows}

        # Replace only this dancer's placements.
        await conn.execute("DELETE FROM placements WHERE dancer_id = $1", data.dancer_id)
        await conn.executemany(
            """
            INSERT INTO placements
                (dancer_id, event_occurrence_id, role_id, division_id, result, points)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            [
                (data.dancer_id, occ_map[(event_id, date)], role_id, division_id, result, points)
                for (event_id, date, role_id, division_id, result, points) in data.placements
            ],
        )

        await conn.executemany(
            """
            INSERT INTO event_occurrence_tiers
                (event_occurrence_id, division_id, role_id, tier)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (event_occurrence_id, division_id, role_id) DO UPDATE SET
                tier = EXCLUDED.tier
            """,
            [
                (occ_map[(event_id, date)], division_id, role_id, tier)
                for (event_id, date, division_id, role_id, tier) in data.tiers
            ],
        )


async def _resolve_latlon(conn, location: str, api_key: str):
    """Look up (or geocode + cache) a location's coordinates via geocode_cache.

    A cached row with NULL lat/lon is a known miss and is returned as-is. Cache
    writes are autocommitted here (independent of the upcoming_events replace).
    """
    if not location:
        return (None, None)
    row = await conn.fetchrow(
        "SELECT latitude, longitude FROM geocode_cache WHERE location = $1", location
    )
    if row is not None:
        return (row["latitude"], row["longitude"])

    coords = await asyncio.to_thread(source.geocode_location, location, api_key)
    latitude, longitude = coords if coords else (None, None)
    await conn.execute(
        """
        INSERT INTO geocode_cache (location, latitude, longitude)
        VALUES ($1, $2, $3)
        ON CONFLICT (location) DO UPDATE SET
            latitude = EXCLUDED.latitude,
            longitude = EXCLUDED.longitude,
            updated_at = now()
        """,
        location, latitude, longitude,
    )
    return (latitude, longitude)


async def refresh_upcoming_events(conn, events: list[dict], api_key: str) -> None:
    """Replace upcoming_events. Geocodes via geocode_cache when a key is set;
    without a key, geocoding is skipped (an error is logged) and the events are
    still stored with no coordinates."""
    geocode = bool(api_key)
    if not geocode:
        log.error(
            "OPEN_WEATHER_MAP_API_KEY not set; skipping geocoding — "
            "upcoming events will be stored without coordinates"
        )

    rows = []
    for e in events:
        if geocode:
            latitude, longitude = await _resolve_latlon(conn, e["location"], api_key)
        else:
            latitude, longitude = (None, None)
        rows.append(
            (
                e["name"], e["location"], latitude, longitude,
                e["url"], e["event_type"], e["start_date"], e["end_date"],
            )
        )

    async with conn.transaction():
        await conn.execute("DELETE FROM upcoming_events")
        await conn.executemany(
            """
            INSERT INTO upcoming_events
                (name, location, latitude, longitude, url, event_type, start_date, end_date)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            rows,
        )
    log.info("Refreshed %s upcoming events", len(rows))


async def mark_refresh_complete(conn) -> None:
    """Record a completed pass so the home page's 'last updated' advances."""
    await conn.execute("INSERT INTO data_refreshes DEFAULT VALUES")
