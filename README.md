# WSDC Points — server

A server-rendered site for **West Coast Swing** competition data from the
[WSDC](https://worldsdc.com) registry: look up dancers' points and division
eligibility, browse past events and their competitors, and see upcoming
sanctioned events. It replaces an older Jekyll static-site + flat-file approach
with HTML rendered on the server from PostgreSQL.

## Stack

FastAPI · Jinja2 (server-rendered HTML, minimal progressive-enhancement JS) ·
PostgreSQL (`asyncpg`) · uvicorn · Docker.

## Quick start (Docker)

```bash
cp .env.example .env          # add OPEN_WEATHER_MAP_API_KEY for event geocoding
docker compose up --build
```

This starts PostgreSQL (migrations apply automatically on first init), the app on
<http://localhost:8000>, and the data importer. Credentials are
`postgres:postgres` / db `wsdc` (dev only).

To load data without hitting WSDC, point the importer at the legacy cached files
and run a single offline pass (set `IMPORTER_OFFLINE=true` in `.env`):

```bash
docker compose run --rm importer python -m src.importer --once
```

## Pages

`/` home · `/dancers` · `/dancer/{id}` · `/events` · `/event/{id}` ·
`/event-competitors/{occurrence_id}` · `/upcoming-events` (+ `/wsdc_events.ics`) ·
`/dancers-over-time` · `/about`. `/health` is the JSON health check.

## Data importer

`python -m src.importer` fetches each dancer from WSDC and upserts it in its own
transaction, prioritising recent competitors and looping forever; `--once` runs a
single pass and `IMPORTER_OFFLINE=1` reads the legacy cache files instead of the
network. See [AGENTS.md](AGENTS.md) for the full design.

## Local development (without Docker)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                  # set DATABASE_URL
./database/migrate.sh                 # needs DATABASE_URL in the environment
uvicorn src.main:app --reload
```

## More

[AGENTS.md](AGENTS.md) is the detailed reference (schema, importer internals,
theme conventions, deployment). The image is published to GHCR by
`.github/workflows/docker-publish.yml`.
