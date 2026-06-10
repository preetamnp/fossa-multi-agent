"""Poll FOSSA until the fix branch scan shows remediated issues."""

from __future__ import annotations

import asyncio
import os
import subprocess
import time
from typing import Any

import httpx

from neuro_san.interfaces.coded_tool import CodedTool

from _config import (
    FossaRevisionNotFound,
    get_repo_by_name,
    is_remediation_dry_run,
)
from fossa_api import (
    fetch_vulnerability_issues,
    normalize_git_sha,
    resolve_branch_revision,
    revision_commit_sha,
)
from remediation_log import report_progress


class VerifyFossaScan(CodedTool):
    """Wait for FOSSA to scan the fix branch and confirm zero security vulnerabilities (licensing ignored)."""

    DEFAULT_MAX_WAIT = 600
    DEFAULT_POLL = 30

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> Any:
        repo_name = args.get("repo_name")
        if not repo_name:
            return "repo_name is required."

        repo = get_repo_by_name(repo_name)
        if repo is None:
            return f"Unknown repo_name: {repo_name}"

        if is_remediation_dry_run(sly_data):
            result = {
                "passed": False,
                "skipped": True,
                "reason": "REMEDIATION_DRY_RUN=true — FOSSA branch verify skipped for POC speed",
            }
            sly_data.setdefault("fossa_verify", {})[repo_name] = result
            return (
                f"FOSSA verification SKIPPED for {repo_name} (dry run / POC mode). "
                "Set REMEDIATION_DRY_RUN=false before CreatePullRequest to require a clean branch scan."
            )

        repo_path = (sly_data.get("repo_paths") or {}).get(repo_name)
        branch_name = (sly_data.get("repo_branches") or {}).get(repo_name)
        if not repo_path or not branch_name:
            return f"Missing cloned repo or branch for {repo_name}. Run GitCloneAndBranch and GitCommitAndPush first."

        max_wait = int(args.get("max_wait_seconds") or os.environ.get("FOSSA_VERIFY_MAX_WAIT_SECONDS") or self.DEFAULT_MAX_WAIT)
        poll_seconds = int(args.get("poll_seconds") or os.environ.get("FOSSA_VERIFY_POLL_SECONDS") or self.DEFAULT_POLL)
        severity = args.get("severity") or ["critical", "high", "medium", "low"]

        commit_sha = normalize_git_sha(
            (sly_data.get("repo_commits") or {}).get(repo_name) or await self._git_head(repo_path)
        )
        if not commit_sha:
            return f"Could not determine commit SHA for {repo_name}. Run GitCommitAndPush first."

        project_locator = repo["fossa"]["project_locator"]
        # GitHub PR checks use the GitHub-imported project (git+github.com/...).
        # `fossa analyze` CLI uploads to a separate custom+*/ project — do not use it for verify.
        deadline = time.monotonic() + max_wait
        attempt = 0
        last_status = (
            "waiting for FOSSA GitHub App to scan this branch "
            f"(project `{project_locator}`). Open a draft PR first if the branch is not indexed."
        )

        await report_progress(
            args,
            phase="FOSSA verify",
            detail=f"waiting for GitHub scan on `{branch_name}` (up to {max_wait}s)",
        )

        async with httpx.AsyncClient(timeout=60.0) as client:
            while time.monotonic() < deadline:
                attempt += 1
                await report_progress(
                    args,
                    phase="FOSSA verify",
                    detail=last_status,
                    attempt=attempt,
                )
                revision_entry = await resolve_branch_revision(
                    client, project_locator, branch_name, commit_sha
                )

                if revision_entry is None:
                    pr_url = (sly_data.get("pull_requests") or {}).get(repo_name, {}).get("url")
                    pr_hint = f" Draft PR: {pr_url}." if pr_url else " Open a draft PR to trigger GitHub FOSSA scan."
                    last_status = (
                        f"branch `{branch_name}` commit `{commit_sha[:12]}` not in FOSSA GitHub project yet.{pr_hint}"
                    )
                else:
                    fossa_sha = revision_commit_sha(revision_entry)
                    resolved = revision_entry.get("resolved")
                    unresolved_total = revision_entry.get("unresolved_issue_count")
                    last_status = (
                        f"branch `{branch_name}` indexed as `{fossa_sha[:12]}` "
                        f"(resolved={resolved}, unresolved_total={unresolved_total})"
                    )

                    if fossa_sha and (resolved is False or resolved is None):
                        last_status += " — FOSSA analysis still running"
                    elif fossa_sha:
                        try:
                            vuln_findings = await fetch_vulnerability_issues(
                                client,
                                project_locator,
                                fossa_sha,
                                severity=severity,
                                max_count=100,
                            )
                        except FossaRevisionNotFound:
                            last_status = (
                                f"revision `{fossa_sha[:12]}` listed in /projects/revisions but "
                                "/v2/issues not ready yet — analysis may still be running."
                            )
                        else:
                            vuln_count = len(vuln_findings)
                            remaining_cves = sorted({item.get("cve") for item in vuln_findings if item.get("cve")})
                            last_status = (
                                f"{vuln_count} security vulnerability issue(s) on revision `{fossa_sha[:12]}` "
                                f"(branch `{branch_name}`)"
                            )

                            if vuln_count == 0:
                                result = {
                                    "passed": True,
                                    "revision": fossa_sha,
                                    "branch": branch_name,
                                    "attempts": attempt,
                                    "vulnerability_count": vuln_count,
                                    "remaining_cves": remaining_cves,
                                    "unresolved_issue_count": unresolved_total,
                                }
                                sly_data.setdefault("fossa_verify", {})[repo_name] = result
                                return (
                                    f"FOSSA verification PASSED for {repo_name} on revision `{fossa_sha[:12]}` "
                                    f"(branch `{branch_name}`) after {attempt} poll(s): "
                                    "0 security vulnerabilities (GitHub Security Analysis should be green). "
                                    "License issues are not checked. Safe to open draft PR."
                                )

                            result = {
                                "passed": False,
                                "revision": fossa_sha,
                                "branch": branch_name,
                                "attempts": attempt,
                                "vulnerability_count": vuln_count,
                                "remaining_cves": remaining_cves,
                                "unresolved_issue_count": unresolved_total,
                            }
                            sly_data.setdefault("fossa_verify", {})[repo_name] = result
                            return (
                                f"FOSSA verification FAILED for {repo_name}: {vuln_count} security "
                                f"vulnerability issue(s) remain on revision `{fossa_sha[:12]}` "
                                f"(branch `{branch_name}`). CVEs: {', '.join(remaining_cves[:10])}"
                                f"{'...' if len(remaining_cves) > 10 else ''}. "
                                "Revise the remediation plan and re-run."
                            )

                remaining = int(deadline - time.monotonic())
                if remaining <= 0:
                    break
                await asyncio.sleep(min(poll_seconds, remaining))

        result = {
            "passed": False,
            "revision": commit_sha,
            "branch": branch_name,
            "attempts": attempt,
            "last_status": last_status,
        }
        sly_data.setdefault("fossa_verify", {})[repo_name] = result
        return (
            f"FOSSA verification FAILED for {repo_name} after {max_wait}s ({attempt} polls). "
            f"Last status: {last_status}. "
            "FOSSA GitHub App has not indexed this branch on the GitHub-imported project. "
            "Open a draft PR first (triggers scan), then re-run VerifyFossaScan. "
            "Note: `fossa analyze` CLI uploads to a different FOSSA project and does not satisfy GitHub PR checks."
        )

    @staticmethod
    async def _git_head(repo_path: str) -> str | None:
        try:
            proc = await asyncio.to_thread(
                subprocess.run,
                ["git", "-C", repo_path, "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            )
            return proc.stdout.strip()
        except subprocess.CalledProcessError:
            return None
