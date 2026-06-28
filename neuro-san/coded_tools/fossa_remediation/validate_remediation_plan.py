"""Validate LLM remediation plans before ApplyDependencyFix runs."""

from __future__ import annotations

from typing import Any

from neuro_san.interfaces.coded_tool import CodedTool

from _config import (
    MAX_PLAN_VALIDATION_ATTEMPTS,
    increment_plan_validation_attempts,
    plan_validation_attempts,
    reset_plan_validation_attempts,
)
from plan_validation import validate_plan


class ValidateRemediationPlan(CodedTool):
    """Enforce policy: versions must trace to FOSSA/OSV/Maven lookups; critical/high CVEs covered."""

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> Any:
        repo_name = args.get("repo_name")
        if not repo_name:
            return "repo_name is required."

        if plan_validation_attempts(sly_data, repo_name) >= MAX_PLAN_VALIDATION_ATTEMPTS:
            return (
                f"Plan validation retry limit reached for {repo_name} "
                f"({MAX_PLAN_VALIDATION_ATTEMPTS} failed attempts). "
                "Escalate to human review; do not resubmit without revisiting findings."
            )

        pending = (sly_data.get("pending_plan") or {}).get(repo_name)
        if not pending:
            return f"No pending plan for {repo_name}. Call SubmitRemediationPlan first."

        plan_type = pending.get("plan_type") or "remediation"
        try:
            actions, errors = await validate_plan(
                repo_name,
                pending.get("actions") or [],
                sly_data,
                plan_type=plan_type,
                deferred_issue_ids=pending.get("deferred_issue_ids"),
            )
        except Exception as exc:
            detail = str(exc).strip() or repr(exc)
            return f"Plan validation ERROR for {repo_name}: {type(exc).__name__}: {detail}"

        if errors:
            attempt = increment_plan_validation_attempts(sly_data, repo_name)
            sly_data.setdefault("plan_validation_errors", {})[repo_name] = errors
            remaining = max(MAX_PLAN_VALIDATION_ATTEMPTS - attempt, 0)
            if attempt >= MAX_PLAN_VALIDATION_ATTEMPTS:
                return (
                    f"Plan validation FAILED for {repo_name} ({len(errors)} issue(s)) — "
                    f"retry limit reached ({MAX_PLAN_VALIDATION_ATTEMPTS} attempts).\n"
                    + "\n".join(f"- {err}" for err in errors)
                    + "\n\nEscalate to human review; do not open PR."
                )
            return (
                f"Plan validation FAILED for {repo_name} ({len(errors)} issue(s); "
                f"attempt {attempt}/{MAX_PLAN_VALIDATION_ATTEMPTS}, {remaining} retry(s) left):\n"
                + "\n".join(f"- {err}" for err in errors)
                + "\n\nRevise the plan and call SubmitRemediationPlan again, then ValidateRemediationPlan."
            )

        if plan_type == "test_fix":
            sly_data.setdefault("suggested_test_fixes", {})[repo_name] = actions
        else:
            sly_data.setdefault("remediation_plan", {})[repo_name] = actions
            sly_data.setdefault("remediation_plan_meta", {})[repo_name] = {
                "strategy_summary": pending.get("strategy_summary") or "",
                "deferred_issue_ids": pending.get("deferred_issue_ids") or [],
            }

        reset_plan_validation_attempts(sly_data, repo_name)
        sly_data.get("pending_plan", {}).pop(repo_name, None)
        sly_data.get("plan_validation_errors", {}).pop(repo_name, None)

        lines = [f"Plan validation PASSED for {repo_name} ({plan_type}): {len(actions)} action(s)."]
        for action in actions:
            if action.get("action") == "bump_version":
                lines.append(
                    f"- bump {action.get('group_id')}:{action.get('artifact_id')} "
                    f"-> {action.get('target_version')} ({action.get('reason')})"
                )
            elif action.get("action") == "remove":
                lines.append(f"- remove {action.get('group_id')}:{action.get('artifact_id')}")
            elif action.get("action") == "replace":
                lines.append(
                    f"- replace {action.get('artifact_id')} with {action.get('replacement_coordinate')}"
                )
        return "\n".join(lines)
