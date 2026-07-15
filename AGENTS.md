# WSDC Points — Server (`server/`)

A new server-rendered backend that is being built to replace the Jekyll static
site + flat-file approach described in the repository-root `AGENTS.md`. It serves
**HTML rendered on the server** (no SPA, no client-side AJAX) from a PostgreSQL
database.

This directory is self-contained and is excluded from the Jekyll build (see
`_config.yml`). The legacy site under `pages/`, `assets/`, and `points/` still
runs independently.

> **Keep this file current.** Update the relevant section here in the same pass
> as any behavioural, status, layout, or convention change.

## Status

Built (verified with `python -m py_compile` plus offline transform tests against
the legacy cached data — DB/network calls are **not** exercised in the dev
sandbox, so expect to debug runtime/SQL issues on the first real run):

- Migrations 001–004 + reference-data seed (roles, divisions).
- App scaffold: `config`, asyncpg pool, lifespan, Jinja2, `/static` mount.
- Anonymous-user session middleware + `uid` cookie.
- Favorites add/remove endpoints.
- `/health` and the server-rendered pages: home `/`, `/about`, `/dancers`,
  `/dancer/{id}` (star toggle, "can compete" eligibility, points, placements,
  points-over-time chart), `/events`, `/event/{id}` (per-occurrence tiers,
  "pointed"-count links (dancers who placed high enough to earn points, not
  total entrants), pointed-over-time chart),
  `/event-competitors/{occurrence_id}` (placements per division/role),
  `/upcoming-events`, and `/dancers-over-time`. Line charts are server-rendered
  SVG via `src/charts.py` + the `_line_chart.html` partial; the dancer
  points-over-time chart uses `multi_line_chart` + `_multi_line_chart.html`
  to draw one line per role (Leader/Follower) with a legend, plus a labelled
  dot on each line at the month the role first scored in each laddered
  (skill-ladder) division. A shared navbar
  (`base.html`) links the top-level pages.
- PWA: web manifest + icons (ported from the legacy site) and a `theme-color`,
  wired in `base.html`. The Google Play button is hidden inside the Android app.
- `/upcoming-events` has client-side search + "sort by distance" (progressive
  enhancement) and a subscribable iCalendar feed at `/wsdc_events.ics`.
- **Data importer** (`src/importer/`): fetches each dancer from WSDC and upserts
  it in its own transaction, looping forever. See *Data importer* below.
- Container/deploy: `Dockerfile`, `docker-compose.yml` (db + app + importer),
  `.dockerignore`, and a GitHub Actions workflow that builds the image and
  pushes it to GHCR (`.github/workflows/docker-publish.yml`).
- Hardening & SEO: themed HTML error pages (404/500), security headers + CSP +
  `/static` cache-control (in `main.py`), Open Graph/Twitter meta, `/robots.txt`,
  and `/sitemap.xml` (top-level pages + every event and dancer). `README.md`.
- `/service-worker.js` is a **self-destroying** service worker (in `pages.py`).
  The legacy Jekyll site registered a SW at this same path whose fetch handler
  re-issued navigations as `fetch(request.url)`, turning form POSTs (e.g. the
  star toggle) into GETs and 405s — visible only in installed-app (TWA) webviews
  where the old SW lingered. This one unregisters itself, clears caches, and
  reloads on activate. The app itself registers no service worker.
- `/.well-known/assetlinks.json` (in `pages.py`, served from
  `src/static/assetlinks.json`) is the Digital Asset Links file for the Android
  TWA (`dev.mechstack.wsdc.twa`). Without it the app shows a Custom Tab URL bar
  instead of running chrome-less; the fingerprint must match the app's signing
  key. Same content the legacy site served.

Not built yet:

- The tables stay empty until the importer has run a pass, so until then the
  pages render their empty states and the home page shows "Not yet updated".
- `/dancers-on-the-rise`, `/dancers-over-time`, `/division-progression` (the
  aggregate/chart pages).
- No automated tests.

## Stack

| Concern | Choice |
|---|---|
| Language | Python 3.13 |
| Web framework | FastAPI |
| Templating | Jinja2 (server-rendered HTML) |
| Database | PostgreSQL (via `asyncpg`) |
| ASGI server | uvicorn |
| Settings | pydantic-settings (`.env`) |

Pages are plain request → HTML responses. Each route runs a couple of indexed
read queries and renders a Jinja2 template; there is no client-side data
fetching.

## Layout

