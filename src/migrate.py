"""Apply database migrations from the SQL files baked into the image.

This lets the image carry and apply its own schema — no source checkout on the
server, no `docker-entrypoint-initdb.d` volume mount. Applied files are recorded
in a `schema_migrations` table, so it's safe to run on every startup; an advisory
lock makes concurrent runners (app + importer) safe too.

    python -m src.migrate        # apply pending migrations and exit

The app and importer also call ``ensure_migrated()`` on startup (unless
`AUTO_MIGRATE=false`).
"""

import asyncio
import logging
import re
from pathlib import Path

import asyncpg

from .config import settings

log = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "database" / "migrations"
# Arbitrary app-wide key so only one process applies migrations at a time.
ADVISORY_LOCK_KEY = 0x57534443  # "WSDC"
# The migration files wrap themselves in BEGIN/COMMIT for psql; we run each file
# inside our own transaction (together with recording it), so strip those.
_BEGIN_COMMIT = re.compile(r"^\s*(BEGIN|COMMIT)\s*;\s*$", re.IGNORECASE | re.MULTILINE)


async def _apply(conn) -> None:
    await conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "  filename text PRIMARY KEY,"
        "  applied_at timestamptz NOT NULL DEFAULT now())"
    )
    applied = {r["filename"] for r in await conn.fetch("SELECT filename FROM schema_migrations")}
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not files:
        log.warning("No migration files found at %s", MIGRATIONS_DIR)
        return

    # A database created the old way (initdb volume mount) already has the schema
    # but no tracking rows. Mark the current files as applied once, rather than
    # re-running them (which would fail — the SQL isn't idempotent).
    if not applied and await conn.fetchval("SELECT to_regclass('public.dancers')"):
        await conn.executemany(
            "INSERT INTO schema_migrations (filename) VALUES ($1) ON CONFLICT DO NOTHING",
            [(f.name,) for f in files],
        )
        log.info("Backfilled %s pre-existing migrations as applied", len(files))
        return

    pending = [f for f in files if f.name not in applied]
    if not pending:
        log.info("Schema up to date (%s migrations applied)", len(applied))
        return

    for f in pending:
        log.info("Applying migration %s", f.name)
        sql = _BEGIN_COMMIT.sub("", f.read_text())
        async with conn.transaction():
            await conn.execute(sql)
            await conn.execute(
                "INSERT INTO schema_migrations (filename) VALUES ($1)", f.name
            )
    log.info("Applied %s migration(s)", len(pending))


async def ensure_migrated() -> None:
    """Apply any pending migrations, holding an advisory lock for safety."""
    conn = await asyncpg.connect(settings.database_url)
    try:
        await conn.execute("SELECT pg_advisory_lock($1)", ADVISORY_LOCK_KEY)
        try:
            await _apply(conn)
        finally:
            await conn.execute("SELECT pg_advisory_unlock($1)", ADVISORY_LOCK_KEY)
    finally:
        await conn.close()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(ensure_migrated())


if __name__ == "__main__":
    main()
