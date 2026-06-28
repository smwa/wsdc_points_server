-- 008_event_name_as_of.sql
-- Events (and their names) recur and are shared across dancers. Without this,
-- whichever dancer was imported *last* won the name — so re-importing a dancer
-- whose latest appearance is an old occurrence could revert an event's name to
-- a stale one. Track the occurrence date the stored name/location came from and
-- only let a newer (or equal) occurrence overwrite it. Backfill from the newest
-- known occurrence of each event.

BEGIN;

ALTER TABLE events ADD COLUMN name_as_of DATE;

UPDATE events e
SET name_as_of = (
    SELECT MAX(eo.date) FROM event_occurrences eo WHERE eo.event_id = e.id
);

COMMIT;
