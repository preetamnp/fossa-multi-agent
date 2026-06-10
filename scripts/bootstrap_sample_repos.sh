#!/usr/bin/env bash
# Create GitHub repos from sample-repos/, generate build wrappers, and push.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

GITHUB_ORG="${GITHUB_ORG:-${GITHUB_USERNAME:-}}"
if [[ -z "$GITHUB_ORG" ]]; then
  if command -v gh >/dev/null 2>&1; then
    GITHUB_ORG="$(gh api user -q .login 2>/dev/null || true)"
  fi
fi

if [[ -z "$GITHUB_ORG" ]]; then
  echo "Set GITHUB_ORG to your GitHub username or org, e.g.:"
  echo "  export GITHUB_ORG=your-username"
  exit 1
fi

echo "Using GitHub org/user: $GITHUB_ORG"
echo ""

bootstrap_repo() {
  local name="$1"
  local dir="$ROOT/sample-repos/$name"

  echo "=== Bootstrapping $name ==="
  cd "$dir"

  if [[ "$name" == "payment-service" ]]; then
    if [[ ! -f mvnw ]]; then
      if command -v mvn >/dev/null 2>&1; then
        mvn -q -N wrapper:wrapper -Dmaven=3.9.9
        chmod +x mvnw
      else
        echo "WARN: Maven not installed — install Maven or run 'mvn wrapper:wrapper' later"
      fi
    fi
  fi

  if [[ "$name" == "user-service" ]]; then
    if [[ ! -f gradlew ]]; then
      if command -v gradle >/dev/null 2>&1; then
        gradle wrapper --gradle-version 8.10.2
        chmod +x gradlew
      elif [[ -f "$ROOT/sample-repos/user-service/gradlew" ]]; then
        chmod +x gradlew
      else
        echo "WARN: Gradle not installed — install Gradle or run 'gradle wrapper' later"
      fi
    fi
  fi

  if [[ ! -d .git ]]; then
    git init
    git checkout -b main 2>/dev/null || git branch -M main
  fi

  git add .
  if ! git diff --cached --quiet; then
    git commit -m "Initial commit: FOSSA POC $name with intentional vulnerable deps"
  fi

  if command -v gh >/dev/null 2>&1; then
    if ! gh repo view "$GITHUB_ORG/$name" >/dev/null 2>&1; then
      gh repo create "$GITHUB_ORG/$name" --public --source=. --remote=origin --push \
        --description "FOSSA multi-agent POC sample ($name) — intentional vulns for demo"
    else
      git remote remove origin 2>/dev/null || true
      git remote add origin "https://github.com/$GITHUB_ORG/$name.git"
      git push -u origin main
    fi
  else
    echo ""
    echo "gh CLI not found. Create repo manually:"
    echo "  https://github.com/new → $name"
    echo "  git remote add origin https://github.com/$GITHUB_ORG/$name.git"
    echo "  git push -u origin main"
  fi

  echo ""
}

bootstrap_repo payment-service
bootstrap_repo user-service

echo "=== Done ==="
echo ""
echo "Next steps:"
echo "  1. Import both repos in FOSSA: https://app.fossa.com (Add Project → GitHub)"
echo "  2. Wait for analysis to complete"
echo "  3. Run: python scripts/fetch_fossa_locators.py"
echo "  4. Update config/repos.yaml (or use --write flag)"
echo ""
echo "Full guide: docs/FOSSA_SETUP.md"
