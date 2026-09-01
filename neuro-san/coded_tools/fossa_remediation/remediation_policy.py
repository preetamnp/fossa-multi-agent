"""Load remediation policy and classify actions as auto vs human_required."""

from __future__ import annotations

import fnmatch
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from _config import CONFIG_DIR

RISK_AUTO = "auto"
RISK_HUMAN = "human_required"
RISK_BLOCKED = "blocked"

MODE_HOLD = "hold_and_report"
MODE_FAIL = "fail_run"
MODE_SKIP = "skip_risky"


@lru_cache(maxsize=1)
def load_remediation_policy() -> dict[str, Any]:
    path = CONFIG_DIR / "remediation_policy.yaml"
    if not path.exists():
        return {
            "on_human_required": {"mode": MODE_HOLD},
            "breaking_change_rules": {
                "major_bump_requires_approval": True,
                "deny_remove_without_approval": True,
                "deny_replace_without_approval": True,
            },
            "require_human_approval": [],
            "auto_apply_allowed": [],
        }
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data


def clear_policy_cache() -> None:
    load_remediation_policy.cache_clear()


def human_required_mode(policy: dict[str, Any] | None = None) -> str:
    policy = policy or load_remediation_policy()
    mode = ((policy.get("on_human_required") or {}).get("mode") or MODE_HOLD).strip().lower()
    if mode == MODE_SKIP:
        return MODE_HOLD
    if mode not in {MODE_HOLD, MODE_FAIL}:
        return MODE_HOLD
    return mode


def coordinate_of(action: dict[str, Any]) -> str:
    group_id = (action.get("group_id") or "").strip()
    artifact_id = (action.get("artifact_id") or "").strip()
    if group_id and artifact_id:
        return f"{group_id}:{artifact_id}"
    return artifact_id


def parse_semver_major(version: str | None) -> int | None:
    if not version:
        return None
    match = re.match(r"^v?(\d+)", str(version).strip())
    if not match:
        return None
    return int(match.group(1))


def _matches_policy_entry(action: dict[str, Any], entry: dict[str, Any]) -> str | None:
    """Return reason if action matches a require_human_approval entry."""
    coord = coordinate_of(action)
    artifact_id = (action.get("artifact_id") or "").strip()
    reason = (entry.get("reason") or "policy require_human_approval").strip()

    exact = (entry.get("coordinate") or "").strip()
    if exact and coord == exact:
        return reason

    glob = (entry.get("artifact_glob") or "").strip()
    if glob and artifact_id and fnmatch.fnmatch(artifact_id, glob):
        return reason

    coord_glob = (entry.get("coordinate_glob") or "").strip()
    if coord_glob and coord and fnmatch.fnmatch(coord, coord_glob):
        return reason

    return None


def _allowlist_permits(action: dict[str, Any], allowlist: list[Any]) -> bool:
    if not allowlist:
        return True
    coord = coordinate_of(action)
    for entry in allowlist:
        if isinstance(entry, str) and entry.strip() == coord:
            return True
        if isinstance(entry, dict):
            exact = (entry.get("coordinate") or "").strip()
            if exact and exact == coord:
                return True
    return False


def classify_action(action: dict[str, Any], policy: dict[str, Any] | None = None) -> dict[str, Any]:
    """Annotate action with risk and risk_reason. Mutates a copy."""
    policy = policy or load_remediation_policy()
    item = dict(action)
    rules = policy.get("breaking_change_rules") or {}
    reasons: list[str] = []

    allowlist = policy.get("auto_apply_allowed") or []
    if allowlist and not _allowlist_permits(item, allowlist):
        reasons.append(f"not on auto_apply_allowed list ({coordinate_of(item)})")

    for entry in policy.get("require_human_approval") or []:
        if not isinstance(entry, dict):
            continue
        matched = _matches_policy_entry(item, entry)
        if matched:
            reasons.append(matched)

    action_type = (item.get("action") or "").strip().lower()
    if action_type == "remove" and rules.get("deny_remove_without_approval", True):
        reasons.append("remove requires human approval")
    if action_type == "replace" and rules.get("deny_replace_without_approval", True):
        reasons.append("replace requires human approval")

    if action_type == "bump_version" and rules.get("major_bump_requires_approval", True):
        current_major = parse_semver_major(item.get("current_version"))
        target_major = parse_semver_major(item.get("target_version"))
        if (
            current_major is not None
            and target_major is not None
            and target_major > current_major
        ):
            reasons.append(
                f"major version bump {item.get('current_version')} → {item.get('target_version')}"
            )

    if reasons:
        item["risk"] = RISK_HUMAN
        item["risk_reason"] = "; ".join(reasons)
    else:
        item["risk"] = RISK_AUTO
        item["risk_reason"] = ""

    return item


def classify_actions(
    actions: list[dict[str, Any]],
    policy: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (auto_actions, human_actions)."""
    policy = policy or load_remediation_policy()
    auto: list[dict[str, Any]] = []
    human: list[dict[str, Any]] = []
    for raw in actions:
        classified = classify_action(raw, policy)
        if classified.get("risk") == RISK_AUTO:
            auto.append(classified)
        else:
            human.append(classified)
    return auto, human


def is_human_required(action: dict[str, Any], policy: dict[str, Any] | None = None) -> bool:
    return classify_action(action, policy).get("risk") != RISK_AUTO


def policy_path() -> Path:
    return CONFIG_DIR / "remediation_policy.yaml"
