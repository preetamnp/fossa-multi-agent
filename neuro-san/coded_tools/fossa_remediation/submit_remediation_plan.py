"""Accept structured remediation plans from the LLM strategist agent."""

from __future__ import annotations

import json
from typing import Any

from neuro_san.interfaces.coded_tool import CodedTool

from plan_validation import normalize_action


class SubmitRemediationPlan(CodedTool):
    """Store a candidate remediation or test-fix plan for validation."""

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> Any:
        repo_name = args.get("repo_name")
        if not repo_name:
            return "repo_name is required."

        raw_actions = args.get("actions")
        if raw_actions is None:
            return "actions is required (JSON array of bump_version/remove/replace objects)."

        if isinstance(raw_actions, str):
            try:
                raw_actions = json.loads(raw_actions)
            except json.JSONDecodeError as exc:
                return f"actions must be valid JSON array: {exc}"

        if not isinstance(raw_actions, list) or not raw_actions:
            return "actions must be a non-empty JSON array."

        plan_type = (args.get("plan_type") or "remediation").strip().lower()
        if plan_type not in {"remediation", "test_fix"}:
            return "plan_type must be 'remediation' or 'test_fix'."

        normalized = [normalize_action(item) for item in raw_actions if isinstance(item, dict)]
        if not normalized:
            return "No valid action objects found in actions array."

        deferred = args.get("deferred_issue_ids") or []
        if isinstance(deferred, str):
            try:
                deferred = json.loads(deferred)
            except json.JSONDecodeError:
                deferred = [deferred]
        deferred = [str(item) for item in deferred if item is not None and str(item).strip()]

        pending = {
            "plan_type": plan_type,
            "actions": normalized,
            "strategy_summary": args.get("strategy_summary") or "",
            "deferred_issue_ids": deferred,
        }
        sly_data.setdefault("pending_plan", {})[repo_name] = pending

        lines = [
            f"Stored pending {plan_type} plan for {repo_name} with {len(normalized)} action(s).",
            "Call ValidateRemediationPlan next.",
        ]
        if pending["strategy_summary"]:
            lines.append(f"Strategy: {pending['strategy_summary'][:500]}")
        return "\n".join(lines)
