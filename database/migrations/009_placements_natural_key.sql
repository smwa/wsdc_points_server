-- 009_placements_natural_key.sql
-- A placement is uniquely identified by who placed, where, and in what
-- division/role: (dancer_id, event_occurrence_id, division_id, role_id). The
-- importer used to DELETE all of a dancer's placements and reinsert them on
-- every pass, which churned the table (dead tuples + WAL for rows that did not
-- change) and reassigned placements.id each run. A unique constraint on the
-- natural key lets the importer upsert idempotently instead: unchanged rows are
-- left untouched and keep their id, so only genuinely changed rows write.
-- (Note: INSERT ... ON CONFLICT still consumes one IDENTITY value per incoming
-- row even on conflict, so the id sequence keeps advancing at roughly the same
-- rate as before; that is a separate, pre-existing concern -- bump id to BIGINT
-- if INTEGER exhaustion ever looms.)

BEGIN;

-- Defensive: collapse any accidental duplicates (none expected given the old
-- replace-wholesale logic) before the constraint, keeping the lowest id.
DELETE FROM placements p
USING placements dup
WHERE p.dancer_id = dup.dancer_id
  AND p.event_occurrence_id = dup.event_occurrence_id
  AND p.division_id = dup.division_id
  AND p.role_id = dup.role_id
  AND p.id > dup.id;

ALTER TABLE placements
    ADD CONSTRAINT placements_natural_key
    UNIQUE (dancer_id, event_occurrence_id, division_id, role_id);

COMMIT;
