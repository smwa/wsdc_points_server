-- 003_users_and_favorites.sql
-- Anonymous users (identified by a cookie) and their starred dancers.
-- Requires PostgreSQL 13+ for the built-in gen_random_uuid().

BEGIN;

-- One row per anonymous visitor. The id is stored in the visitor's `uid`
-- cookie; there is no login. last_seen is refreshed on every page view so
-- stale visitors can be pruned (see database/cleanup_stale_users.sql).
CREATE TABLE users (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Dancers a user has starred. Cascades so pruning a user removes their stars.
CREATE TABLE favorite_dancers (
    user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    dancer_id  INTEGER NOT NULL REFERENCES dancers(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, dancer_id)
);

-- Supports pruning users who haven't visited in a while.
CREATE INDEX idx_users_last_seen ON users(last_seen);

COMMIT;