```
server/
├── AGENTS.md                 # this file
├── README.md                 # short intro / quickstart
├── requirements.txt
├── .env.example              # copy to .env
├── Dockerfile                # python:3.13-slim image (runs uvicorn / the importer)
├── docker-compose.yml        # db + app + importer
├── psql.sh                   # interactive psql into the compose `db` service
├── .dockerignore
├── .github/workflows/
│   └── docker-publish.yml    # build + push image to ghcr.io on push/tag
├── database/                 # database changes
│   ├── migrate.sh            # applies migrations/*.sql in order
│   ├── cleanup_stale_users.sql  # prunes users not seen in > 1 year
│   └── migrations/
│       ├── 001_initial_schema.sql
│       ├── 002_seed_reference_data.sql
│       ├── 003_users_and_favorites.sql
│       ├── 004_data_refreshes.sql
│       ├── 005_geocode_cache.sql
│       ├── 006_dancer_last_imported.sql
│       ├── 007_user_feed_token.sql
│       ├── 008_event_name_as_of.sql
│       ├── 009_placements_natural_key.sql
│       └── 010_placement_first_seen.sql
└── src/                      # application code (a Python package)
    ├── config.py             # Settings (DATABASE_URL, cookie, importer knobs)
    ├── db.py                 # asyncpg pool factory
    ├── migrate.py            # applies baked-in migrations (schema_migrations table)
    ├── charts.py             # SVG line-chart helper: line_chart([(date, value)…])
    │                         #   true date-spaced x, first/last labels, nice y ticks
    ├── divisions.py          # "can compete" eligibility logic (ported from fetch.py)
    ├── session.py            # anonymous `uid` cookie middleware + current_user_id dep
    ├── templates.py          # Jinja2Templates configured to src/templates
    ├── main.py               # app factory + lifespan + middleware/router/static wiring
    ├── routers/
    │   ├── health.py         # GET /health (also checks DB connectivity)
    │   ├── pages.py          # all server-rendered GET pages
    │   └── favorites.py      # POST /favorites/{id}, POST /favorites/{id}/delete
    ├── importer/             # WSDC -> Postgres data importer (run: python -m src.importer)
    │   ├── __main__.py       # forever loop: scan ids, fetch, upsert; --once / IMPORTER_OFFLINE
    │   ├── source.py         # WSDC fetch + events scrape/geocode + offline raw-file loaders
    │   ├── transform.py      # flatten one dancer response -> relational rows
    │   └── run.py            # per-dancer upsert + reference maps + upcoming/refresh writes
    ├── templates/            # base.html (+ navbar), index, about, dancers, dancer,
    │   │                     #   events, event, upcoming_events
    │   └── ...
    └── static/
        ├── manifest.webmanifest          # PWA manifest (ported from legacy)
        ├── css/index.css                 # immersive dark theme (tokens, per-page bg)
        ├── img/                          # dance photos (per-page backgrounds, hero)
        ├── js/
        │   ├── list-search.js            # tokenized, debounced search over #item-list (events, upcoming)
        │   ├── dancers-list.js           # /dancers: embedded JSON, chunked render + search
        │   ├── distance-sort.js          # "sort by distance" via Geolocation + IP fallback (upcoming)
        │   ├── star.js                   # star/unstar via fetch (no nav → no extra history entry)
        │   └── matomo.js                 # self-hosted Matomo analytics loader (mat.mechstack.dev, site 7)
        └── icons/
            ├── getItOnGooglePlay.svg     # Google Play badge (copied from assets/)
            ├── favicon.png               # favicon (copied from the legacy assets/)
            ├── themed-mask-icon.png      # PWA maskable icon
            └── apple-mask-icon.svg       # PWA monochrome icon
```

## Estimating Approximate Number of Competitors

The WSDC awards points per placement based on a tier system where the number of
competitors in a role (Leader or Follower) for a given division determines the tier, which
determines the points awarded. Working backwards, given the points earned by any
placement we can identify the tier and thus estimate the approximate number of
competitors.

**Key principle:** Tiers are per-role — Leaders and Followers may be in different tiers for
the same contest at the same event. Minimum for a WSDC-registered contest: 5 Leaders
and 5 Followers in finals.

### Era 1: Pre-January 1, 2007 (rules not available)

No rule documents have been located for competitions before January 2007.
**Competitor counts cannot be inferred from these records.**

### Era 2: January 1, 2007 – October 31, 2008 (3-tier, couple-based, different point values)

Source: WSDC Points Registry, effective January 1, 2007.  
Tier was determined by the number of **couples** — the *lower* of leaders vs. followers —
so both roles were always in the same tier. Point values for Tiers 1 and 3 differ from
all later eras.

