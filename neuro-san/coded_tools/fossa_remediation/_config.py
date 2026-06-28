"""Shared helpers for FOSSA remediation coded tools."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CONFIG_DIR = PROJECT_ROOT / "config"
WORK_DIR = Path(os.environ.get("FOSSA_WORK_DIR", PROJECT_ROOT / "work"))
_ENV_LOADED = False


class FossaRevisionNotFound(Exception):
    """FOSSA has not scanned this revision yet (API returns 404)."""


def default_fix_branch_name(repo_name: str) -> str:
    """Unique fix branch from main for each agent run."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"fix/fossa-auto-{repo_name}-{ts}"


def ensure_env_loaded() -> None:
    global _ENV_LOADED
    if _ENV_LOADED or load_dotenv is None:
        return
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=True)
    _ENV_LOADED = True


def load_repos_config() -> list[dict[str, Any]]:
    path = CONFIG_DIR / "repos.yaml"
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    return data.get("repos", [])


def get_repo_by_name(name: str) -> dict[str, Any] | None:
    for repo in load_repos_config():
        if repo.get("name") == name:
            return repo
    return None


def fossa_headers() -> dict[str, str]:
    ensure_env_loaded()
    token = (
        os.environ.get("FOSSA_API_TOKEN", "").strip()
        or os.environ.get("FOSSA_API_KEY", "").strip()
    )
    if not token:
        raise ValueError("FOSSA_API_TOKEN is not set. Copy .env.example to .env and add your token.")
    return {"Authorization": f"Bearer {token}"}


def fossa_base_url() -> str:
    ensure_env_loaded()
    return os.environ.get("FOSSA_API_BASE", "https://app.fossa.com/api").rstrip("/")


def github_headers() -> dict[str, str]:
    ensure_env_loaded()
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise ValueError("GITHUB_TOKEN is not set. Copy .env.example to .env and add your token.")
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def ensure_work_dir() -> Path:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    return WORK_DIR


def is_remediation_dry_run(sly_data: dict[str, Any] | None = None) -> bool:
    """POC/demo mode: skip FOSSA branch verify; production runs set REMEDIATION_DRY_RUN=false."""
    ensure_env_loaded()
    if sly_data is not None and "dry_run" in sly_data:
        return bool(sly_data["dry_run"])
    raw = os.environ.get("REMEDIATION_DRY_RUN", "true").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def is_no_safe_version(value: str | None) -> bool:
    """True when FOSSA reports no safe upgrade path for this dependency."""
    if not value:
        return False
    normalized = str(value).strip().upper().replace(" ", "_")
    return normalized in {"NO_SAFE_VERSION", "NO_SAFE_UPGRADE", "NONE", "N/A"}


