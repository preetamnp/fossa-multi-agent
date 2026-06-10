"""Validate LLM-submitted remediation plans against FOSSA facts and public version sources."""

from __future__ import annotations

import re
from typing import Any

import httpx

from _config import artifacts_with_no_safe_version, is_no_safe_version, is_osv_lookup_enabled
from lookup_fix import fossa_remediation_version, parse_fossa_source, parse_maven_coordinate


ALLOWED_ACTIONS = frozenset({"bump_version", "remove", "replace"})


def version_sort_key(value: str) -> tuple:
    parts = re.split(r"[.\-]", value)
    key: list[Any] = []
    for part in parts:
        key.append(int(part) if part.isdigit() else part)
    return tuple(key)


def normalize_action(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize LLM action fields to the shape ApplyDependencyFix expects."""
    action = (raw.get("action") or "").strip().lower()
    group_id = (raw.get("group_id") or "").strip()
    artifact_id = (raw.get("artifact_id") or "").strip()
    package = (raw.get("package") or "").strip()

    if not artifact_id and package:
        group_id, artifact_id, _ = parse_maven_coordinate(package, raw.get("current_version"))

    return {
        "action": action,
        "group_id": group_id,
        "artifact_id": artifact_id,
        "current_version": raw.get("current_version"),
        "target_version": raw.get("target_version"),
        "replacement_coordinate": raw.get("replacement_coordinate") or raw.get("replacement"),
        "source": raw.get("source") or "agent",
        "reason": raw.get("reason") or raw.get("rationale") or raw.get("issue_id"),
        "issue_id": raw.get("issue_id"),
        "category": raw.get("category") or "vulnerability",
        "finding_ids": raw.get("finding_ids") or ([raw.get("issue_id")] if raw.get("issue_id") else []),
    }


def build_allowed_versions(sly_data: dict[str, Any], repo_name: str) -> dict[str, set[str]]:
    """Map artifact_id -> set of acceptable target versions from FOSSA + lookups + baseline."""
    allowed: dict[str, set[str]] = {}

    def add(artifact_id: str, version: str | None) -> None:
        if not artifact_id or not version or is_no_safe_version(str(version)):
            return
        allowed.setdefault(artifact_id, set()).add(str(version))

    for finding in sly_data.get("fossa_findings") or []:
        if finding.get("repo") != repo_name:
            continue
        raw = finding.get("raw") or {}
        remediation = raw.get("remediation") or {}
        _, artifact_id, _ = parse_fossa_source(raw.get("source") or {})
        if not artifact_id:
            _, artifact_id, _ = parse_maven_coordinate(finding.get("package") or "", finding.get("current_version"))

        add(artifact_id, finding.get("recommended_version"))
        add(artifact_id, fossa_remediation_version(remediation))
        add(artifact_id, remediation.get("partialFix"))
        add(artifact_id, remediation.get("completeFix"))

        vuln = raw.get("vulnerability") or raw.get("vuln") or {}
        fixed_in = vuln.get("fixedIn") or vuln.get("fixed_in")
        if isinstance(fixed_in, list):
            for item in fixed_in:
                add(artifact_id, str(item))
        elif fixed_in:
            add(artifact_id, str(fixed_in))

    osv_fallback_artifacts = artifacts_with_no_safe_version(sly_data, repo_name)
    for coordinate, lookup in (sly_data.get("lookup_fixes") or {}).items():
        artifact_id = lookup.get("artifact_id") or coordinate.split(":")[-1]
        if is_osv_lookup_enabled(sly_data) or artifact_id in osv_fallback_artifacts:
            add(artifact_id, lookup.get("target_version"))

    for action in (sly_data.get("remediation_plan_baseline") or {}).get(repo_name) or []:
        add(action.get("artifact_id") or "", action.get("target_version"))

    return allowed


def merge_bump_actions(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    index: dict[str, int] = {}

    for item in actions:
        key = f"{item.get('group_id')}:{item.get('artifact_id')}:{item.get('action')}"
        if item.get("action") == "bump_version" and key in index:
            existing = merged[index[key]]
            existing_ver = existing.get("target_version") or "0"
            incoming_ver = item.get("target_version") or "0"
            if version_sort_key(incoming_ver) > version_sort_key(existing_ver):
                merged[index[key]] = item
            continue
        index[key] = len(merged)
        merged.append(item)

    return merged


def best_complete_fix_per_artifact(sly_data: dict[str, Any], repo_name: str) -> dict[str, str]:
    """Highest FOSSA completeFix per artifact_id (security findings only)."""
    best: dict[str, str] = {}
    for finding in sly_data.get("fossa_findings") or []:
        if finding.get("repo") != repo_name or finding.get("category") != "vulnerability":
            continue
        raw = finding.get("raw") or {}
        remediation = raw.get("remediation") or {}
        complete = remediation.get("completeFix")
        if not complete or is_no_safe_version(str(complete)):
            continue
        _, artifact_id, _ = parse_fossa_source(raw.get("source") or {})
        if not artifact_id:
            _, artifact_id, _ = parse_maven_coordinate(finding.get("package") or "", finding.get("current_version"))
        if not artifact_id:
            continue
        current_best = best.get(artifact_id)
        if not current_best or version_sort_key(str(complete)) > version_sort_key(current_best):
            best[artifact_id] = str(complete)
    return best


def finding_issue_id(finding: dict[str, Any]) -> str:
    return str(finding.get("issue_id") or "")


def validate_deferred_issues(
    repo_name: str,
    deferred_issue_ids: list[str] | None,
    sly_data: dict[str, Any],
) -> list[str]:
    """Only licensing findings may be deferred; security vulns must be fixed."""
    errors: list[str] = []
    deferred = {str(item) for item in (deferred_issue_ids or []) if item is not None and str(item).strip()}
    if not deferred:
        return errors

    by_id: dict[str, dict[str, Any]] = {}
    for finding in sly_data.get("fossa_findings") or []:
        if finding.get("repo") != repo_name:
            continue
        issue_id = finding_issue_id(finding)
        if issue_id:
            by_id[issue_id] = finding

    for issue_id in deferred:
        finding = by_id.get(str(issue_id))
        if finding is None:
            errors.append(f"deferred_issue_id {issue_id} is not a known FOSSA finding for {repo_name}.")
            continue
        if finding.get("category") == "vulnerability":
            cve = finding.get("cve") or "CVE"
            pkg = finding.get("package") or finding.get("artifact_id") or "package"
            errors.append(
                f"Cannot defer vulnerability {issue_id} ({cve} on {pkg}). "
                "Add bump_version/remove/replace using FOSSA completeFix, or LookupVulnerabilityFix when NO_SAFE_VERSION."
            )
    return errors


async def maven_version_exists(group_id: str, artifact_id: str, version: str) -> bool | None:
    """Return True/False if Maven Central responds; None if the lookup timed out or failed."""
    if not group_id or not artifact_id or not version:
        return False
    url = "https://search.maven.org/solrsearch/select"
    params = {
        "q": f"g:{group_id} AND a:{artifact_id} AND v:{version}",
        "rows": 1,
        "wt": "json",
        "core": "gav",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params)
            if response.status_code != 200:
                return False
            docs = (response.json().get("response") or {}).get("docs") or []
        return len(docs) > 0
    except httpx.HTTPError:
        return None


async def validate_plan(
    repo_name: str,
    actions: list[dict[str, Any]],
    sly_data: dict[str, Any],
    *,
    plan_type: str = "remediation",
    deferred_issue_ids: list[str] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Return (normalized_actions, errors). Empty errors means valid."""
    errors: list[str] = []
    if not actions:
        return [], ["Plan has no actions."]

    normalized = merge_bump_actions([normalize_action(item) for item in actions])
    allowed_versions = build_allowed_versions(sly_data, repo_name)
    required_complete_fix = best_complete_fix_per_artifact(sly_data, repo_name)
    deferred = {str(item) for item in (deferred_issue_ids or []) if item is not None and str(item).strip()}
    errors.extend(validate_deferred_issues(repo_name, list(deferred), sly_data))

    for index, item in enumerate(normalized, start=1):
        action = item.get("action")
        artifact_id = item.get("artifact_id") or ""
        group_id = item.get("group_id") or ""

        if action not in ALLOWED_ACTIONS:
            errors.append(f"Action #{index}: unsupported action '{action}'.")
            continue
        if not artifact_id:
            errors.append(f"Action #{index}: artifact_id is required.")
            continue

        if action == "bump_version":
            target = item.get("target_version")
            if not target:
                errors.append(f"Action #{index}: bump_version requires target_version for {artifact_id}.")
                continue

            permitted = allowed_versions.get(artifact_id, set())
            if not permitted:
                hint = (
                    "Call LookupVulnerabilityFix or use a FOSSA completeFix/partialFix version."
                    if is_osv_lookup_enabled(sly_data)
                    else "Use FOSSA completeFix/partialFix, call LookupVulnerabilityFix if NO_SAFE_VERSION, or remove/replace."
                )
                errors.append(f"Action #{index}: no allowed target_version for {artifact_id}. {hint}")
            elif str(target) not in permitted:
                hint = (
                    "Call LookupVulnerabilityFix or use FOSSA completeFix/partialFix."
                    if is_osv_lookup_enabled(sly_data)
                    else "Use FOSSA fix versions; OSV lookup only when FOSSA reports NO_SAFE_VERSION."
                )
                errors.append(
                    f"Action #{index}: target_version {target} for {artifact_id} not in allowed set "
                    f"{sorted(permitted)}. {hint}"
                )

            current = item.get("current_version")
            if current and version_sort_key(str(target)) <= version_sort_key(str(current)):
                errors.append(
                    f"Action #{index}: target_version {target} must be newer than current {current}."
                )

            if group_id and str(target) not in permitted:
                maven_ok = await maven_version_exists(group_id, artifact_id, str(target))
                if maven_ok is False:
                    errors.append(
                        f"Action #{index}: {group_id}:{artifact_id}:{target} not found on Maven Central."
                    )
                elif maven_ok is None:
                    errors.append(
                        f"Action #{index}: could not verify {group_id}:{artifact_id}:{target} on Maven Central "
                        "(search.maven.org timed out). Retry validation or use a FOSSA completeFix version."
                    )

            min_complete = required_complete_fix.get(artifact_id)
            if min_complete and version_sort_key(str(target)) < version_sort_key(min_complete):
                errors.append(
                    f"Action #{index}: {artifact_id} target_version {target} is below FOSSA completeFix "
                    f"{min_complete}. Use completeFix (not partialFix) to clear all CVEs on this dependency."
                )

        if action == "remove" and not group_id:
            errors.append(f"Action #{index}: remove requires group_id for {artifact_id}.")

        if action == "replace" and not item.get("replacement_coordinate"):
            errors.append(f"Action #{index}: replace requires replacement_coordinate for {artifact_id}.")

    if plan_type == "remediation":
        findings = [
            item
            for item in (sly_data.get("fossa_findings") or [])
            if item.get("repo") == repo_name and item.get("category") == "vulnerability"
        ]
        addressed_artifacts: set[str] = set()
        addressed_issue_ids: set[str] = set()
        for item in normalized:
            if item.get("artifact_id"):
                addressed_artifacts.add(item.get("artifact_id"))
            for issue_id in item.get("finding_ids") or []:
                if issue_id:
                    addressed_issue_ids.add(str(issue_id))
            if item.get("issue_id"):
                addressed_issue_ids.add(str(item.get("issue_id")))

        for finding in findings:
            issue_id = finding_issue_id(finding)
            if issue_id and issue_id in deferred:
                continue
            raw = finding.get("raw") or {}
            _, artifact_id, _ = parse_fossa_source(raw.get("source") or {})
            if not artifact_id:
                _, artifact_id, _ = parse_maven_coordinate(finding.get("package") or "")

            covered = issue_id in addressed_issue_ids or (
                artifact_id and artifact_id in addressed_artifacts
            )
            if not covered:
                sev = finding.get("severity") or "unknown"
                errors.append(
                    f"Vulnerability finding {issue_id} ({finding.get('cve', 'CVE')}, {sev}) on {artifact_id} "
                    "has no action. All security findings must be fixed; only licensing may be deferred."
                )

    return normalized, errors