| Tier | Couples | 1st | 2nd | 3rd | 4th | 5th | Additional |
|------|---------|-----|-----|-----|-----|-----|------------|
| 1    | 5–15    | 8   | 6   | 4   | 2   | 1   | 0          |
| 2    | 16–39   | 10  | 8   | 6   | 4   | 2   | 1 pt each, 6th–10th |
| 3    | 40+     | 12  | 10  | 8   | 6   | 4   | 1 pt, all finalists |

Tier 1 1st-place value `8` and Tier 3 1st-place value `12` are unique to this era.
Tier 2 values (10/8/6/4/2) are identical to the next era.

### Era 3: November 1, 2008 – December 31, 2010 (3-tier, couple-based, revised points)

Source: WSDC Points Registry, updated November 2008.  
Still couple-based counting, but Tier 1 and 3 point values were revised.
Identical point values to Era 4 below.

| Tier | Couples | 1st | 2nd | 3rd | 4th | 5th | Additional |
|------|---------|-----|-----|-----|-----|-----|------------|
| 1    | 5–15    | 5   | 4   | 3   | 2   | 1   | 0          |
| 2    | 16–39   | 10  | 8   | 6   | 4   | 2   | 1 pt each, 6th–10th |
| 3    | 40+     | 15  | 12  | 10  | 8   | 6   | 1 pt, all finalists |

### Era 4: January 1, 2011 – January 2, 2018 (3-tier, per-role counting)

Source: WSDC Points Registry, updated August 2010, effective January 1, 2011.  
Switched from couple-based to **per-role** counting: leaders and followers can now fall
into different tiers for the same contest. Same point values as Era 3.

| Tier | Competitors (per role) | 1st | 2nd | 3rd | 4th | 5th | Additional |
|------|------------------------|-----|-----|-----|-----|-----|------------|
| 1    | 5–15                   | 5   | 4   | 3   | 2   | 1   | 0          |
| 2    | 16–39                  | 10  | 8   | 6   | 4   | 2   | 1 pt each, 6th–10th |
| 3    | 40+                    | 15  | 12  | 10  | 8   | 6   | 1 pt, all finalists |

**Caution:** 1st-place values `10` and `15` overlap with the post-2018 system (Tier 3 and
Tier 4 respectively). Always check the competition date before applying this table.

### Era 5: January 3, 2018 – present (6-tier system)

Announced at the WSDC general membership meeting, November 25, 2017; effective
January 3, 2018. Based on WSDC's analysis of 2015–2016 competition data.

| Tier | Competitors (per role) | 1st | 2nd | 3rd | 4th | 5th | Additional |
|------|------------------------|-----|-----|-----|-----|-----|------------|
| 1    | 5–10                   | 3   | 2   | 1   | 0   | 0   | 0 |
| 2    | 11–19                  | 6   | 4   | 3   | 2   | 1   | 0 |
| 3    | 20–39                  | 10  | 8   | 6   | 4   | 2   | 1 pt, up to 10th |
| 4    | 40–79                  | 15  | 12  | 10  | 8   | 6   | 1 pt, up to 12th |
| 5    | 80–129                 | 20  | 16  | 14  | 12  | 10  | 2 pts, up to 15th |
| 6    | 130+                   | 25  | 22  | 18  | 15  | 12  | 2 pts, up to 15th |

For any placement position 1st–5th, the point value uniquely identifies the tier across
all six tiers. Example: 1st place with 20 points → Tier 5 → 80–129 competitors.

**Tier 6 is open-ended.** Tier 6 covers 130+ competitors with no upper bound; large
events regularly field 200–400+ competitors per role in popular divisions.

#### Minor changes to additional-placement cutoffs within the 6-tier era

These changes affect only how many places beyond 5th receive any points; they do
**not** change the 1st–5th point values used to identify the tier.

| Period | Tier 3 additional | Tier 4 additional | Tier 5 additional |
|--------|-------------------|-------------------|-------------------|
| Jan 2018 – ~early 2024 | 1 pt, up to 12th | 1 pt, up to 15th | 1 pt, up to 15th |
| ~March 2024 – ~late 2024 | 1 pt, up to 10th | 1 pt, up to 15th | 2 pts, up to 15th |
| Jan 2025 – present | 1 pt, up to 10th | 1 pt, up to 12th | 2 pts, up to 15th |

### How the code uses this

`src/importer/transform.py` implements `_tier_for_placement(result, points, date)`
which selects the era by date, then does a `(result, points)` lookup in that era's
table. Era boundaries are defined as constants:

```python
ERA1_START = datetime.date(2007, 1, 1)   # 2007 rules
ERA2_START = datetime.date(2008, 11, 1)  # 2009 rules (updated Nov 2008)
ERA3_START = datetime.date(2011, 1, 1)   # per-role counting (same points as Era 2/3)
ERA4_START = datetime.date(2018, 1, 3)   # 6-tier rules
```

