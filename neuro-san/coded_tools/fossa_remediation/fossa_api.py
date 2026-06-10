"""FOSSA REST helpers for revision resolution and issue queries."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from _config import FossaRevisionNotFound, fossa_base_url, fossa_headers


def normalize_git_sha(value: str | None) -> str:
    """Return lowercase full or prefix git SHA (FOSSA needs 40 chars for scope[revision])."""
    if not value:
        return ""
    normalized = value.strip().lower()
    if normalized.startswith("git+"):
        if "$" in normalized:
            normalized = normalized.rsplit("$", 1)[-1]
        else:
            return normalized
    return normalized


def revision_commit_sha(entry: dict[str, Any]) -> str:
    loc = entry.get("loc") or {}
    return normalize_git_sha(loc.get("revision") or "")


def revisions_for_branch(revisions_payload: dict[str, Any], branch_name: str) -> list[dict[str, Any]]:
    branches = revisions_payload.get("branch") or {}
    entries = branches.get(branch_name) or []
    return entries if isinstance(entries, list) else []


async def fetch_project_revisions(
    client: httpx.AsyncClient,
    project_locator: str,
) -> dict[str, Any]:
    encoded = quote(project_locator, safe="")
    url = f"{fossa_base_url()}/projects/{encoded}/revisions"
    response = await client.get(url, headers=fossa_headers())
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, dict) else {}


def find_branch_revision(
    revisions_payload: dict[str, Any],
    branch_name: str,
    commit_sha: str | None = None,
) -> dict[str, Any] | None:
    """Return the FOSSA revision entry for branch (optionally matching commit)."""
    entries = revisions_for_branch(revisions_payload, branch_name)
    if not entries:
        return None

    target = normalize_git_sha(commit_sha)
    if target:
        for entry in entries:
            rev = revision_commit_sha(entry)
            if rev == target or rev.startswith(target) or target.startswith(rev):
                return entry

    return entries[0]


async def resolve_branch_revision(
    client: httpx.AsyncClient,
    project_locator: str,
    branch_name: str,
    commit_sha: str | None = None,
) -> dict[str, Any] | None:
    payload = await fetch_project_revisions(client, project_locator)
    return find_branch_revision(payload, branch_name, commit_sha)


async def fetch_vulnerability_issues(
    client: httpx.AsyncClient,
    project_locator: str,
    revision_sha: str,
    *,
    severity: list[str] | None = None,
    max_count: int = 100,
) -> list[dict[str, Any]]:
    """Fetch all vulnerability issues for a project revision (full 40-char SHA required)."""
    revision = normalize_git_sha(revision_sha)
    if not revision:
        return []

    levels = severity or ["critical", "high", "medium", "low"]
    issues: list[dict[str, Any]] = []
    page = 1
    page_size = min(max_count, 100)

    while len(issues) < max_count:
        params: list[tuple[str, str]] = [
            ("category", "vulnerability"),
            ("scope[type]", "project"),
            ("scope[id]", project_locator),
            ("scope[revision]", revision),
            ("count", str(page_size)),
            ("page", str(page)),
        ]
        for index, level in enumerate(levels):
            params.append((f"filter[severity][{index}]", level))

        response = await client.get(
            f"{fossa_base_url()}/v2/issues",
            headers=fossa_headers(),
            params=params,
        )
        if response.status_code == 404:
            raise FossaRevisionNotFound(revision)
        response.raise_for_status()

        batch = (response.json() or {}).get("issues") or []
        if not isinstance(batch, list) or not batch:
            break
        issues.extend(batch)
        if len(batch) < page_size:
            break
        page += 1

    return issues[:max_count]
