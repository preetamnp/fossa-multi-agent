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

export PYTHONPATH="${ROOT}/neuro-san/coded_tools/fossa_remediation:${ROOT}"
export AGENT_MANIFEST_FILE="${ROOT}/neuro-san/registries/manifest.hocon"
export AGENT_TOOL_PATH="${ROOT}/neuro-san/coded_tools/fossa_remediation"
export AGENT_LLM_INFO_FILE="${ROOT}/neuro-san/registries/mistral_llm_info.hocon"

if [[ -n "${MISTRAL_API_KEY:-}" ]]; then
  export OPENAI_API_KEY="${MISTRAL_API_KEY}"
fi

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "ERROR: Set MISTRAL_API_KEY in .env before running the POC."
  exit 1
fi

PROMPT="${1:-Remediate FOSSA vulnerabilities for payment-service. Call remediation_pipeline and return the draft PR URL.}"

source .venv/bin/activate

echo "Sending prompt to fossa_remediation agent network (live progress below)..."
if [[ "${REMEDIATION_DRY_RUN:-true}" =~ ^(0|false|no|off)$ ]]; then
  echo "Mode: production — FOSSA verify required (0 security vulns before PR; licensing ignored; ~15 min)"
else
  echo "Mode: POC dry run (FOSSA verify skipped — set REMEDIATION_DRY_RUN=false for green Security Analysis)"
fi
if [[ "${REMEDIATION_OSV_LOOKUP_ENABLED:-false}" =~ ^(1|true|yes|on)$ ]]; then
  echo "Fix source: FOSSA + OSV/Maven lookup"
else
  echo "Fix source: FOSSA-first (OSV fallback for NO_SAFE_VERSION only)"
fi
echo "Prompt: ${PROMPT}"
echo ""
echo "If the LLM refuses to call tools, use the deterministic fallback:"
echo "  python scripts/run_deterministic_poc.py"
echo ""

# Pass llm_config in sly_data so nested agents inherit the Mistral API key from the client request.
SLY_DATA="$(python "${ROOT}/scripts/build_sly_data.py")"

python scripts/run_poc_client.py \
  --prompt "${PROMPT}" \
  --sly_data "${SLY_DATA}"
