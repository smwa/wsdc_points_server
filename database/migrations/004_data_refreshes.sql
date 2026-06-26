-- 004_data_refreshes.sql
-- Append-only log of successful data imports from the WSDC source.
-- The site's "last updated" timestamp is the most recent completed_at.

BEGIN;

CREATE TABLE data_refreshes (
    id           INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    completed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMIT;
