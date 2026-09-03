#!/usr/bin/env bash
# Stop NSFlow (Neuro SAN Studio web UI) on NSFLOW_PORT (default 4173).
set -euo pipefail

NSFLOW_PORT="${NSFLOW_PORT:-4173}"
PIDS="$(lsof -ti ":${NSFLOW_PORT}" -sTCP:LISTEN 2>/dev/null || true)"

if [[ -z "${PIDS}" ]]; then
  echo "No process listening on NSFlow port ${NSFLOW_PORT}."
  exit 0
fi

echo "Stopping NSFlow listener(s) on port ${NSFLOW_PORT}: ${PIDS}"
kill ${PIDS} 2>/dev/null || true
sleep 1

if lsof -ti ":${NSFLOW_PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Force stopping..."
  lsof -ti ":${NSFLOW_PORT}" -sTCP:LISTEN | xargs kill -9 2>/dev/null || true
fi

echo "NSFlow port ${NSFLOW_PORT} is free."
