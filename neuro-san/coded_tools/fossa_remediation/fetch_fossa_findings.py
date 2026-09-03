"""Fetch security and license issues from FOSSA for configured pilot repos."""

from __future__ import annotations

from typing import Any

import httpx

from neuro_san.interfaces.coded_tool import CodedTool

from _config import fossa_base_url, fossa_headers, get_repo_by_name, load_repos_config, FossaRevisionNotFound
from fossa_api import normalize_git_sha
from lookup_fix import fossa_remediation_version, parse_fossa_source, parse_maven_coordinate


class FetchFossaFindings(CodedTool):
    """Query FOSSA v2 Issues API for vulnerabilities and licensing policy violations."""

    DEFAULT_CATEGORIES = ("vulnerability", "licensing")

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> Any:
        repo_name = args.get("repo_name")
        severity = args.get("severity") or ["critical", "high", "medium"]
        # Never let the LLM truncate below the default — partial findings cause
        # incomplete plans (e.g. missing SnakeYAML) and broken Spring Boot tests.
        requested = args.get("max_count")
        try:
            max_count = int(requested) if requested is not None else 50
        except (TypeError, ValueError):
            max_count = 50
        max_count = max(max_count, 50)
        categories = args.get("categories") or list(self.DEFAULT_CATEGORIES)

        repos = [get_repo_by_name(repo_name)] if repo_name else load_repos_config()
        repos = [r for r in repos if r is not None]

        all_findings: list[dict[str, Any]] = []

        async with httpx.AsyncClient(timeout=60.0) as client:
            for repo in repos:
                for category in categories:
                    per_category_limit = max_count if len(categories) == 1 else max(max_count // 2, 5)
                    findings = await self.fetch_issues(
                        client,
                        repo,
                        category=category,
                        severity=severity,
                        max_count=per_category_limit,
                    )
                    all_findings.extend(findings)

        sly_data["fossa_findings"] = all_findings
        if not all_findings:
            return "No FOSSA vulnerability or licensing issues found for configured repos."

        vuln_count = sum(1 for item in all_findings if item.get("category") == "vulnerability")
        license_count = sum(1 for item in all_findings if item.get("category") == "licensing")

        lines = [
            f"Found {len(all_findings)} FOSSA issue(s): "
            f"{vuln_count} vulnerability, {license_count} licensing."
        ]
        for item in all_findings:
            rec = item.get("recommended_version")
            rec_text = f" recommended={rec}" if rec else ""
            notes = item.get("remediation_notes")
            notes_text = f" notes={notes[:80]}..." if notes and len(notes) > 80 else (f" notes={notes}" if notes else "")
            if item.get("category") == "licensing":
                lines.append(
                    f"- [{item['repo']}] [license] {item.get('license', 'unknown-license')} "
                    f"package={item.get('package', 'n/a')} severity={item.get('severity', 'n/a')}"
                    f"{rec_text}{notes_text}"
                )
            else:
                lines.append(
                    f"- [{item['repo']}] [vuln] {item.get('cve', 'unknown-cve')} "
                    f"package={item.get('package', 'n/a')} "
                    f"current={item.get('current_version', 'n/a')} severity={item.get('severity', 'n/a')}"
                    f"{rec_text}{notes_text}"
                )
        return "\n".join(lines)

    async def fetch_issues(
        self,
        client: httpx.AsyncClient,
        repo: dict[str, Any],
        *,
        category: str,
        severity: list[str],
        max_count: int,
        revision: str | None = None,
    ) -> list[dict[str, Any]]:
        return await self._fetch_repo_issues(client, repo, category, severity, max_count, revision)

    async def _fetch_repo_issues(
        self,
        client: httpx.AsyncClient,
        repo: dict[str, Any],
        category: str,
        severity: list[str],
        max_count: int,
        revision: str | None = None,
    ) -> list[dict[str, Any]]:
        project_locator = repo["fossa"]["project_locator"]
        params: list[tuple[str, str]] = [
            ("category", category),
            ("scope[type]", "project"),
            ("scope[id]", project_locator),
            ("count", str(max_count)),
        ]
        if revision:
            params.append(("scope[revision]", normalize_git_sha(revision)))
        if category == "vulnerability":
            for index, level in enumerate(severity):
                params.append((f"filter[severity][{index}]", level))

        response = await client.get(
            f"{fossa_base_url()}/v2/issues",
            headers=fossa_headers(),
            params=params,
        )
        if response.status_code == 404 and revision:
            raise FossaRevisionNotFound(revision)
        response.raise_for_status()
        payload = response.json()
        issues = payload.get("issues", [])
        if not isinstance(issues, list):
            issues = []

        findings: list[dict[str, Any]] = []
        for issue in issues[:max_count]:
            findings.append(self._normalize_issue(repo["name"], category, issue))
        return findings

    @staticmethod
    def _normalize_issue(repo_name: str, category: str, issue: dict[str, Any]) -> dict[str, Any]:
        vuln = issue.get("vulnerability") or issue.get("vuln") or {}
        source = issue.get("source") or {}
        dependency = issue.get("dependency") or issue.get("package") or {}
        remediation = issue.get("remediation") or {}
        license_info = issue.get("license") or issue.get("licenses") or {}

        license_name = issue.get("licenseName") or issue.get("license_name")
        if not license_name and isinstance(license_info, dict):
            license_name = license_info.get("name") or license_info.get("id")
        if not license_name and isinstance(license_info, list) and license_info:
            first = license_info[0]
            if isinstance(first, dict):
                license_name = first.get("name") or first.get("id")
            else:
                license_name = str(first)

        group_id, artifact_id, source_version = parse_fossa_source(source if isinstance(source, dict) else None)
        if not group_id:
            group_id, artifact_id, source_version = parse_maven_coordinate(
                source.get("name") or dependency.get("name") or issue.get("packageName") or "",
                source.get("version") or dependency.get("version") or issue.get("version"),
            )

        recommended = fossa_remediation_version(remediation if isinstance(remediation, dict) else None)

        return {
            "repo": repo_name,
            "category": category,
            "issue_id": issue.get("id") or issue.get("issueId"),
            "cve": issue.get("cve") or vuln.get("cve") or issue.get("vulnId"),
            "license": license_name,
            "severity": issue.get("severity") or vuln.get("severity") or issue.get("priority"),
            "package": source.get("name") or dependency.get("name") or issue.get("packageName"),
            "group_id": group_id,
            "artifact_id": artifact_id,
            "current_version": source_version or source.get("version") or dependency.get("version") or issue.get("version"),
            "recommended_version": recommended,
            "remediation_notes": remediation.get("notes") or remediation.get("description") if isinstance(remediation, dict) else None,
            "title": issue.get("title") or vuln.get("title") or issue.get("issueTitle"),
            "raw": issue,
        }


class FetchRemediationGuidance(CodedTool):
    """Fetch FOSSA remediation guidance report (JSON) for a project revision."""

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> Any:
        repo_name = args.get("repo_name")
        if not repo_name:
            return "repo_name is required."

        repo = get_repo_by_name(repo_name)
        if repo is None:
            return f"Unknown repo_name: {repo_name}"

        from urllib.parse import quote

        locator = quote(repo["fossa"]["project_locator"], safe="")
        url = f"{fossa_base_url()}/revisions/{locator}/report/remediation-guidance"

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.get(
                url,
                headers=fossa_headers(),
                params={"format": "JSON", "excludeLowPriority": "true"},
            )
            if response.status_code == 403:
                return (
                    "Remediation Guidance API is not enabled for this FOSSA org. "
                    "Use FetchFossaFindings output and manual upgrade paths for the POC."
                )
            response.raise_for_status()

            content_type = response.headers.get("content-type", "")
            if "json" in content_type:
                guidance = response.json()
            else:
                guidance = {"note": "Non-JSON response received", "size_bytes": len(response.content)}

        key = f"remediation_guidance_{repo_name}"
        sly_data[key] = guidance
        quick_wins = guidance.get("quickWins") or guidance.get("quick_wins") or []
        return (
            f"Remediation guidance loaded for {repo_name}. "
            f"Quick wins sections: {len(quick_wins) if isinstance(quick_wins, list) else 'see sly_data'}."
        )
