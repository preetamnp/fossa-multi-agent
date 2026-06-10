"""Diagnose test failures and suggest dependency fixes (dynamic, no hardcoded versions)."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from neuro_san.interfaces.coded_tool import CodedTool

from _config import is_osv_lookup_enabled
from lookup_fix import LookupVulnerabilityFix, parse_maven_coordinate


class DiagnoseTestFailures(CodedTool):
    """Parse test/build output and surefire reports; suggest fixes via pom inspection + OSV/Maven lookup."""

    MAX_ATTEMPTS = 3

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> Any:
        repo_name = args.get("repo_name")
        repo_path = (sly_data.get("repo_paths") or {}).get(repo_name)
        if not repo_path:
            return f"No cloned repo found for {repo_name}. Run GitCloneAndBranch and RunJavaTests first."

        test_result = (sly_data.get("test_results") or {}).get(repo_name)
        if not test_result:
            return f"No test_results for {repo_name}. Run RunJavaTests first."

        if test_result.get("returncode") == 0:
            return f"Tests already passed for {repo_name}. No diagnosis needed."

        attempt = int((sly_data.get("test_fix_attempts") or {}).get(repo_name, 0)) + 1
        sly_data.setdefault("test_fix_attempts", {})[repo_name] = attempt

        if attempt > self.MAX_ATTEMPTS:
            return (
                f"Test self-heal limit reached ({self.MAX_ATTEMPTS} attempts) for {repo_name}. "
                "Escalate to human review; do not open PR."
            )

        log_text = self._collect_log_text(repo_path, test_result)
        errors = self._extract_errors(log_text)
        surefire = self._parse_surefire_reports(repo_path)
        pom_deps = self._read_pom_dependencies(repo_path)

        lookup = LookupVulnerabilityFix()
        suggested: list[dict[str, Any]] = []
        lines = [
            f"Test failure diagnosis for {repo_name} (attempt {attempt}/{self.MAX_ATTEMPTS}):",
            "",
            "### Errors detected",
        ]

        if not errors and not surefire:
            lines.append("- Could not parse specific errors. Review build log tail below.")
            lines.append("")
            lines.append("```")
            lines.append(log_text[-2500:])
            lines.append("```")
        else:
            for err in errors[:8]:
                lines.append(f"- {err['summary']}")
            for case in surefire[:5]:
                lines.append(f"- Test `{case['name']}`: {case['message'][:200]}")

        lines.extend(["", "### Suggested fixes (dynamic)"])

        for err in errors:
            fix = await self._suggest_fix_for_error(err, pom_deps, lookup, sly_data, repo_path)
            if fix and not self._action_in_list(fix, suggested):
                suggested.append(fix)
                lines.append(
                    f"- {fix['action']} {fix.get('group_id')}:{fix.get('artifact_id')} "
                    f"-> {fix.get('target_version') or fix.get('replacement_coordinate')} "
                    f"({fix.get('reason')})"
                )

        if not suggested:
            if is_osv_lookup_enabled(sly_data):
                lines.append(
                    "- No automatic dependency fix inferred. Inspect log, then call LookupVulnerabilityFix "
                    "for the failing package and ApplyDependencyFix with action/group_id/artifact_id/target_version."
                )
            else:
                lines.append(
                    "- No automatic dependency fix inferred. OSV lookup is disabled — use FOSSA fix versions "
                    "from PrepareRemediationContext or adjust the plan manually."
                )

        sly_data.setdefault("suggested_test_fixes", {})[repo_name] = suggested
        sly_data.setdefault("test_failure_diagnosis", {})[repo_name] = {
            "attempt": attempt,
            "errors": errors,
            "surefire": surefire,
            "suggested_count": len(suggested),
        }

        lines.extend(
            [
                "",
                "### Next steps for agent",
                "1. Reason about the errors above.",
                "2. Call ApplyDependencyFix with apply_test_fixes=true OR pass action/group_id/artifact_id/target_version.",
                "3. Call RunJavaTests again.",
                "4. Repeat up to 3 times; only GitCommitAndPush + CreatePullRequest after tests pass.",
            ]
        )
        return "\n".join(lines)

    @staticmethod
    def _collect_log_text(repo_path: str, test_result: dict[str, Any]) -> str:
        parts = [
            test_result.get("stdout_tail") or "",
            test_result.get("stderr_tail") or "",
        ]
        log_path = Path(repo_path) / "target" / "maven-build.log"
        if log_path.exists():
            parts.append(log_path.read_text(encoding="utf-8", errors="replace")[-8000:])
        return "\n".join(parts)

    @staticmethod
    def _extract_errors(log_text: str) -> list[dict[str, Any]]:
        errors: list[dict[str, Any]] = []
        patterns = [
            (r"ClassNotFoundException:\s*([^\s\n]+)", "missing_class"),
            (r"NoClassDefFoundError:\s*([^\s\n]+)", "missing_class"),
            (r"NoSuchMethodError:\s*([^\s\n]+)", "binary_incompat"),
            (r"Could not resolve dependencies[^\n]*", "dependency_resolution"),
            (r"Failed to execute goal[^\n]*", "maven_goal_failure"),
            (r"compilation failure[^\n]*", "compile_failure"),
            (r"TagInspector", "snakeyaml_incompat"),
            (r"snakeyaml", "snakeyaml_issue"),
        ]
        for pattern, kind in patterns:
            for match in re.finditer(pattern, log_text, re.IGNORECASE):
                errors.append(
                    {
                        "kind": kind,
                        "match": match.group(0)[:300],
                        "class_or_token": match.group(1) if match.lastindex else match.group(0),
                        "summary": match.group(0)[:200],
                    }
                )
        return errors

    @staticmethod
    def _parse_surefire_reports(repo_path: str) -> list[dict[str, str]]:
        reports_dir = Path(repo_path) / "target" / "surefire-reports"
        if not reports_dir.exists():
            return []

        cases: list[dict[str, str]] = []
        for xml_path in reports_dir.glob("TEST-*.xml"):
            try:
                root = ET.parse(xml_path).getroot()
            except ET.ParseError:
                continue
            for case in root.findall(".//testcase"):
                failure = case.find("failure") or case.find("error")
                if failure is None:
                    continue
                cases.append(
                    {
                        "name": case.get("name") or xml_path.name,
                        "message": (failure.get("message") or failure.text or "")[:500],
                    }
                )
        return cases

    @staticmethod
    def _read_pom_dependencies(repo_path: str) -> list[dict[str, str]]:
        pom = Path(repo_path) / "pom.xml"
        if not pom.exists():
            return []

        deps: list[dict[str, str]] = []
        for block in re.findall(r"<dependency>.*?</dependency>", pom.read_text(encoding="utf-8"), re.DOTALL):
            group = re.search(r"<groupId>([^<]+)</groupId>", block)
            artifact = re.search(r"<artifactId>([^<]+)</artifactId>", block)
            version = re.search(r"<version>([^<]+)</version>", block)
            if artifact:
                deps.append(
                    {
                        "group_id": group.group(1).strip() if group else "",
                        "artifact_id": artifact.group(1).strip(),
                        "version": version.group(1).strip() if version else "",
                    }
                )
        return deps

    async def _suggest_fix_for_error(
        self,
        err: dict[str, Any],
        pom_deps: list[dict[str, str]],
        lookup: LookupVulnerabilityFix,
        sly_data: dict[str, Any],
        repo_path: str,
    ) -> dict[str, Any] | None:
        kind = err.get("kind")

        if kind in {"snakeyaml_incompat", "snakeyaml_issue"}:
            return await self._bump_pom_artifact(pom_deps, "snakeyaml", lookup, sly_data, "Spring Boot requires snakeyaml 2.x")

        if kind == "missing_class":
            class_name = str(err.get("class_or_token") or "")
            artifact = self._artifact_from_class(class_name, pom_deps)
            if artifact:
                return await self._bump_pom_artifact(
                    pom_deps, artifact["artifact_id"], lookup, sly_data,
                    f"classpath missing {class_name}",
                    group_id=artifact.get("group_id"),
                )

        if kind in {"binary_incompat", "dependency_resolution", "maven_goal_failure"}:
            for dep in pom_deps:
                fix = await self._bump_pom_artifact(
                    pom_deps, dep["artifact_id"], lookup, sly_data,
                    f"possible incompatible {dep['group_id']}:{dep['artifact_id']}",
                    group_id=dep.get("group_id"),
                )
                if fix:
                    return fix

        return None

    async def _bump_pom_artifact(
        self,
        pom_deps: list[dict[str, str]],
        artifact_id: str,
        lookup: LookupVulnerabilityFix,
        sly_data: dict[str, Any],
        reason: str,
        group_id: str | None = None,
    ) -> dict[str, Any] | None:
        dep = next((d for d in pom_deps if d["artifact_id"] == artifact_id), None)
        if dep:
            group_id = group_id or dep.get("group_id") or ""
            current = dep.get("version") or ""
        else:
            current = ""

        if not is_osv_lookup_enabled(sly_data):
            return None

        coordinate = f"{group_id}:{artifact_id}" if group_id else artifact_id
        await lookup.async_invoke({"package": coordinate, "current_version": current}, sly_data)
        result = (sly_data.get("lookup_fixes") or {}).get(coordinate)
        if not result or not result.get("target_version"):
            return None

        target = str(result["target_version"])
        if current and target == current:
            return None

        return {
            "action": "bump_version",
            "group_id": result.get("group_id") or group_id,
            "artifact_id": artifact_id,
            "current_version": current,
            "target_version": target,
            "source": result.get("source", "test-diagnosis"),
            "reason": reason,
            "category": "test_fix",
        }

    @staticmethod
    def _artifact_from_class(class_name: str, pom_deps: list[dict[str, str]]) -> dict[str, str] | None:
        lower = class_name.lower()
        for dep in pom_deps:
            aid = dep["artifact_id"].replace("-", "").lower()
            if aid and aid in lower.replace(".", "").replace("_", ""):
                return dep
        if "snakeyaml" in lower or "yaml" in lower:
            dep = next((d for d in pom_deps if d["artifact_id"] == "snakeyaml"), None)
            if dep:
                return dep
        return None

    @staticmethod
    def _action_in_list(action: dict[str, Any], actions: list[dict[str, Any]]) -> bool:
        for item in actions:
            if (
                item.get("action") == action.get("action")
                and item.get("artifact_id") == action.get("artifact_id")
                and item.get("target_version") == action.get("target_version")
            ):
                return True
        return False
