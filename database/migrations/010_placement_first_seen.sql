-- 010_placement_first_seen.sql
-- Track when each placement first appeared in the database. The favorites RSS
-- feed only wants placements that arrived *after* the user starred the dancer
-- (p.first_seen_at >= fd.created_at) — otherwise starring someone dumps their
-- entire competition history into the feed as "new". Event dates can't express
-- this because WSDC results are often imported weeks after the event.
--
-- This only works because the importer upserts placements idempotently
-- (migration 009): unchanged rows are never rewritten, so first_seen_at
-- survives import passes. Existing rows are backfilled with the migration
-- time, which is fine — the feed filter compares per-favorite, so current
-- subscribers see no change.

BEGIN;

ALTER TABLE placements
    ADD COLUMN first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now();

COMMIT;
