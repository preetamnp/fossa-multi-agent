"""Build a remediation plan from FOSSA findings and public fix lookups (no static version map)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from neuro_san.interfaces.coded_tool import CodedTool

from _config import allows_osv_lookup, is_no_safe_version
from lookup_fix import LookupVulnerabilityFix, fossa_remediation_version, parse_fossa_source, parse_maven_coordinate


class PlanRemediationActions(CodedTool):
    """Turn FOSSA scan results into concrete dependency actions using FOSSA hints + OSV/Maven lookup."""

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> Any:
        repo_name = args.get("repo_name")
        findings = [
            item
            for item in (sly_data.get("fossa_findings") or [])
            if not repo_name or item.get("repo") == repo_name
        ]

        if not findings:
            return f"No FOSSA findings in sly_data for {repo_name or 'configured repos'}. Run FetchFossaFindings first."

        repo_path = (sly_data.get("repo_paths") or {}).get(repo_name) if repo_name else None
        lookup = LookupVulnerabilityFix()
        actions: list[dict[str, Any]] = []
        seen_keys: set[str] = set()

        for finding in findings:
            planned = await self._plan_for_finding(finding, lookup, sly_data, repo_path)
            if not planned:
                continue
            key = self._action_key(planned)
            if key in seen_keys:
                self._merge_bump_action(actions, planned)
                continue
            seen_keys.add(key)
            actions.append(planned)

        if repo_name:
            key = "remediation_plan_baseline" if args.get("baseline_only") else "remediation_plan"
            sly_data.setdefault(key, {})[repo_name] = actions
        else:
            key = "remediation_plan_baseline" if args.get("baseline_only") else "remediation_plan"
            sly_data[key] = {findings[0].get("repo", "unknown"): actions}

        if not actions:
            return (
                f"Could not derive automated remediation actions for {repo_name}. "
                "Call LookupVulnerabilityFix for individual packages, then PlanRemediationActions again."
            )

        lines = [f"Planned {len(actions)} remediation action(s) for {repo_name}:"]
        for action in actions:
            lines.append(self._format_action(action))
        return "\n".join(lines)

    async def _plan_for_finding(
        self,
        finding: dict[str, Any],
        lookup: LookupVulnerabilityFix,
        sly_data: dict[str, Any],
        repo_path: str | None,
    ) -> dict[str, Any] | None:
        category = finding.get("category") or "vulnerability"
        package = finding.get("package") or ""
        current_version = finding.get("current_version")
        group_id = finding.get("group_id") or ""
        artifact_id = finding.get("artifact_id") or ""
        raw_source = (finding.get("raw") or {}).get("source") or {}
        if not group_id or not artifact_id or " " in artifact_id:
            parsed_group, parsed_artifact, parsed_version = parse_fossa_source(raw_source)
            group_id = group_id or parsed_group
            artifact_id = parsed_artifact or artifact_id
            current_version = current_version or parsed_version

        if not artifact_id:
            _, artifact_id, current_version = parse_maven_coordinate(package, current_version)
        if not group_id and ":" in package:
            group_id, artifact_id, current_version = parse_maven_coordinate(package, current_version)
        if not group_id and artifact_id and repo_path:
            group_id = self._find_group_in_pom(repo_path, artifact_id) or group_id

        fossa_action, target_version, replacement = self._extract_fossa_remediation(finding)

        if category == "licensing":
            if fossa_action == "replace" and replacement:
                return self._action(
                    "replace",
                    group_id,
                    artifact_id,
                    current_version,
                    finding,
                    category,
                    replacement_coordinate=replacement,
                    source="fossa",
                )
            if fossa_action == "remove" and group_id and artifact_id:
                return self._action(
                    "remove",
                    group_id,
                    artifact_id,
                    current_version,
                    finding,
                    category,
                    source="fossa",
                )
            return None

        if target_version and is_no_safe_version(str(target_version)):
            target_version = None

        if target_version:
            return self._action(
                "bump_version",
                group_id,
                artifact_id,
                current_version,
                finding,
                category,
                target_version=str(target_version),
                source="fossa",
            )

        coordinate = f"{group_id}:{artifact_id}" if group_id else artifact_id
        if not coordinate:
            return None

        if not allows_osv_lookup(sly_data, finding=finding, package=coordinate, cve=finding.get("cve")):
            return None

        await lookup.async_invoke(
            {
                "package": coordinate,
                "current_version": current_version,
                "cve": finding.get("cve"),
                "no_safe_version_fallback": True,
            },
            sly_data,
        )
        lookup_result = (sly_data.get("lookup_fixes") or {}).get(coordinate)
        if not lookup_result:
            return None

        return self._action(
            "bump_version",
            lookup_result.get("group_id") or group_id,
            lookup_result.get("artifact_id") or artifact_id,
            current_version,
            finding,
            category,
            target_version=str(lookup_result.get("target_version")),
            source=lookup_result.get("source", "lookup"),
            reason=lookup_result.get("reason"),
        )

    @staticmethod
    def _action(
        action: str,
        group_id: str,
        artifact_id: str,
        current_version: str | None,
        finding: dict[str, Any],
        category: str,
        *,
        target_version: str | None = None,
        replacement_coordinate: str | None = None,
        source: str = "fossa",
        reason: str | None = None,
    ) -> dict[str, Any]:
        return {
            "action": action,
            "group_id": group_id,
            "artifact_id": artifact_id,
            "current_version": current_version,
            "target_version": target_version,
            "replacement_coordinate": replacement_coordinate,
            "source": source,
            "reason": reason or finding.get("cve") or finding.get("license") or finding.get("title"),
            "issue_id": finding.get("issue_id"),
            "category": category,
        }

    @staticmethod
    def _find_group_in_pom(repo_path: str, artifact_id: str) -> str | None:
        pom = Path(repo_path) / "pom.xml"
        if not pom.exists():
            return None
        pattern = re.compile(
            rf"<dependency>\s*.*?<groupId>(?P<group>[^<]+)</groupId>\s*"
            rf".*?<artifactId>{re.escape(artifact_id)}</artifactId>\s*.*?</dependency>",
            re.DOTALL,
        )
        match = pattern.search(pom.read_text(encoding="utf-8"))
        return match.group("group").strip() if match else None

    @staticmethod
    def _merge_bump_action(actions: list[dict[str, Any]], planned: dict[str, Any]) -> None:
        if planned.get("action") != "bump_version":
            return
        for action in actions:
            if (
                action.get("action") == "bump_version"
                and action.get("artifact_id") == planned.get("artifact_id")
                and action.get("group_id") == planned.get("group_id")
            ):
                existing = action.get("target_version") or "0"
                incoming = planned.get("target_version") or "0"
                if incoming > existing:
                    action["target_version"] = incoming
                return

    @staticmethod
    def _extract_fossa_remediation(finding: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
        raw = finding.get("raw") or {}
        remediation = raw.get("remediation") or {}
        vuln = raw.get("vulnerability") or raw.get("vuln") or {}

        target_version = (
            finding.get("recommended_version")
            or fossa_remediation_version(remediation)
            or remediation.get("version")
            or remediation.get("recommendedVersion")
            or remediation.get("targetVersion")
        )
        fixed_in = vuln.get("fixedIn") or vuln.get("fixed_in")
        if not target_version and isinstance(fixed_in, list) and fixed_in:
            target_version = str(fixed_in[0])
        elif not target_version and isinstance(fixed_in, str):
            target_version = fixed_in

        action_hint = (remediation.get("action") or remediation.get("type") or "").lower()
        replacement = remediation.get("replacement") or remediation.get("replacementPackage")

        notes = remediation.get("notes") or remediation.get("description") or ""
        if not action_hint and "remove" in notes.lower():
            action_hint = "remove"
        if not action_hint and "replace" in notes.lower():
            action_hint = "replace"

        if finding.get("category") == "licensing" and not action_hint:
            action_hint = None

        return action_hint or None, str(target_version) if target_version else None, replacement

    @staticmethod
    def _action_key(action: dict[str, Any]) -> str:
        return (
            f"{action.get('action')}:{action.get('group_id')}:{action.get('artifact_id')}:"
            f"{action.get('target_version')}:{action.get('replacement_coordinate')}"
        )

    @staticmethod
    def _format_action(action: dict[str, Any]) -> str:
        artifact = action.get("artifact_id") or "unknown"
        if action["action"] == "bump_version":
            return (
                f"- bump {artifact} {action.get('current_version')} -> {action.get('target_version')} "
                f"({action.get('source')}: {action.get('reason')})"
            )
        if action["action"] == "remove":
            return f"- remove {action.get('group_id')}:{artifact} ({action.get('reason')})"
        if action["action"] == "replace":
            return (
                f"- replace {artifact} with {action.get('replacement_coordinate')} "
                f"({action.get('reason')})"
            )
        return f"- {action}"
