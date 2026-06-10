#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ok=true

check() {
  local label="$1"
  local cmd="$2"
  if eval "$cmd" >/dev/null 2>&1; then
    echo "OK   $label"
  else
    echo "FAIL $label"
    ok=false
  fi
}

echo "=== FOSSA Multi-Agent POC — setup validation ==="
echo ""

check "Python 3.12+" "python3 -c 'import sys; assert sys.version_info >= (3, 12)'"
check "Virtual env" "test -d .venv"
check ".env file" "test -f .env"
check "repos.yaml" "test -f config/repos.yaml"
check "agent manifest" "test -f neuro-san/registries/manifest.hocon"
check "agent network" "test -f neuro-san/registries/fossa_remediation.hocon"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

[[ -n "${FOSSA_API_TOKEN:-}" ]] && echo "OK   FOSSA_API_TOKEN set" || { echo "WARN FOSSA_API_TOKEN missing"; ok=false; }
[[ -n "${MISTRAL_API_KEY:-}" ]] && echo "OK   MISTRAL_API_KEY set" || { echo "WARN MISTRAL_API_KEY missing"; ok=false; }
[[ -n "${GITHUB_TOKEN:-}" ]] && echo "OK   GITHUB_TOKEN set" || { echo "WARN GITHUB_TOKEN missing"; ok=false; }

check "git" "command -v git"
check "java" "command -v java"

if grep -qE "YOUR_ORG_ID|your-github-username|your-org" config/repos.yaml 2>/dev/null; then
  echo "WARN config/repos.yaml still has placeholders — run bootstrap + fetch_fossa_locators.py --write"
  ok=false
fi

echo ""
if $ok; then
  echo "All checks passed. Run scripts/dry_run_fossa.py then scripts/run_server.sh + scripts/run_poc.sh"
  exit 0
fi

echo "Fix warnings above before the leadership demo."
exit 1
