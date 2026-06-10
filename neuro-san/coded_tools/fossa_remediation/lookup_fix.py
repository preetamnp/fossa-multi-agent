"""Look up dependency fix versions from OSV and Maven metadata (no hardcoded versions)."""

from __future__ import annotations

import re
from typing import Any

import httpx

from neuro_san.interfaces.coded_tool import CodedTool

from _config import allows_osv_lookup


def parse_maven_coordinate(package: str, current_version: str | None = None) -> tuple[str, str, str | None]:
    """Parse FOSSA/OSV package strings into group_id, artifact_id, version."""
    text = (package or "").strip()
    version = current_version

    if "@" in text:
        text, _, pinned = text.partition("@")
        version = version or pinned.strip() or None

    if ":" in text:
        group_id, artifact_id = text.split(":", 1)
        return group_id.strip(), artifact_id.strip(), version

    artifact_id = text.split("/")[-1].strip() if text else ""
    return "", artifact_id, version


def parse_fossa_source(source: dict[str, Any] | None) -> tuple[str, str, str | None]:
    """Parse FOSSA issue source into Maven group_id, artifact_id, version.

    FOSSA source.id format: mvn+org.apache.commons:commons-text$1.9
    """
    if not source:
        return "", "", None

    source_id = str(source.get("id") or "")
    if source_id:
        text = source_id
        for prefix in ("mvn+", "npm+", "gem+", "go+"):
            if text.startswith(prefix):
                text = text[len(prefix) :]
                break
        if "$" in text:
            coord, version = text.rsplit("$", 1)
        else:
            coord, version = text, source.get("version")
        if ":" in coord:
            group_id, artifact_id = coord.split(":", 1)
            return group_id.strip(), artifact_id.strip(), str(version).strip() if version else None

    name = source.get("name") or ""
    version = source.get("version")
    return parse_maven_coordinate(name, str(version) if version else None)


def fossa_remediation_version(remediation: dict[str, Any] | None) -> str | None:
    """Extract target version from FOSSA remediation block."""
    if not remediation:
        return None
    for key in ("completeFix", "partialFix", "version", "recommendedVersion", "targetVersion"):
        value = remediation.get(key)
        if value:
            return str(value)
    return None


class LookupVulnerabilityFix(CodedTool):
    """Resolve a safe target version for a package/CVE using OSV.dev (public API, no API key)."""

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> Any:
        package = args.get("package") or args.get("package_name")
        current_version = args.get("current_version")
        cve = args.get("cve")
        ecosystem = args.get("ecosystem") or "Maven"

        if not package:
            return "package is required (e.g. org.apache.commons:commons-text)."

        group_id, artifact_id, parsed_version = parse_maven_coordinate(package, current_version)
        if not allows_osv_lookup(
            sly_data,
            package=package,
            cve=cve,
            artifact_id=artifact_id,
            no_safe_version_fallback=bool(args.get("no_safe_version_fallback")),
        ):
            return (
                "OSV/Maven lookup is disabled for this package (FOSSA-first mode). "
                "Use FOSSA completeFix/partialFix/recommended_version, or call this tool only when "
                "FOSSA reports NO_SAFE_VERSION for the finding."
            )

        current_version = parsed_version or current_version
        osv_name = f"{group_id}:{artifact_id}" if group_id else artifact_id

        result = await self._query_osv(osv_name, current_version, ecosystem, cve)
        if not result:
            result = await self._query_maven_latest(group_id, artifact_id)

        if not result:
            return (
                f"No automated fix found for {osv_name}@{current_version or 'unknown'}. "
                "Review FOSSA issue remediation notes or choose a fixed version manually."
            )

        key = f"{group_id}:{artifact_id}" if group_id else artifact_id
        sly_data.setdefault("lookup_fixes", {})[key] = result

        return (
            f"Lookup result for {key}: target_version={result['target_version']} "
            f"(source={result['source']}, reason={result.get('reason', 'n/a')})"
        )

    async def _query_osv(
        self,
        package_name: str,
        version: str | None,
        ecosystem: str,
        cve: str | None,
    ) -> dict[str, Any] | None:
        payload: dict[str, Any] = {"package": {"name": package_name, "ecosystem": ecosystem}}
        if version:
            payload["version"] = version
        if cve:
            payload["vuln_id"] = cve

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post("https://api.osv.dev/v1/query", json=payload)
            if response.status_code != 200:
                return None
            data = response.json()

        vulns = data.get("vulns") or []
        if cve:
            vulns = [v for v in vulns if v.get("id") == cve or cve in (v.get("aliases") or [])] or vulns

        fixed_versions: list[str] = []
        for vuln in vulns:
            for affected in vuln.get("affected") or []:
                for item in affected.get("ranges") or []:
                    for event in item.get("events") or []:
                        fixed = event.get("fixed")
                        if fixed:
                            fixed_versions.append(str(fixed))

        if not fixed_versions:
            return None

        target = sorted(set(fixed_versions), key=self._version_sort_key)[-1]
        return {
            "group_id": parse_maven_coordinate(package_name)[0],
            "artifact_id": parse_maven_coordinate(package_name)[1],
            "package": package_name,
            "current_version": version,
            "target_version": target,
            "source": "osv.dev",
            "reason": cve or vulns[0].get("id"),
        }

    async def _query_maven_latest(self, group_id: str, artifact_id: str) -> dict[str, Any] | None:
        if not group_id or not artifact_id:
            return None

        url = "https://search.maven.org/solrsearch/select"
        params = {"q": f"g:{group_id} AND a:{artifact_id}", "rows": 1, "wt": "json", "core": "gav"}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, params=params)
            if response.status_code != 200:
                return None
            docs = (response.json().get("response") or {}).get("docs") or []

        if not docs:
            return None

        latest = str(docs[0].get("latestVersion") or docs[0].get("v") or "")
        if not latest:
            return None

        return {
            "group_id": group_id,
            "artifact_id": artifact_id,
            "package": f"{group_id}:{artifact_id}",
            "target_version": latest,
            "source": "search.maven.org",
            "reason": "latest release (fallback when OSV has no fixed event)",
        }

    @staticmethod
    def _version_sort_key(value: str) -> tuple:
        parts = re.split(r"[.\-]", value)
        key: list[Any] = []
        for part in parts:
            key.append(int(part) if part.isdigit() else part)
        return tuple(key)