Lookup tables: `_ERA1`, `_ERA2_3` (shared by Eras 3 and 4 — same point values),
`_ERA4`. Returns `None` for "F" (finalist) results and pre-2007 dates.

Tiers are stored in `event_occurrence_tiers` keyed on
`(event_occurrence_id, division_id, role_id)` — one row per role per division per
occurrence. Any result in `("1","2","3","4","5")` that resolves unambiguously to a
tier triggers an upsert; the last writer wins (idempotent across dancer imports).

The `event_occurrence_tiers` table stores the tier string for each 1st-place finish
(post-2020 per the current code), so SQL like the following can recover the competitor
range for any 1st-place win without re-deriving from points:

```sql
SELECT tier FROM event_occurrence_tiers
WHERE event_occurrence_id = $1 AND division_id = $2 AND role_id = $3;
```

### Deriving competitor count for any placement

1. Get the competition date for the placement.
2. Select the applicable tier table (3-tier for Jan 2012–Jan 2018; 6-tier for Jan 2018+;
   unknown for pre-Jan 2012).
3. Find which tier's row matches the placement's (position, points) pair. For positions
   1st–5th the match is unambiguous within each era. For additional placements
   (all earning 1–2 pts), check the 1st-place points for the same
   event/occurrence/division/role to confirm the tier.
4. The tier gives the competitor count range. Use the range midpoint or the range
   itself depending on the use case.

## Database

The schema mirrors the relational design documented in the root `AGENTS.md`
(roles, divisions, dancers, events, event_occurrences, event_occurrence_tiers,
placements, upcoming_events) plus the read-path indexes on `placements`. There
is intentionally **no** denormalized competitors table — competitor lookups use
`idx_placements_occurrence`.

Migration `003` adds two tables for anonymous starred dancers (see *Sessions &
favorites* below):
- `users` — one row per anonymous visitor: `id` (UUID, stored in the `uid`
  cookie), `created_at`, `last_seen`. Indexed on `last_seen` for pruning.
- `favorite_dancers` — `(user_id, dancer_id)` join table, `ON DELETE CASCADE`
  from `users` so pruning a user also removes their stars.

`gen_random_uuid()` requires PostgreSQL 13+.

Migration `004` adds `data_refreshes`, an append-only log of successful imports
(`id`, `completed_at`). The home page's "last updated" line is
`SELECT MAX(completed_at) FROM data_refreshes`; the importer inserts a row at the
end of each pass. With no rows yet, the page shows "Not yet updated".

Migration `005` adds `geocode_cache` (`location` PK, `latitude`, `longitude`,
`updated_at`) — the importer's persisted geocoding cache, replacing the legacy
`points/locations.json`. A row with NULL lat/lon records a known miss so that
location isn't re-queried. To fix misses, `GET /geocode-fixups.sql` downloads a
script with one blank `UPDATE geocode_cache …` per NULL row; fill in the
coordinates, then paste/run them — `./psql.sh` opens a psql prompt on the
compose `db` service for exactly this — and re-run the importer so
`upcoming_events` picks up the new coordinates.

Migration `006` adds `dancers.last_imported_at` (+ index), which the importer
stamps on every fetch to drive its prioritised refresh (see *Data importer*).

Migration `007` adds `users.feed_token` (UUID, unique, defaulting to
`gen_random_uuid()`) — the per-user secret that authorises the favorites RSS
feed without a cookie (see *Sessions & favorites*). The volatile default
backfills a distinct token for every existing user when the column is added.

Migration `008` adds `events.name_as_of` (DATE), the occurrence date the stored
event name/location came from. Events are shared across dancers, so the importer
only overwrites the name when it sees a **more recent (or equal) occurrence**,
keeping the most recently seen name instead of letting whichever dancer was
imported last win (see *Per-dancer transaction*). Backfilled from each event's
newest occurrence.

Division ids in the seed match the **WSDC API** division objects (note: these
differ from the legacy `points/fetch.py` `DIVISIONS_MAP` ids for non-skill
divisions 9–13).

Migrations are plain numbered SQL files. **Applying them is the image's job**:
the files are baked into the image (`COPY database/migrations`) and `src/migrate.py`
applies any not yet recorded in a `schema_migrations` table, each in its own
transaction, under a Postgres advisory lock. The app and importer call
`ensure_migrated()` on startup (unless `AUTO_MIGRATE=false`), so a deploy needs
**no source checkout and no initdb mount** — just the image and a database.

- Run standalone: `python -m src.migrate`.
- The individual `.sql` files aren't idempotent, but the runner is: it skips
  already-applied files. A database created the old way (initdb mount) has the
  schema but no tracking rows — on first run the runner detects this and
  backfills the current files as applied instead of re-running them.
