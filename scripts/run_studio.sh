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

export PYTHONPATH="${ROOT}/neuro-san/coded_tools/fossa_remediation:${ROOT}"
export NEURO_SAN_SERVER_HOST="${NEURO_SAN_SERVER_HOST:-localhost}"
export NEURO_SAN_SERVER_CONNECTION="${NEURO_SAN_SERVER_CONNECTION:-http}"

SERVER_PORT="${AGENT_HTTP_PORT:-8080}"
export NEURO_SAN_SERVER_HTTP_PORT="${SERVER_PORT}"
NSFLOW_PORT="${NSFLOW_PORT:-4173}"
HEALTH_URL="http://localhost:${SERVER_PORT}/api/v1/fossa_remediation/function"
SLY_DATA_FILE="${ROOT}/logs/nsflow_sly_data.json"

if [[ -n "${MISTRAL_API_KEY:-}" ]]; then
  export OPENAI_API_KEY="${MISTRAL_API_KEY}"
fi

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "ERROR: Set MISTRAL_API_KEY in .env before opening Studio."
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

python - <<'PY' > "${SLY_DATA_FILE}"
import json
import os

dry_run = os.environ.get("REMEDIATION_DRY_RUN", "true").strip().lower() not in {"0", "false", "no", "off"}
osv_lookup = os.environ.get("REMEDIATION_OSV_LOOKUP_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}

print(
    json.dumps(
        {
            "dry_run": dry_run,
            "osv_lookup_enabled": osv_lookup,
            "llm_config": {
                "openai_api_key": os.environ["OPENAI_API_KEY"],
                "openai_api_base": os.environ.get("OPENAI_API_BASE", "https://api.mistral.ai/v1"),
            },
        },
        indent=2,
    )
)
PY

if lsof -ti ":${NSFLOW_PORT}" >/dev/null 2>&1; then
  echo "NSFlow UI already running on http://localhost:${NSFLOW_PORT}/"
else
  echo "Starting NSFlow on http://localhost:${NSFLOW_PORT}/ ..."
fi

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
echo "   This sets dry_run, osv_lookup, and Mistral llm_config (required)."
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
