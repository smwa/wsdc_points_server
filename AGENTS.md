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
  competitor-count links, competitors-over-time chart),
  `/event-competitors/{occurrence_id}` (placements per division/role),
  `/upcoming-events`, and `/dancers-over-time`. Line charts are server-rendered
  SVG via `src/charts.py` + the `_line_chart.html` partial. A shared navbar
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
│       └── 006_dancer_last_imported.sql
└── src/                      # application code (a Python package)
    ├── config.py             # Settings (DATABASE_URL, cookie, importer knobs)
    ├── db.py                 # asyncpg pool factory
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
        │   └── distance-sort.js          # "sort by distance" via Geolocation + IP fallback (upcoming)
        └── icons/
            ├── getItOnGooglePlay.svg     # Google Play badge (copied from assets/)
            ├── favicon.png               # favicon (copied from the legacy assets/)
            ├── themed-mask-icon.png      # PWA maskable icon
            └── apple-mask-icon.svg       # PWA monochrome icon
```

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

Division ids in the seed match the **WSDC API** division objects (note: these
differ from the legacy `points/fetch.py` `DIVISIONS_MAP` ids for non-skill
divisions 9–13).

Migrations are plain numbered SQL files, applied in order. They are **not
idempotent** — run them against a fresh database.

```bash
createdb wsdc
export DATABASE_URL=postgresql://localhost:5432/wsdc
./database/migrate.sh
```

There is not yet an importer that loads dancer/event/placement data from the
WSDC source into these tables; only reference data (roles, divisions) is seeded.

## Running

### Docker Compose (db + app + importer)

```bash
docker compose up --build
```

Brings up Postgres (migrations 001–004 run automatically from
`/docker-entrypoint-initdb.d` on first init), the FastAPI app on `:8000`, and
the importer loop. Credentials are `postgres:postgres`, db `wsdc` (dev only).
Set `OPEN_WEATHER_MAP_API_KEY` in the environment to enable event geocoding.

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

  Templates needing extra `<head>` tags use the `{% block head %}` in `base.html`.
- **Theme.** `css/index.css` is an immersive dark theme: CSS-variable tokens
  (`--brand` green, `--panel`, `--text`, etc.), a frosted translucent content
  panel over a full-bleed per-page dance photo, sticky blurred navbar with an
  active-link state, and zebra/hover tables. Each page sets its background via
  `{% block body_class %}bg-<name>{% endblock %}`; the `.bg-*` classes each map
  to a distinct photo in `static/img/` (only `/event` and its
  `/event-competitors` sub-page share one). New pages should set a `body_class`
  (add a `.bg-*` rule with a photo) and reuse the `.card`/`.data-table`/`.chart`
  classes.
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
  (same-origin + `connect-src https://get.geojs.io` for the distance sort),
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
`importer_recent_years` (default 3) is *likely* to have changed and is fetched
**every pass** (likely cohort first). Everyone else is *unlikely* and only
re-fetched once their `last_imported_at` is older than
`importer_unlikely_refresh_days` (default 28) — so the long tail rotates through
roughly monthly instead of being hammered weekly. (Offline mode ignores all of
this and imports the whole file.)

### Per-dancer transaction (`run.import_dancer`)

Each dancer is written in a single `conn.transaction()`:

- Upsert the `dancers` row and the `events` they reference (`ON CONFLICT DO
  UPDATE` — events recur and are shared; latest writer wins for name/location).
- Upsert `event_occurrences` (date normalized to the first of the month) and read
  back their generated ids via `... ON CONFLICT (event_id, date) DO UPDATE SET
  event_id = EXCLUDED.event_id RETURNING id` (the no-op update forces conflicting
  rows into `RETURNING`).
- `DELETE FROM placements WHERE dancer_id = $1`, then reinsert just this dancer's
  placements (West Coast Swing only).
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
a Division/Leader/Follower table, a per-date competitor-count link, and a
competitors-over-time chart; other dates listed plainly);
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
