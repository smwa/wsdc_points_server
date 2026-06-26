-- 002_seed_reference_data.sql
-- Fixed reference data: dance roles and WSDC divisions.

BEGIN;

INSERT INTO roles (id, name) VALUES
    (1, 'Leader'),
    (2, 'Follower'),
    (3, 'Switch');

-- Division ids match the division objects returned by the WSDC points API.
-- (Note: the legacy points/fetch.py DIVISIONS_MAP uses different ids for the
-- non-skill divisions 9-13; the API ids below are treated as source of truth.)
-- is_skill_division marks the Newcomer -> Champions progression ladder.
INSERT INTO divisions (id, abbreviation, name, is_skill_division) VALUES
    (1,  'JRS',  'Juniors',       FALSE),
    (2,  'MSTR', 'Masters',       FALSE),
    (3,  'NEW',  'Newcomer',      TRUE),
    (4,  'NOV',  'Novice',        TRUE),
    (5,  'INT',  'Intermediate',  TRUE),
    (6,  'ADV',  'Advanced',      TRUE),
    (7,  'ALS',  'All-Stars',     TRUE),
    (8,  'CHMP', 'Champions',     TRUE),
    (9,  'INV',  'Invitational',  FALSE),
    (10, 'PRO',  'Professional',  FALSE),
    (12, 'SPH',  'Sophisticated', FALSE),
    (13, 'TCH',  'Teacher',       FALSE);

COMMIT;
