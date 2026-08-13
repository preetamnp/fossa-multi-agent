"""Summarize remediation outcomes for the PR author agent."""

from __future__ import annotations

import json
from typing import Any

from neuro_san.interfaces.coded_tool import CodedTool


class SummarizeRemediationForPR(CodedTool):
    """Return structured facts the PR author agent uses to write title/body."""

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> Any:
        repo_name = args.get("repo_name")
        if not repo_name:
            return "repo_name is required."

        findings = [f for f in (sly_data.get("fossa_findings") or []) if f.get("repo") == repo_name]
        fixes = (sly_data.get("dependency_fixes") or {}).get(repo_name) or []
        verify = (sly_data.get("fossa_verify") or {}).get(repo_name) or {}
        meta = (sly_data.get("remediation_plan_meta") or {}).get(repo_name) or {}
        branch = (sly_data.get("repo_branches") or {}).get(repo_name)
        test_result = (sly_data.get("test_results") or {}).get(repo_name) or {}
        compile_result = (sly_data.get("compile_results") or {}).get(repo_name) or {}

        payload = {
            "repo_name": repo_name,
            "branch": branch,
            "strategy_summary": meta.get("strategy_summary"),
            "deferred_issue_ids": meta.get("deferred_issue_ids") or [],
            "findings_count": len(findings),
            "vulnerabilities": [
                {
                    "cve": item.get("cve"),
                    "severity": item.get("severity"),
                    "package": item.get("package"),
                }
                for item in findings
                if item.get("category") == "vulnerability"
            ],
            "licensing": [
                {
                    "license": item.get("license"),
                    "package": item.get("package"),
                }
                for item in findings
                if item.get("category") == "licensing"
            ],
            "changes_applied": fixes,
            "compile_passed": bool(compile_result.get("passed")),
            "tests_passed": bool(test_result.get("passed")),
            "fossa_verify_passed": bool(verify.get("passed")),
            "fossa_revision": verify.get("revision"),
        }

        sly_data.setdefault("pr_summary", {})[repo_name] = payload
        return (
            f"PR summary for {repo_name} (pass to SubmitPullRequestBody, then CreatePullRequest):\n"
            + json.dumps(payload, indent=2)
        )