- `database/migrate.sh` (psql, no tracking) still works for a fresh local DB.

There is not yet an importer that loads dancer/event/placement data from the
WSDC source into these tables; only reference data (roles, divisions) is seeded.

## Running

### Docker Compose (db + app + importer)

```bash
docker compose up --build
```

Brings up Postgres, the FastAPI app on `:8000`, and the importer loop. The app
and importer apply migrations on startup from the SQL baked into the image (see
*Database*). Credentials are `postgres:postgres`, db `wsdc` (dev only). Set
`OPEN_WEATHER_MAP_API_KEY` in the environment to enable event geocoding.

### Local (without Docker)

```bash
cd server
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # edit DATABASE_URL if needed
./database/migrate.sh         # requires DATABASE_URL in the environment

uvicorn src.main:app --reload
python -m src.importer --once  # one import pass (omit --once to loop forever)

# Offline test: import from the legacy raw files, no WSDC/OWM calls:
IMPORTER_OFFLINE=1 python -m src.importer --once
```

Then:
- `http://127.0.0.1:8000/` — home page (last-updated, dancer/event counts, links, starred dancers)
- `http://127.0.0.1:8000/health` — `{"status": "ok"}` if the DB is reachable

Run `uvicorn` from the `server/` directory so that `src` resolves as a package
and `.env` is picked up from the working directory.

## Sessions & favorites

There is no login. `src/session.py` registers an HTTP middleware that, on every
page request (static assets and `/health` are skipped):

1. Reads the `uid` cookie. If it is a valid UUID for an existing user, it bumps
   that user's `last_seen` to `now()`.
2. Otherwise it inserts a new `users` row and uses that id.
3. Stores the id on `request.state.user_id` and (re)sets the `uid` cookie
   (HttpOnly, SameSite=Lax, 1-year max-age, `Secure` when `cookie_secure=true`).

Handlers read the current user via the `current_user_id` dependency. Favorites
are changed with plain HTML form POSTs (no JavaScript):

- `POST /favorites/{dancer_id}` — star a dancer (`INSERT ... ON CONFLICT DO NOTHING`)
- `POST /favorites/{dancer_id}/delete` — unstar a dancer

Both redirect (303) back to the `Referer`, or `/`. The home page lists the
current user's starred dancers with their most recent placement month, and the
"Starred Dancers" section is omitted entirely when they have none.

**Favorites RSS feed.** `GET /feed/{feed_token}.xml` is a per-user RSS 2.0 feed
of the newest placements (50) of that user's starred dancers, each item naming
the division/role, place, points, event, location, and month. `feed_token` is
the user's `users.feed_token` UUID (migration 007) — opaque enough to embed in
a subscription URL, so no cookie is needed. The home page shows a small "RSS"
link next to the "Starred Dancers" heading (only when they have favorites and so
a token is in scope). Fetching the feed also bumps that user's `last_seen`, so a
subscriber who never opens a browser isn't pruned as stale.

Each item's `<guid>` is derived from the placement's **stable natural key**
(`dancer_id`, `event_occurrence_id`, `division_id`, `role_id`), not the
surrogate `placements.id`. The importer now upserts placements idempotently so
`p.id` is stable (see *Per-dancer transaction*), but the guid stays keyed on the
natural key — it's the durable identity regardless of how rows are written, and
historically the importer reassigned `p.id` every pass, which made every item
look brand-new to RSS readers on each run.

The feed is a **news feed, not a history dump**: it only includes placements
where `p.first_seen_at >= fd.created_at` (migration 010), so starring a dancer
doesn't flood the reader with their entire competition history — only results
imported after the star appear. `first_seen_at` (default `now()`, preserved by
the guarded upsert) is also the item's `pubDate` and the sort key, because
results are imported weeks after the event and readers sort by `pubDate`; the
event's first-of-month date would bury fresh news under old-dated items.
Consequence: a newly starred dancer contributes nothing until new results
arrive for them.

Prune visitors who haven't returned in over a year by running
`database/cleanup_stale_users.sql` on a schedule (cron, etc.); the cascade
removes their favorites.

### Android app (TWA) detection

The site is also shipped as an Android Trusted Web Activity
(`dev.mechstack.wsdc.twa`). Its first navigation arrives with a Referer of
`android-app://<package>`; the session middleware latches that into an `app=1`
cookie and sets `request.state.is_app` on every request thereafter (a normal
browser never sees that referer, and the TWA has its own cookie jar). The home
template hides the "Get it on Google Play" button when `is_app` is set — pass
`is_app` into any other template that needs it.

