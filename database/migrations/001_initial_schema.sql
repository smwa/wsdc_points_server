-- 001_initial_schema.sql
-- Initial schema for the WSDC Points database (PostgreSQL).
-- Apply against a fresh database; these migrations are not idempotent.

BEGIN;

-- Reference: dance roles (1=Leader, 2=Follower, 3=Switch)
CREATE TABLE roles (
    id   INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);

-- Reference: WSDC competition divisions
CREATE TABLE divisions (
    id                INTEGER PRIMARY KEY,
    abbreviation      TEXT NOT NULL,
    name              TEXT NOT NULL,
    is_skill_division BOOLEAN NOT NULL DEFAULT FALSE  -- the Newcomer -> Champions ladder
);

-- Dancer registry (id is the WSDC dancer id, dancer_wsdcid)
CREATE TABLE dancers (
    id              INTEGER PRIMARY KEY,
    first_name      TEXT NOT NULL,
    last_name       TEXT NOT NULL,
    is_pro          BOOLEAN NOT NULL DEFAULT FALSE,
    primary_role_id INTEGER REFERENCES roles(id)
);

-- Past sanctioned events; recurring events have a single row here
CREATE TABLE events (
    id       INTEGER PRIMARY KEY,  -- WSDC event id
    name     TEXT NOT NULL,
    location TEXT,
    url      TEXT
);

-- Each time an event was held (events recur, typically annually)
CREATE TABLE event_occurrences (
    id       INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id INTEGER NOT NULL REFERENCES events(id),
    date     DATE NOT NULL,  -- normalized to the first of the month (YYYY-MM-01)
    UNIQUE (event_id, date)
);

-- Competition tier per division/role for each event occurrence.
-- Derived from first-place points: 3->Tier1, 6->T2, 10->T3, 15->T4, 20->T5, 25->T6.
CREATE TABLE event_occurrence_tiers (
    id                  INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_occurrence_id INTEGER NOT NULL REFERENCES event_occurrences(id),
    division_id         INTEGER NOT NULL REFERENCES divisions(id),
    role_id             INTEGER NOT NULL REFERENCES roles(id),
    tier                TEXT NOT NULL,
    UNIQUE (event_occurrence_id, division_id, role_id)
);

-- Individual competition placements (the core fact table)
CREATE TABLE placements (
    id                  INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    dancer_id           INTEGER NOT NULL REFERENCES dancers(id),
    event_occurrence_id INTEGER NOT NULL REFERENCES event_occurrences(id),
    role_id             INTEGER NOT NULL REFERENCES roles(id),
    division_id         INTEGER NOT NULL REFERENCES divisions(id),
    result              TEXT NOT NULL,  -- "1".."5" or "F" (finalist)
    points              INTEGER NOT NULL
);

-- Upcoming events scraped from worldsdc.com/events/ (refreshed on a schedule)
CREATE TABLE upcoming_events (
    id         INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name       TEXT NOT NULL,
    location   TEXT,
    latitude   DOUBLE PRECISION,
    longitude  DOUBLE PRECISION,
    url        TEXT,
    event_type TEXT,
    start_date TIMESTAMP,
    end_date   TIMESTAMP
);

-- Indexes for the main read paths.
-- Competitors at an event occurrence; roles/divisions are tiny reference
-- tables, so no denormalized competitors table is needed.
CREATE INDEX idx_placements_occurrence      ON placements(event_occurrence_id);
-- All placements for a dancer (dancer profile page).
CREATE INDEX idx_placements_dancer          ON placements(dancer_id);
-- Aggregate points by dancer + division + role (covers the points table).
CREATE INDEX idx_placements_dancer_div_role ON placements(dancer_id, division_id, role_id);

COMMIT;
