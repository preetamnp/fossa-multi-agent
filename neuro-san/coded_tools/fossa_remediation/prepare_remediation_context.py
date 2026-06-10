"""Gather FOSSA findings, baseline plan, and build context for the remediation strategist agent."""

from __future__ import annotations

import json
from typing import Any

from neuro_san.interfaces.coded_tool import CodedTool

from _config import is_osv_lookup_enabled
from plan_remediation import PlanRemediationActions


class PrepareRemediationContext(CodedTool):
    """Package findings + rule-based baseline suggestions for LLM remediation planning."""

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> Any:
        repo_name = args.get("repo_name")
        if not repo_name:
            return "repo_name is required."

        findings = [
            item for item in (sly_data.get("fossa_findings") or []) if item.get("repo") == repo_name
        ]
        if not findings:
            return f"No FOSSA findings for {repo_name}. Run FetchFossaFindings first."

        baseline_tool = PlanRemediationActions()
        baseline_text = await baseline_tool.async_invoke(
            {"repo_name": repo_name, "baseline_only": True},
            sly_data,
        )
        baseline_actions = list((sly_data.get("remediation_plan_baseline") or {}).get(repo_name) or [])

        summary_findings = []
        for item in findings:
            summary_findings.append(
                {
                    "issue_id": item.get("issue_id"),
                    "category": item.get("category"),
                    "severity": item.get("severity"),
                    "cve": item.get("cve"),
                    "license": item.get("license"),
                    "package": item.get("package"),
                    "group_id": item.get("group_id"),
                    "artifact_id": item.get("artifact_id"),
                    "current_version": item.get("current_version"),
                    "recommended_version": item.get("recommended_version"),
                    "remediation_notes": item.get("remediation_notes"),
                }
            )

        context = {
            "repo_name": repo_name,
            "findings": summary_findings,
            "baseline_actions": baseline_actions,
            "lookup_fixes": sly_data.get("lookup_fixes") or {},
        }
        sly_data.setdefault("remediation_context", {})[repo_name] = context

        lines = [
            f"Remediation context for {repo_name}:",
            f"- {len(findings)} FOSSA issue(s)",
            f"- {len(baseline_actions)} baseline action(s) from FOSSA rules (reference only)",
            "",
            "Findings (JSON):",
            json.dumps(summary_findings, indent=2),
            "",
            "Baseline suggested actions (you may improve/reject/defer with rationale):",
            baseline_text,
            "",
            (
                "Next: read pom/dependency tree if needed, call LookupVulnerabilityFix for gaps, "
                "then SubmitRemediationPlan followed by ValidateRemediationPlan."
                if is_osv_lookup_enabled(sly_data)
                else "Next: use FOSSA completeFix/partialFix/recommended_version per finding; "
                "for NO_SAFE_VERSION call LookupVulnerabilityFix (OSV fallback), then SubmitRemediationPlan."
            ),
        ]
        return "\n".join(lines)
