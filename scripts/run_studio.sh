#!/usr/bin/env bash
# Launch Neuro SAN Studio (NSFlow web UI) against the FOSSA remediation server.
#
# Usage (two terminals):
#   Terminal 1: ./scripts/run_server.sh
#   Terminal 2: ./scripts/run_studio.sh
#
# Then open http://localhost:4173 — see printed steps for Sly Data + chat prompt.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

# shellcheck disable=SC1091
source "${ROOT}/scripts/_llm_env.sh"

export PYTHONPATH="${ROOT}/neuro-san/coded_tools/fossa_remediation:${ROOT}"
export NEURO_SAN_SERVER_HOST="${NEURO_SAN_SERVER_HOST:-localhost}"
export NEURO_SAN_SERVER_CONNECTION="${NEURO_SAN_SERVER_CONNECTION:-http}"

SERVER_PORT="${AGENT_HTTP_PORT:-8080}"
export NEURO_SAN_SERVER_HTTP_PORT="${SERVER_PORT}"
NSFLOW_PORT="${NSFLOW_PORT:-4173}"
HEALTH_URL="http://localhost:${SERVER_PORT}/api/v1/fossa_remediation/function"
SLY_DATA_FILE="${ROOT}/logs/nsflow_sly_data.json"

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "ERROR: Set DEEPSEEK_API_KEY in .env before opening Studio."
  exit 1
fi

source .venv/bin/activate

if ! command -v ns >/dev/null 2>&1; then
  echo "ERROR: neuro-san-studio not installed."
  echo "  pip install neuro-san-studio"
  exit 1
fi

if ! curl -sf "${HEALTH_URL}" >/dev/null 2>&1; then
  echo "ERROR: Neuro SAN server is not reachable at ${HEALTH_URL}"
  echo "  Start it first: ./scripts/run_server.sh"
  exit 1
fi

mkdir -p logs

python "${ROOT}/scripts/build_sly_data.py" > "${SLY_DATA_FILE}"

NSFLOW_URL="http://localhost:${NSFLOW_PORT}/"
if lsof -ti ":${NSFLOW_PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
  if curl -sf --max-time 3 "${NSFLOW_URL}" >/dev/null 2>&1; then
    echo ""
    echo "NSFlow is already running at ${NSFLOW_URL}"
    echo "  Paste Sly Data from: ${SLY_DATA_FILE}"
    echo "  To restart the UI: ./scripts/stop_studio.sh && ./scripts/run_studio.sh"
    exit 0
  fi
  echo "Port ${NSFLOW_PORT} is in use but NSFlow is not responding."
  echo "  Freeing the port and starting a fresh NSFlow instance..."
  "${ROOT}/scripts/stop_studio.sh"
fi

echo "Starting NSFlow on ${NSFLOW_URL} ..."

echo ""
echo "══════════════════════════════════════════════════════════════"
echo " Run FOSSA remediation in the browser (localhost:${NSFLOW_PORT})"
echo "══════════════════════════════════════════════════════════════"
echo ""
echo "1. Open:  http://localhost:${NSFLOW_PORT}/"
echo ""
echo "2. Select agent network:  fossa_remediation"
echo "   (sidebar / network picker — must match manifest.hocon)"
echo ""
echo "3. Open the  Sly Data  tab and paste JSON from:"
echo "      ${SLY_DATA_FILE}"
echo "   This sets dry_run, osv_lookup, model_name, and DeepSeek llm_config (required for nested agents)."
echo ""
echo "4. Open the  Chat  tab and send, for example:"
echo '      Remediate all FOSSA security vulnerabilities for payment-service.'
echo '      License issues may be deferred.'
echo ""
echo "5. Watch progress in:"
echo "      • Internal Chat / Agent Communications  (tool calls live)"
echo "      • Agent Network Diagram                 (highlights active agents)"
echo "      • Sly Data                              (session state updates)"
echo ""
echo "Server: http://localhost:${SERVER_PORT}  |  Mode: REMEDIATION_DRY_RUN=${REMEDIATION_DRY_RUN:-true}"
echo ""
echo "Press Ctrl+C here to stop the UI (server keeps running in the other terminal)."
echo "══════════════════════════════════════════════════════════════"
echo ""

# NSFlow --client-only reads server host/port from NEURO_SAN_SERVER_* env vars above.
exec ns run \
  --client-only \
  --nsflow-port "${NSFLOW_PORT}" \
  --log-level info