## Public data export

`GET /data.json` streams the whole dataset for anyone who wants to download it:
a JSON object keyed by table name, each value the list of that table's rows.
Every `public` base table is included **except** those in `_PRIVATE_TABLES`
(`routers/pages.py`): the private `users`/`favorite_dancers`, plus the
operational/derived `schema_migrations`, `geocode_cache`,
`event_occurrence_tiers`, and `data_refreshes`. Rows are
streamed straight from per-table server-side cursors (inside a transaction) via
`StreamingResponse`, so the large tables (placements) are never fully buffered.
`_json_default` coerces the Postgres types `json` can't (`date`/`datetime` →
ISO, `Decimal` → float, `UUID` → str).

## Adding a page

1. Add a handler to `src/routers/pages.py` (or a new router included in
   `main.py`) returning `templates.TemplateResponse(request, "<name>.html", ctx)`.
2. Add the template under `src/templates/`, extending `base.html`.
3. Query data with the pool: `async with request.app.state.pool.acquire() as conn`.

## Conventions & gotchas

- **Server-rendered only.** Pages return
  `templates.TemplateResponse(request, "name.html", ctx)` — note Starlette's
  newer signature with `request` first. `/health` is JSON; `/wsdc_events.ics`
  is `text/calendar`. Client JS is progressive enhancement only (no AJAX except
  the geojs.io IP fallback noted below):
  - `static/js/list-search.js` — tokenized, debounced (200 ms) search over any
    `#item-list` of `[data-search]` cards driven by `#list-search`. Per-word and
    within-word: "el smith" matches "michael w. smith". Used by events/upcoming.
  - `static/js/distance-sort.js` — upcoming-events "sort by distance". Tries the
    Geolocation API, then falls back to a coarse IP lookup
    (`https://get.geojs.io/v1/ip/geo.json`) when the browser provider is
    unavailable/denied (common on Firefox/Linux) — the one outbound request.
  - `static/js/dancers-list.js` — `/dancers` only. The page **doesn't** render
    rows server-side: the handler embeds the whole list (`[id, name]` pairs,
    ordered by id desc) as JSON in a `<script type="application/json">`, and the
    JS renders it in 100-row chunks (appended on scroll via IntersectionObserver)
    with the same tokenized/debounced search. Requires JS (has a `<noscript>`).
    `GZipMiddleware` keeps the ~700 KB payload ~270 KB on the wire.
  - `static/js/star.js` — intercepts `.star-form` submits and toggles the star
    via `fetch` (POST, `redirect:"manual"`). The plain-form fallback uses
    Post/Redirect/Get back to the same page, which adds a duplicate history entry
    (so "back" needs two presses); fetch avoids the navigation entirely. Loaded
    globally from `base.html`; falls back to a real submit on any error.
  - `static/js/matomo.js` — self-hosted Matomo analytics (mat.mechstack.dev, site
    id 7). The legacy Jekyll site inlined this snippet; here it's an external file
    so the CSP stays strict (no `'unsafe-inline'`). Loaded globally from
    `base.html`; the CSP allow-lists `https://mat.mechstack.dev` for `script-src`
    (loads `matomo.js`), `img-src`, and `connect-src` (tracking to `matomo.php`).

  Templates needing extra `<head>` tags use the `{% block head %}` in `base.html`.

- **Behind a reverse proxy.** The container runs uvicorn with `--proxy-headers
  --forwarded-allow-ips "*"` (see `Dockerfile`) so `X-Forwarded-Proto` is honored
  and `request.base_url`/`request.url` are https. Absolute URLs (RSS feed, Open
  Graph `og:url`/`og:image`, `sitemap.xml`, `robots.txt`, the ICS feed) derive
  from those, so without this they render as http. Safe because the app is only
  reachable through the proxy on a private network.
- **Theme.** `css/index.css` is an immersive dark theme: CSS-variable tokens
  (`--brand` green, `--panel`, `--text`, etc.), a frosted translucent content
  panel over a full-bleed per-page dance photo, sticky blurred navbar with an
  active-link state, and zebra/hover tables. Each page sets its background via
  `{% block body_class %}bg-<name>{% endblock %}`; the `.bg-*` classes each map
  to a distinct photo in `static/img/` (only `/event` and its
  `/event-competitors` sub-page share one). New pages should set a `body_class`
  (add a `.bg-*` rule with a photo) and reuse the `.card`/`.data-table`/`.chart`
  classes. A wide table that would overflow a phone can add the `responsive`
  modifier (`class="data-table responsive"`) and a `data-label="…"` on each
  `<td>`: under `@media (max-width: 36rem)` the header is hidden and every row
  restacks into a labelled card (used by the dancer placements table).