def is_osv_lookup_enabled(sly_data: dict[str, Any] | None = None) -> bool:
    """When true, OSV/Maven lookup is allowed for any package (not just NO_SAFE_VERSION fallbacks)."""
    ensure_env_loaded()
    if sly_data is not None and "osv_lookup_enabled" in sly_data:
        return bool(sly_data["osv_lookup_enabled"])
    raw = os.environ.get("REMEDIATION_OSV_LOOKUP_ENABLED", "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def finding_has_no_safe_version(finding: dict[str, Any]) -> bool:
    """True when a FOSSA finding has no actionable fix version."""
    if is_no_safe_version(finding.get("recommended_version")):
        return True
    raw = finding.get("raw") or {}
    remediation = raw.get("remediation") or {}
    return is_no_safe_version(remediation.get("completeFix")) and is_no_safe_version(
        remediation.get("partialFix")
    )


def fossa_finding_needs_osv_fallback(
    sly_data: dict[str, Any],
    *,
    package: str | None = None,
    cve: str | None = None,
    artifact_id: str | None = None,
) -> bool:
    """True if any matching FOSSA finding in sly_data needs OSV because FOSSA has no safe version."""
    from lookup_fix import parse_fossa_source, parse_maven_coordinate

    for finding in sly_data.get("fossa_findings") or []:
        if cve and finding.get("cve") != cve:
            continue
        finding_artifact = finding.get("artifact_id") or ""
        if not finding_artifact:
            raw_source = (finding.get("raw") or {}).get("source") or {}
            _, finding_artifact, _ = parse_fossa_source(raw_source)
            if not finding_artifact:
                _, finding_artifact, _ = parse_maven_coordinate(
                    finding.get("package") or "", finding.get("current_version")
                )
        if artifact_id and finding_artifact and finding_artifact != artifact_id:
            continue
        if package:
            pkg = (finding.get("package") or "").lower()
            coord = package.lower()
            if coord not in pkg and pkg not in coord and finding_artifact not in coord:
                continue
        if finding_has_no_safe_version(finding):
            return True
    return False


def allows_osv_lookup(
    sly_data: dict[str, Any] | None,
    *,
    finding: dict[str, Any] | None = None,
    package: str | None = None,
    cve: str | None = None,
    artifact_id: str | None = None,
    no_safe_version_fallback: bool = False,
) -> bool:
    """FOSSA-first: OSV allowed when globally enabled or FOSSA says NO_SAFE_VERSION."""
    if is_osv_lookup_enabled(sly_data):
        return True
    if no_safe_version_fallback:
        return True
    if finding and finding_has_no_safe_version(finding):
        return True
    if sly_data and (package or cve or artifact_id):
        return fossa_finding_needs_osv_fallback(
            sly_data, package=package, cve=cve, artifact_id=artifact_id
        )
    return False


def artifacts_with_no_safe_version(sly_data: dict[str, Any], repo_name: str) -> set[str]:
    """Artifact IDs where FOSSA reported NO_SAFE_VERSION (OSV fallback permitted)."""
    from lookup_fix import parse_fossa_source, parse_maven_coordinate

    artifacts: set[str] = set()
    for finding in sly_data.get("fossa_findings") or []:
        if finding.get("repo") != repo_name:
            continue
        if not finding_has_no_safe_version(finding):
            continue
        artifact_id = finding.get("artifact_id") or ""
        if not artifact_id:
            raw_source = (finding.get("raw") or {}).get("source") or {}
            _, artifact_id, _ = parse_fossa_source(raw_source)
            if not artifact_id:
                _, artifact_id, _ = parse_maven_coordinate(
                    finding.get("package") or "", finding.get("current_version")
                )
        if artifact_id:
            artifacts.add(artifact_id)
    return artifacts


def ensure_remediation_mode_in_sly_data(sly_data: dict[str, Any]) -> None:
    """Expose dry_run and osv_lookup flags so coded tools and agents share the same mode."""
    if "dry_run" not in sly_data:
        sly_data["dry_run"] = is_remediation_dry_run(sly_data)
    if "osv_lookup_enabled" not in sly_data:
        sly_data["osv_lookup_enabled"] = is_osv_lookup_enabled(sly_data)


MAX_PLAN_VALIDATION_ATTEMPTS = 3
MAX_TEST_HEAL_ATTEMPTS = 3
DEFAULT_LLM_MODEL = "labs-devstral-small-2512"


def resolve_fix_branch_name(repo_name: str, args: dict[str, Any] | None = None) -> tuple[str, str | None]:
    """Return a unique fix branch name; ignore agent-supplied branch_name by default."""
    args = args or {}
    requested = (args.get("branch_name") or "").strip() or None
    allow_custom = os.environ.get("ALLOW_AGENT_BRANCH_NAME", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if allow_custom and requested:
        return requested, None

    fresh = args.get("fresh_branch")
    if fresh is None:
        fresh = os.environ.get("FOSSA_FRESH_BRANCH", "true").lower() in {"1", "true", "yes"}
    branch = default_fix_branch_name(repo_name) if fresh else f"fix/fossa-auto-{repo_name}"
    ignored = requested if requested and requested != branch else None
    return branch, ignored


def plan_validation_attempts(sly_data: dict[str, Any], repo_name: str) -> int:
    return int((sly_data.get("plan_validation_attempts") or {}).get(repo_name, 0))


def increment_plan_validation_attempts(sly_data: dict[str, Any], repo_name: str) -> int:
    attempts = plan_validation_attempts(sly_data, repo_name) + 1
    sly_data.setdefault("plan_validation_attempts", {})[repo_name] = attempts
    return attempts


def reset_plan_validation_attempts(sly_data: dict[str, Any], repo_name: str) -> None:
    sly_data.setdefault("plan_validation_attempts", {})[repo_name] = 0


def test_heal_attempts(sly_data: dict[str, Any], repo_name: str) -> int:
    return int((sly_data.get("test_fix_attempts") or {}).get(repo_name, 0))


def build_default_sly_data() -> dict[str, Any]:
    """Default session state for NSFlow and CLI clients (includes full llm_config)."""
    ensure_env_loaded()
    api_key = (
        os.environ.get("OPENAI_API_KEY", "").strip()
        or os.environ.get("MISTRAL_API_KEY", "").strip()
    )
    if not api_key:
        raise ValueError("OPENAI_API_KEY or MISTRAL_API_KEY must be set.")

    model_name = os.environ.get("REMEDIATION_LLM_MODEL", DEFAULT_LLM_MODEL).strip() or DEFAULT_LLM_MODEL
    api_base = os.environ.get("OPENAI_API_BASE", "").strip() or "https://api.mistral.ai/v1"

    return {
        "dry_run": is_remediation_dry_run(None),
        "osv_lookup_enabled": is_osv_lookup_enabled(None),
        "llm_config": {
            "model_name": model_name,
            "class": "openai",
            "openai_api_key": api_key,
            "openai_api_base": api_base,
            "temperature": 0.0,
        },
    }


def ensure_llm_config_in_sly_data(sly_data: dict[str, Any]) -> None:
    """Propagate Mistral/OpenAI credentials into sly_data for nested LLM agents."""
    ensure_env_loaded()
    llm_config = sly_data.setdefault("llm_config", {})
    api_key = (
        os.environ.get("OPENAI_API_KEY", "").strip()
        or os.environ.get("MISTRAL_API_KEY", "").strip()
    )
    if api_key and not llm_config.get("openai_api_key"):
        llm_config["openai_api_key"] = api_key
    api_base = os.environ.get("OPENAI_API_BASE", "").strip() or "https://api.mistral.ai/v1"
    if not llm_config.get("openai_api_base"):
        llm_config["openai_api_base"] = api_base
    if not llm_config.get("model_name"):
        llm_config["model_name"] = (
            os.environ.get("REMEDIATION_LLM_MODEL", DEFAULT_LLM_MODEL).strip() or DEFAULT_LLM_MODEL
        )
    if not llm_config.get("class"):
        llm_config["class"] = "openai"
    if "temperature" not in llm_config:
        llm_config["temperature"] = 0.0
