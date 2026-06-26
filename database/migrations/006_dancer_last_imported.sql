-- 006_dancer_last_imported.sql
-- Track when each dancer was last fetched from WSDC, so the importer can
-- prioritise recent competitors and refresh everyone else less often.

BEGIN;

ALTER TABLE dancers ADD COLUMN last_imported_at TIMESTAMPTZ;

-- Speeds up "least recently imported first" ordering for the unlikely cohort.
CREATE INDEX idx_dancers_last_imported ON dancers(last_imported_at);

COMMIT;