- **Mutations use the PRG pattern.** HTML form POST → `RedirectResponse(...,
  status_code=303)` back to `Referer`. HTML forms support only GET/POST, so
  deletes are modeled as `POST /.../delete`, not HTTP DELETE.
- **asyncpg `Record` in templates.** `{{ row.name }}` works because Jinja falls
  back from attribute to item access. `DATE` columns come back as
  `datetime.date`, so `{{ row.last_placed.strftime('%B %Y') }}` is fine.
- **Date display** uses `strftime('%B %d, %Y')` (zero-padded, no ordinal). The
  legacy Jekyll site rendered ordinals ("5th"); add a Jinja filter to match.
- **Config** is env / `.env` via pydantic-settings. Set `COOKIE_SECURE=true` in
  production (HTTPS) so the session cookie is marked `Secure` — that flag also
  switches on the `Strict-Transport-Security` header.
- **Hardening.** `main.py` adds a middleware setting `Content-Security-Policy`
  (same-origin + `https://get.geojs.io` for the distance sort and
  `https://mat.mechstack.dev` for Matomo analytics),
  `X-Content-Type-Options`, `Referrer-Policy`, and `Cache-Control` for `/static`
  (30 d for images, 1 h for css/js). Unhandled and HTTP errors render the themed
  `error.html` via exception handlers — keep new templates working without extra
  CSP allowances (no inline scripts/styles).
- **Run from `server/`** so `src` imports as a package and `.env` loads from CWD.
- **The home page does not yet match the legacy theme** (background images, nav
  arrows, ordinal date). Porting `assets/css/index.css` + images is a separate task.

## Data importer (`src/importer/`)

Unlike the legacy `points/` pipeline, the importer keeps **no dancer cache**. It
fetches each dancer straight from the WSDC API and upserts that one dancer in its
own transaction, so it can run as a slow loop forever, refreshing every dancer
over and over.

Run it with `python -m src.importer` (forever loop) or
`python -m src.importer --once` (one full pass, then exit). The Docker Compose
`importer` service runs the forever loop.

### How a pass works (`__main__.run_pass`)

1. Scrape the events page (`source.fetch_events_page`), geocode each location
   via the `geocode_cache` table (`source.geocode_location` on a cache miss),
   and replace `upcoming_events` (`run.refresh_upcoming_events`). Best-effort —
   a scrape failure doesn't stop the dancer scan. **Geocoding is skipped (an
   error is logged) when `OPEN_WEATHER_MAP_API_KEY` is unset**; events are still
   stored, just without coordinates.
2. Fetch a **prioritised set of ids already in the database**
   (`run.candidate_ids`), then **scan upward from the max id** for brand-new
   dancers (`source.fetch_dancer` = `POST .../lookup2020/find`) until
   `importer_none_slide_limit` (default 200) consecutive misses. Found dancers
   are flattened (`transform.transform_dancer`) and upserted
   (`run.import_dancer`, which stamps `dancers.last_imported_at`). Ids **not** in
   the database below the max are never re-probed, so empty ids aren't retried
   every pass.
3. Insert one `data_refreshes` row so the home page's "last updated" advances.

The forever loop then repeats. `importer_request_delay_seconds` (default 30.0)
throttles the per-dancer fetch; `importer_pass_delay_seconds` sleeps between
passes.

**Prioritisation (`run.candidate_ids`).** A dancer who placed within
`importer_recent_years` (default 2) is *likely* to have changed and is fetched
**every pass** (likely cohort first). Everyone else is *unlikely* and only
re-fetched once their `last_imported_at` is older than
`importer_unlikely_refresh_days` (default 28) — so the long tail rotates through
roughly monthly instead of being hammered weekly. (Offline mode ignores all of
this and imports the whole file.) As of mid-2026 the likely cohort is ~9k of
~26.5k dancers, so at the default 30 s delay a pass takes ~4 days.

### Per-dancer transaction (`run.import_dancer`)

Each dancer is written in a single `conn.transaction()`:

- Upsert the `dancers` row (each fetch is authoritative for that dancer, so its
  name is always refreshed to the latest) and the `events` they reference. Event
  name/location only update when this dancer's occurrence is at least as recent
  as `events.name_as_of` (migration 008) — events are shared and recur, so this
  keeps the **most recently seen** name rather than letting whichever dancer was
  imported last win.
- Upsert `event_occurrences` (date normalized to the first of the month) and read
  back their generated ids via `... ON CONFLICT (event_id, date) DO UPDATE SET
  event_id = EXCLUDED.event_id RETURNING id` (the no-op update forces conflicting
  rows into `RETURNING`).
