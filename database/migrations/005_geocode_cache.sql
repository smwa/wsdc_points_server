-- 005_geocode_cache.sql
-- Cache of geocoded event locations (replaces the legacy points/locations.json).
-- One row per location string; NULL lat/lon records a known miss so we don't
-- re-query OpenWeatherMap for it.

BEGIN;

CREATE TABLE geocode_cache (
    location   TEXT PRIMARY KEY,
    latitude   DOUBLE PRECISION,
    longitude  DOUBLE PRECISION,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMIT;
