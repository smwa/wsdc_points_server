#!/usr/bin/env bash
# Open an interactive psql prompt on the docker-compose `db` service, so you can
# paste SQL directly (e.g. an edited geocode_fixups.sql). Runs from anywhere.
#
#   ./psql.sh                       # interactive prompt
#   ./psql.sh -c "SELECT now();"    # one-off command
#   ./psql.sh -f some_file.sql      # run a file
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
exec docker compose exec db psql -U postgres -d wsdc "$@"
