"""Apply dependency changes from a FOSSA-derived remediation plan (no hardcoded versions)."""

from __future__ import annotations

import re
from typing import Any

from neuro_san.interfaces.coded_tool import CodedTool

from _config import get_repo_by_name
from lookup_fix import parse_maven_coordinate
from remediation_log import report_progress
from workspace import default_build_filename, require_workspace, resolve_relative_path, store_tool_result


class ApplyDependencyFix(CodedTool):
    """Apply bump/remove/replace actions produced by PlanRemediationActions."""

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> Any:
        repo_name = args.get("repo_name")
        ws, error = require_workspace(sly_data, repo_name)
        if error:
            return error
        assert ws is not None

        repo = get_repo_by_name(repo_name)
        if repo is None:
            return f"Unknown repo_name: {repo_name}"

        if args.get("apply_test_fixes"):
            plan = list((sly_data.get("suggested_test_fixes") or {}).get(repo_name) or [])
        else:
            plan = list((sly_data.get("remediation_plan") or {}).get(repo_name) or [])

        if args.get("action") and args.get("artifact_id"):
            plan.append(
                {
                    "action": args.get("action"),
                    "group_id": args.get("group_id") or "",
                    "artifact_id": args.get("artifact_id"),
                    "target_version": args.get("target_version"),
                    "replacement_coordinate": args.get("replacement_coordinate"),
                    "source": "agent",
                    "reason": args.get("reason") or "agent-directed test fix",
                    "category": "test_fix",
                }
            )

        if not plan:
            return (
                f"No remediation actions for {repo_name}. "
                "Run PlanRemediationActions, DiagnoseTestFailures, or pass action/artifact_id/target_version."
            )

        await report_progress(
            args,
            phase="Apply fixes",
            detail=f"{len(plan)} action(s) in {repo_name}",
        )

        root = ws.root
        build_tool = ws.build_tool
        actions: list[str] = []

        if build_tool == "maven":
            pom_rel = ws.dependency_files[0] if ws.dependency_files else default_build_filename(build_tool)
            pom, pom_error = resolve_relative_path(root, pom_rel)
            if pom_error or pom is None:
                return pom_error or f"{pom_rel} path invalid"
            if not pom.exists():
                return f"{pom_rel} not found in workspace for {repo_name}"
            content = pom.read_text(encoding="utf-8")
            updated = content
            for item in plan:
                updated, note = self._apply_maven_action(updated, item)
                if note:
                    actions.append(note)
            if updated != content:
                pom.write_text(updated, encoding="utf-8")
        elif build_tool == "gradle":
            gradle_rel = ws.dependency_files[0] if ws.dependency_files else default_build_filename(build_tool)
            gradle, gradle_error = resolve_relative_path(root, gradle_rel)
            if gradle_error or gradle is None:
                return gradle_error or f"{gradle_rel} path invalid"
            if not gradle.exists():
                return f"{gradle_rel} not found in workspace for {repo_name}"
            content = gradle.read_text(encoding="utf-8")
            updated = content
            for item in plan:
                updated, note = self._apply_gradle_action(updated, item)
                if note:
                    actions.append(note)
            if updated != content:
                gradle.write_text(updated, encoding="utf-8")
        else:
            return f"Unsupported build tool: {build_tool}"

        if not actions:
            return f"No dependency changes applied for {repo_name}. Plan may already be satisfied."

        sly_data.setdefault("dependency_fixes", {})[repo_name] = actions
        store_tool_result(
            sly_data,
            repo_name,
            "ApplyDependencyFix",
            {
                "tool": "ApplyDependencyFix",
                "repo_name": repo_name,
                "ok": True,
                "phase": "apply_fix",
                "changes": actions,
            },
        )
        return f"Applied {len(actions)} planned change(s) in {repo_name}: " + "; ".join(actions)

    def _apply_maven_action(self, content: str, item: dict[str, Any]) -> tuple[str, str | None]:
        action = item.get("action")
        group_id = item.get("group_id") or ""
        artifact_id = item.get("artifact_id") or ""
        if not artifact_id:
            return content, None

        if action == "bump_version":
            target = item.get("target_version")
            if not target:
                return content, None
            updated, count = self._bump_maven_artifact(content, artifact_id, str(target))
            if count:
                return updated, f"bump {group_id}:{artifact_id}->{target} ({item.get('source')})"
            return content, None

        if action == "remove":
            if not group_id:
                return content, None
            updated, removed = self._remove_maven_dependency(content, group_id, artifact_id)
            if removed:
                return updated, f"remove {group_id}:{artifact_id} ({item.get('source')})"
            return content, None

        if action == "replace":
            replacement = item.get("replacement_coordinate") or item.get("replacement")
            if not replacement:
                return content, None
            xml = self._coordinate_to_maven_xml(str(replacement))
            updated, replaced = self._replace_maven_dependency(content, artifact_id, xml)
            if replaced:
                return updated, f"replace {artifact_id} with {replacement} ({item.get('source')})"
            return content, None

        return content, None

    def _apply_gradle_action(self, content: str, item: dict[str, Any]) -> tuple[str, str | None]:
        action = item.get("action")
        group_id = item.get("group_id") or ""
        artifact_id = item.get("artifact_id") or ""
        coordinate_prefix = f"{group_id}:{artifact_id}" if group_id else artifact_id

        if action == "bump_version":
            target = item.get("target_version")
            if not target or not coordinate_prefix:
                return content, None
            pattern = rf"{re.escape(coordinate_prefix)}:[^'\n]+"
            replacement = f"{coordinate_prefix}:{target}"
            updated, count = re.subn(pattern, replacement, content)
            if count:
                return updated, f"bump {coordinate_prefix}->{target} ({item.get('source')})"
            return content, None

        if action == "remove":
            pattern = rf"^\s*implementation\s+['\"]{re.escape(coordinate_prefix)}:[^'\"]+['\"]\s*\n"
            updated, count = re.subn(pattern, "", content, flags=re.MULTILINE)
            if count:
                return updated, f"remove {coordinate_prefix} ({item.get('source')})"
            return content, None

        if action == "replace":
            replacement = item.get("replacement_coordinate") or item.get("replacement")
            if not replacement:
                return content, None
            pattern = rf"(['\"]){re.escape(coordinate_prefix)}:[^'\"]+(['\"])"
            updated, count = re.subn(pattern, rf"\g<1>{replacement}\g<2>", content)
            if count:
                return updated, f"replace {coordinate_prefix} with {replacement} ({item.get('source')})"
            return content, None

        return content, None

    @staticmethod
    def _coordinate_to_maven_xml(coordinate: str) -> str:
        parts = coordinate.split(":")
        if len(parts) >= 3:
            group_id, artifact_id, version = parts[0], parts[1], parts[2]
        elif len(parts) == 2:
            group_id, artifact_id, version = parts[0], parts[1], "LATEST"
        else:
            return coordinate
        return f"""<dependency>
            <groupId>{group_id}</groupId>
            <artifactId>{artifact_id}</artifactId>
            <version>{version}</version>
        </dependency>"""

    @staticmethod
    def _bump_maven_artifact(content: str, artifact: str, version: str) -> tuple[str, int]:
        pattern = (
            rf"(<dependency>\s*"
            rf"(?:.*?\n\s*)*?"
            rf"<artifactId>{re.escape(artifact)}</artifactId>\s*\n\s*"
            rf"<version>)([^<]+)(</version>)"
        )
        return re.subn(pattern, rf"\g<1>{version}\g<3>", content, count=1, flags=re.DOTALL)

    @staticmethod
    def _dependency_blocks(content: str) -> list[str]:
        pattern = re.compile(r"(<dependency>\s*.*?\s*</dependency>)", re.DOTALL)
        return [match.group(1) for match in pattern.finditer(content)]

    @staticmethod
    def _dependency_matches(block: str, group_id: str | None, artifact_id: str) -> bool:
        if group_id and not re.search(rf"<groupId>{re.escape(group_id)}</groupId>", block):
            return False
        return bool(re.search(rf"<artifactId>{re.escape(artifact_id)}</artifactId>", block))

    def _remove_maven_dependency(self, content: str, group_id: str, artifact_id: str) -> tuple[str, bool]:
        updated = content
        for block in self._dependency_blocks(content):
            if not self._dependency_matches(block, group_id, artifact_id):
                continue
            comment_pattern = rf"(?:\s*<!--[^\n]*-->\s*)?{re.escape(block)}\s*\n?"
            new_updated, count = re.subn(comment_pattern, "", updated, count=1, flags=re.DOTALL)
            if count:
                return new_updated, True
        return content, False

    def _replace_maven_dependency(self, content: str, artifact_id: str, replacement_xml: str) -> tuple[str, bool]:
        updated = content
        for block in self._dependency_blocks(content):
            if not self._dependency_matches(block, None, artifact_id):
                continue
            comment_pattern = rf"(?:\s*<!--[^\n]*-->\s*)?{re.escape(block)}\s*\n?"
            replacement = f"\n        {replacement_xml.strip()}\n"
            new_updated, count = re.subn(comment_pattern, replacement, updated, count=1, flags=re.DOTALL)
            if count:
                return new_updated, True
        return content, False
