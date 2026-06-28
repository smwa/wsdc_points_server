-- 007_user_feed_token.sql
-- A per-user secret token for the favorites RSS feed. The token lives in the
-- feed URL (like an iCalendar subscription link), so the RSS endpoint can find
-- a user's favorites without a cookie. Requires PostgreSQL 13+ for
-- gen_random_uuid(); the volatile default assigns a distinct value to every
-- existing row when the column is added.

BEGIN;

ALTER TABLE users
    ADD COLUMN feed_token UUID NOT NULL DEFAULT gen_random_uuid();

ALTER TABLE users
    ADD CONSTRAINT users_feed_token_key UNIQUE (feed_token);

COMMIT;
