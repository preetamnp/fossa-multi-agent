"""Load pilot repo configuration into sly_data for downstream agents."""

from __future__ import annotations

from typing import Any

from neuro_san.interfaces.coded_tool import CodedTool

from _config import (
    ensure_llm_config_in_sly_data,
    ensure_remediation_mode_in_sly_data,
    is_osv_lookup_enabled,
    load_repos_config,
)


class LoadRepoConfig(CodedTool):
    """Expose configured pilot repos (names, FOSSA locators, build commands)."""

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> Any:
        ensure_llm_config_in_sly_data(sly_data)
        ensure_remediation_mode_in_sly_data(sly_data)
        repos = load_repos_config()
        sly_data["pilot_repos"] = repos
        osv = is_osv_lookup_enabled(sly_data)
        lines = [
            "Configured pilot repositories:",
            (
                f"Remediation mode: FOSSA fixes + OSV for all packages."
                if osv
                else "Remediation mode: FOSSA-first (OSV fallback only when FOSSA reports NO_SAFE_VERSION)."
            ),
        ]
        for repo in repos:
            lines.append(
                f"- {repo['name']}: FOSSA={repo['fossa']['project_locator']} "
                f"GitHub={repo['github']['org']}/{repo['github']['repo']}"
            )
        return "\n".join(lines)
