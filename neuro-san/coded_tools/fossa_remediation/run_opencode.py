"""Run the customer's OpenCode CLI as the coding worker for apply / test / git / PR."""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from neuro_san.interfaces.coded_tool import CodedTool

from _config import get_repo_by_name, is_remediation_dry_run
from git_ops import GitCloneAndBranch
from remediation_log import report_progress
from workspace import register_workspace, require_workspace, store_tool_result

PR_URL_RE = re.compile(r"https://github\.com/[^/\s]+/[^/\s]+/pull/\d+", re.IGNORECASE)


def _plan_actions(sly_data: dict[str, Any], repo_name: str) -> list[dict[str, Any]]:
    return list((sly_data.get("remediation_plan") or {}).get(repo_name) or [])


def _build_prompt(
    *,
    repo_name: str,
    repo: dict[str, Any],
    ws_root: Path,
    branch: str | None,
    actions: list[dict[str, Any]],
    meta: dict[str, Any],
    test_command: str,
    dry_run: bool,
) -> str:
    gh = repo["github"]
    github_slug = f"{gh['org']}/{gh['repo']}"
    default_branch = gh.get("default_branch", "main")
    plan_json = json.dumps(actions, indent=2)
    deferred = meta.get("deferred_issue_ids") or []
    strategy = meta.get("strategy_summary") or ""

    return f"""You are the coding worker for FOSSA vulnerability remediation on `{repo_name}`.

Workspace: `{ws_root}`
GitHub repo: `{github_slug}`
Current branch: `{branch or "unknown"}` (create a fix branch from `{default_branch}` if needed)
Test command: `{test_command}`

LOCKED REMEDIATION PLAN (do not invent versions; apply these actions only):
{plan_json}

Strategy: {strategy or "(none)"}
Deferred licensing issue IDs (do not treat as security): {deferred or []}

Do all of the following in this workspace:
1. Apply the locked plan to pom.xml / build.gradle (and source call sites if the bump requires it).
2. Run `{test_command}`. If tests fail, heal source/build files without changing planned versions. Retry tests.
3. If tests still fail, stop. Do not open a PR.
4. If tests pass: commit, push the fix branch, and open a **draft** pull request to `{default_branch}`.
   - Never merge. Never force-push to `{default_branch}`.
   - PR title should mention FOSSA security remediation for `{repo_name}`.
5. Print the draft PR URL on the last line as: PR_URL: https://github.com/{github_slug}/pull/<n>

Dry-run / POC note: {"FOSSA verify will be skipped after you open the PR." if dry_run else "A coded tool will verify FOSSA Security Analysis after the draft PR exists."}
"""


def _extract_pr_url(text: str) -> str | None:
    match = PR_URL_RE.search(text or "")
    return match.group(0) if match else None


async def _git_text(repo_path: Path, *git_args: str) -> str:
    proc = await asyncio.to_thread(
        subprocess.run,
        ["git", "-C", str(repo_path), *git_args],
        check=False,
        capture_output=True,
        text=True,
    )
    return (proc.stdout or "").strip()


class RunOpenCode(CodedTool):
    """Delegate apply, test, commit, push, and draft PR to the customer's OpenCode CLI."""

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> Any:
        repo_name = args.get("repo_name")
        if not repo_name:
            return "repo_name is required."

        repo = get_repo_by_name(repo_name)
        if repo is None:
            return f"Unknown repo_name: {repo_name}"

        actions = _plan_actions(sly_data, repo_name)
        if not actions:
            return (
                f"No validated remediation plan for {repo_name}. "
                "Call SubmitRemediationPlan then ValidateRemediationPlan before RunOpenCode."
            )

        ws, error = require_workspace(sly_data, repo_name)
        if error:
            clone_msg = await GitCloneAndBranch().async_invoke({"repo_name": repo_name}, sly_data)
            ws, error = require_workspace(sly_data, repo_name)
            if error:
                return f"Could not prepare workspace for OpenCode. {clone_msg}"

        assert ws is not None
        opencode = os.environ.get("OPENCODE_BIN", "opencode")
        if shutil.which(opencode) is None:
            return (
                f"OpenCode CLI `{opencode}` is not on PATH. "
                "Install OpenCode for this customer environment, or set OPENCODE_BIN."
            )

        meta = (sly_data.get("remediation_plan_meta") or {}).get(repo_name) or {}
        dry_run = is_remediation_dry_run(sly_data)
        timeout_seconds = int(args.get("timeout_seconds") or os.environ.get("OPENCODE_TIMEOUT_SECONDS") or 1200)
        prompt = _build_prompt(
            repo_name=repo_name,
            repo=repo,
            ws_root=ws.root,
            branch=ws.branch,
            actions=actions,
            meta=meta,
            test_command=ws.test_command,
            dry_run=dry_run,
        )

        argv = [opencode, "run", "--dir", str(ws.root), "--format", "json", prompt]
        model = (args.get("model") or os.environ.get("OPENCODE_MODEL") or "").strip()
        if model:
            argv[2:2] = ["--model", model]

        await report_progress(
            args,
            phase="OpenCode",
            detail=f"apply locked plan, test, draft PR in `{ws.root}`",
        )

        try:
            proc = await asyncio.to_thread(
                subprocess.run,
                argv,
                cwd=str(ws.root),
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return f"OpenCode timed out after {timeout_seconds}s for {repo_name}. Do not call VerifyFossaScan."

        combined = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
        pr_url = _extract_pr_url(combined)
        branch = await _git_text(ws.root, "rev-parse", "--abbrev-ref", "HEAD") or ws.branch
        commit_sha = await _git_text(ws.root, "rev-parse", "HEAD")
        register_workspace(sly_data, repo_name, ws.root, branch)
        if commit_sha:
            sly_data.setdefault("repo_commits", {})[repo_name] = commit_sha
        if pr_url:
            sly_data.setdefault("pull_requests", {})[repo_name] = {"url": pr_url}

        ok = proc.returncode == 0 and bool(pr_url)
        result = {
            "tool": "RunOpenCode",
            "repo_name": repo_name,
            "ok": ok,
            "phase": "opencode_apply",
            "exit_code": proc.returncode,
            "branch": branch,
            "commit_sha": commit_sha,
            "pr_url": pr_url,
            "log_tail": combined[-4000:],
        }
        store_tool_result(sly_data, repo_name, "RunOpenCode", result)

        if proc.returncode != 0:
            return (
                f"OpenCode FAILED for {repo_name} (exit {proc.returncode}). "
                "Do not call VerifyFossaScan until tests pass and a draft PR exists.\n"
                f"{combined[-2000:]}"
            )

        if not pr_url:
            return (
                f"OpenCode finished for {repo_name} on branch `{branch}` "
                f"(commit `{commit_sha[:12] if commit_sha else 'unknown'}`) but no PR URL was found. "
                "Call CreatePullRequest if the branch was pushed, then VerifyFossaScan.\n"
                f"{combined[-1500:]}"
            )

        return (
            f"OpenCode opened draft PR for {repo_name}: {pr_url} "
            f"(branch `{branch}`, commit `{commit_sha[:12] if commit_sha else 'unknown'}`). "
            "Call VerifyFossaScan next."
        )
