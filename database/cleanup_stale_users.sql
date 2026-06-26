-- Delete anonymous users (and, via ON DELETE CASCADE, their starred dancers)
-- that have not visited the site in over a year. Run on a schedule, e.g.:
--   psql "$DATABASE_URL" -f database/cleanup_stale_users.sql
DELETE FROM users WHERE last_seen < now() - INTERVAL '1 year';
