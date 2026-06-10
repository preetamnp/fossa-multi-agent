"""Validate LLM remediation plans before ApplyDependencyFix runs."""

from __future__ import annotations

from typing import Any

from neuro_san.interfaces.coded_tool import CodedTool

from plan_validation import validate_plan


class ValidateRemediationPlan(CodedTool):
    """Enforce policy: versions must trace to FOSSA/OSV/Maven lookups; critical/high CVEs covered."""

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> Any:
        repo_name = args.get("repo_name")
        if not repo_name:
            return "repo_name is required."

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
            sly_data.setdefault("plan_validation_errors", {})[repo_name] = errors
            return (
                f"Plan validation FAILED for {repo_name} ({len(errors)} issue(s)):\n"
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
