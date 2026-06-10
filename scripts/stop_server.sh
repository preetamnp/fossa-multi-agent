#!/usr/bin/env bash
set -euo pipefail

PORT="${AGENT_HTTP_PORT:-8080}"
PIDS="$(lsof -ti ":${PORT}" 2>/dev/null || true)"

if [[ -z "${PIDS}" ]]; then
  echo "No process listening on port ${PORT}."
  exit 0
fi

echo "Stopping process(es) on port ${PORT}: ${PIDS}"
kill ${PIDS} 2>/dev/null || true
sleep 1

if lsof -ti ":${PORT}" >/dev/null 2>&1; then
  echo "Force stopping..."
  lsof -ti ":${PORT}" | xargs kill -9 2>/dev/null || true
fi

echo "Port ${PORT} is free."
