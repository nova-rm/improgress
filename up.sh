#!/usr/bin/env bash
# Un comando: tests en contenedor → Postgres (volumen existente) + API/UI.
# No recarga tablas. No arranca el job diario.
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -f .env ]]; then
  cp .env.example .env
fi

docker compose build test api
docker compose run --rm --no-deps test
docker compose up -d postgres api

PORT="${API_PORT:-8000}"
echo
echo "Listo. UI:  http://localhost:${PORT}"
echo "Health:     http://localhost:${PORT}/health"
echo "API docs:   http://localhost:${PORT}/docs"
