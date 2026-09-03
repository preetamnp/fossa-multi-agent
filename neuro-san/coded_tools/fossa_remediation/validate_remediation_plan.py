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
from remediation_policy import classify_actions, human_required_mode, load_remediation_policy


class ValidateRemediationPlan(CodedTool):
    """Enforce policy: versions, CVE coverage, and human-approval / breaking-change gates."""

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

        policy = load_remediation_policy()
        auto_actions, human_actions = classify_actions(actions, policy)
        mode = human_required_mode(policy)

        # Mode B (hold_and_report): only auto-safe actions go to ApplyDependencyFix.
        # fail_run: humans already caused validation errors above; surviving plans are all auto.
        apply_actions = auto_actions
        if mode == "fail_run":
            apply_actions = actions
            human_actions = []

        escalated_ids: list[str] = []
        for item in human_actions:
            if item.get("issue_id"):
                escalated_ids.append(str(item["issue_id"]))
            for finding_id in item.get("finding_ids") or []:
                if finding_id:
                    escalated_ids.append(str(finding_id))
        escalated_ids = sorted(set(escalated_ids))

        if plan_type == "test_fix":
            # Test-heal: still block human_required from auto-apply.
            sly_data.setdefault("suggested_test_fixes", {})[repo_name] = apply_actions
            sly_data.setdefault("human_review_queue", {})[repo_name] = human_actions
        else:
            sly_data.setdefault("remediation_plan", {})[repo_name] = apply_actions
            sly_data.setdefault("human_review_queue", {})[repo_name] = human_actions
            sly_data.setdefault("remediation_plan_meta", {})[repo_name] = {
                "strategy_summary": pending.get("strategy_summary") or "",
                "deferred_issue_ids": pending.get("deferred_issue_ids") or [],
                "escalated_issue_ids": escalated_ids,
                "policy_mode": mode,
                "auto_action_count": len(apply_actions),
                "human_action_count": len(human_actions),
            }

        reset_plan_validation_attempts(sly_data, repo_name)
        sly_data.get("pending_plan", {}).pop(repo_name, None)
        sly_data.get("plan_validation_errors", {}).pop(repo_name, None)

        lines = [
            f"Plan validation PASSED for {repo_name} ({plan_type}): "
            f"{len(apply_actions)} auto-apply action(s), {len(human_actions)} require human approval."
        ]
        for action in apply_actions:
            lines.append(self._format_action(action, prefix="AUTO"))
        for action in human_actions:
            lines.append(self._format_action(action, prefix="HUMAN"))
        if human_actions:
            lines.append(
                "Do NOT call ApplyDependencyFix for HUMAN items — they are in human_review_queue. "
                "Continue ApplyDependencyFix for AUTO actions only, then ship draft PR and report escalations."
            )
        if not apply_actions and human_actions:
            lines.append(
                "No auto-safe actions. Skip ApplyDependencyFix / PR unless humans approve the queue. "
                "Report human_review_queue and escalate."
            )
        return "\n".join(lines)

    @staticmethod
    def _format_action(action: dict[str, Any], *, prefix: str) -> str:
        risk_note = action.get("risk_reason") or ""
        suffix = f" [{risk_note}]" if risk_note and prefix == "HUMAN" else ""
        if action.get("action") == "bump_version":
            return (
                f"- [{prefix}] bump {action.get('group_id')}:{action.get('artifact_id')} "
                f"-> {action.get('target_version')} ({action.get('reason')}){suffix}"
            )
        if action.get("action") == "remove":
            return f"- [{prefix}] remove {action.get('group_id')}:{action.get('artifact_id')}{suffix}"
        if action.get("action") == "replace":
            return (
                f"- [{prefix}] replace {action.get('artifact_id')} with "
                f"{action.get('replacement_coordinate')}{suffix}"
            )
        return f"- [{prefix}] {action}"