- Reconcile this dancer's placements (West Coast Swing only) idempotently:
  upsert on the natural key `(dancer_id, event_occurrence_id, division_id,
  role_id)` (migration 009), with the `DO UPDATE` guarded by `WHERE
  placements.result IS DISTINCT FROM EXCLUDED.result OR placements.points IS
  DISTINCT FROM EXCLUDED.points` so unchanged rows aren't rewritten, then
  `DELETE` only the rows no longer present. This replaced an earlier
  delete-all-then-reinsert that churned the table (dead tuples + WAL even for
  unchanged rows) and reassigned `placements.id` every pass; ids are now stable,
  so `id` is safe to reference but the RSS guid still keys on the natural key
  (see *Favorites RSS feed*). The guarded upsert also preserves
  `placements.first_seen_at` (migration 010, default `now()` on insert only),
  which the RSS feed relies on to show just the placements that arrived after a
  dancer was starred. Note `INSERT ... ON CONFLICT` still consumes one
  `IDENTITY` value per incoming row even on conflict, so the id sequence keeps
  advancing at about the same rate — a pre-existing concern, addressable by
  moving `placements.id` to `BIGINT` if INTEGER exhaustion ever looms.
- Upsert `event_occurrence_tiers` for this dancer's first-place finishes
  (post-2020). Tiers are owned by whoever placed first, so each winner sets the
  tier for their occurrence/division/role.

Dancers and events are only ever upserted (never deleted), so `favorite_dancers`
foreign keys stay valid across runs.

### Mapping & filtering

- Division name → `divisions.id` (abbreviation as fallback) using the **WSDC API
  ids** seeded in migration 002. Do **not** reuse `fetch.py`'s `DIVISIONS_MAP`
  integers — they differ for ids 9–13. Role: `leader`→1, `follower`→2; the
  dancer's primary role from `short_dominate_role`.
- Only `West Coast Swing` placements; dancers with none are skipped.
- The raw response shape is documented in the root `AGENTS.md` under "Raw WSDC
  API Response Structure".

Derived calculations from `fetch.py` (competable divisions, rising dancers,
new-dancers-over-time, division progression) are **not** computed yet — add them
when those aggregate pages are built (see the "Precomputed vs. derived" table in
the root `AGENTS.md`).

### Offline test mode

Set `IMPORTER_OFFLINE=1` to run the importer against the legacy raw cache files
instead of hitting WSDC — useful for testing the full transform/write path
locally. It reads dancers from `RAW_RESPONSES_PATH`
(`raw_responses.json.gz`, ~27k dancers, iterated in id order) and events from
`RAW_EVENTS_PATH` (`raw_events.html.gz`), applies no request delay, and otherwise
runs identically. Pair with `--once`:

```bash
IMPORTER_OFFLINE=1 python -m src.importer --once
```

Without an `OPEN_WEATHER_MAP_API_KEY` this touches no external services at all
(geocoding is skipped). The default paths point at the sibling legacy repo
(`../wsdc_points/points/`).

## Page porting roadmap

Legacy pages live in `pages/` (each is documented in the root `AGENTS.md`).
Done: `/about`; `/events` (searchable card list); `/dancers` (full list embedded
as JSON, rendered client-side in chunks, id-desc, tokenized search); `/dancer/{id}`
(star-icon favorite toggle, points pivoted to Division/Leader/Follower, cleaned
placements table, points-over-time chart); `/event/{id}` (tiered occurrences as
a Division/Leader/Follower table, a per-date "pointed"-count link (dancers who
earned points, not total entrants), and a pointed-over-time chart; other dates
listed plainly);
`/event-competitors/{occurrence_id}` (placements grouped by division then role,
place/points/dancer link); `/upcoming-events` (search, distance sort,
Google-Maps location links, `/wsdc_events.ics` calendar feed);
`/dancers-over-time` (cumulative dancers with ≥1 point per month since 2000,
via the shared `charts.line_chart` + `_line_chart.html` — no JS/Chart.js).

All line charts take a `[(date, value)…]` series and share `charts.line_chart`:
x is positioned by true date (gaps show), the first and last points are always
labelled, and the y-axis uses nice round ticks plus the series' first value.

Still to port:

- `/dancers-on-the-rise`, `/division-progression` — aggregate/chart pages
  (legacy used Chart.js; use `charts.line_chart` + `_line_chart.html` for the
  server-side-SVG approach, as `/dancers-over-time`, the dancer points chart,
  and the event competitors chart do).

Possible refinements to the pages already built: `/dancers` renders every dancer
(~26k) in one searchable list — consider server-side pagination if the page
weight becomes a problem.
