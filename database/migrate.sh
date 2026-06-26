#!/usr/bin/env bash
# Apply all migrations in order against $DATABASE_URL.
# Migrations are not idempotent: run against a fresh database.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

: "${DATABASE_URL:?Set DATABASE_URL (e.g. postgresql://localhost:5432/wsdc)}"

for f in "$DIR"/migrations/*.sql; do
  echo "Applying $(basename "$f")"
  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f "$f"
done

echo "Migrations complete."
