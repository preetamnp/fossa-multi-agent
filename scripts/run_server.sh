#!/usr/bin/env bash
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
export AGENT_MANIFEST_FILE="${ROOT}/neuro-san/registries/manifest.hocon"
export AGENT_TOOL_PATH="${ROOT}/neuro-san/coded_tools/fossa_remediation"
export AGENT_LLM_INFO_FILE="${ROOT}/neuro-san/registries/mistral_llm_info.hocon"

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "ERROR: OPENAI_API_KEY is not set."
  echo "  Add DEEPSEEK_API_KEY to .env (recommended) or set OPENAI_API_KEY directly."
  echo "  cp .env.example .env  # then edit with your DeepSeek key"
  exit 1
fi

mkdir -p logs

PORT="${AGENT_HTTP_PORT:-8080}"
HEALTH_URL="http://localhost:${PORT}/api/v1/fossa_remediation/function"

_server_has_api_key() {
  local pid="$1"
  ps eww "${pid}" 2>/dev/null | tr ' ' '\n' | grep -q '^OPENAI_API_KEY=.'
}

if lsof -ti ":${PORT}" >/dev/null 2>&1; then
  SERVER_PID="$(lsof -ti ":${PORT}" | head -1)"
  if curl -sf "${HEALTH_URL}" >/dev/null 2>&1; then
    if _server_has_api_key "${SERVER_PID}"; then
      echo "Neuro SAN is already running on port ${PORT}."
      echo "  Health: ${HEALTH_URL} OK"
      echo "  Run the POC in another terminal: ./scripts/run_poc.sh"
      echo "  To restart: ./scripts/stop_server.sh && ./scripts/run_server.sh"
      exit 0
    fi
    echo "Neuro SAN is running on port ${PORT} but OPENAI_API_KEY is missing from the server process."
    echo "  This causes remediation_strategist / test_healer / pr_author to fail."
    echo "  Restarting is required: ./scripts/stop_server.sh && ./scripts/run_server.sh"
    exit 1
  fi
  echo "Port ${PORT} is in use but agent health check failed."
  echo "Free the port or run: ./scripts/stop_server.sh"
  exit 1
fi

echo "Starting Neuro SAN server on port ${PORT}..."
echo "  AGENT_MANIFEST_FILE=${AGENT_MANIFEST_FILE}"
echo "  AGENT_TOOL_PATH=${AGENT_TOOL_PATH}"
echo "  OPENAI_API_KEY is set (DeepSeek/Mistral OpenAI client enabled)"

source .venv/bin/activate
python -m neuro_san.service.main_loop.server_main_loop 2>&1 | tee logs/server.log
