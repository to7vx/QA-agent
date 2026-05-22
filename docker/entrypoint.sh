#!/usr/bin/env bash
# Apply DB migrations (Postgres only) then exec the given command.
#
# SQLite uses metadata.create_all on startup (no migration step), so we only
# run Alembic when pointed at a real Postgres database.
set -euo pipefail

case "${QA_AGENT_DATABASE_URL:-}" in
  postgres*|postgresql*)
    echo "[entrypoint] Running Alembic migrations..."
    alembic upgrade head
    ;;
  *)
    echo "[entrypoint] Non-Postgres database — skipping Alembic, using create_all."
    ;;
esac

exec "$@"
