"""Git operations for cloning, branching, and committing remediation changes."""

from __future__ import annotations

import asyncio
import os
import subprocess
from typing import Any

from neuro_san.interfaces.coded_tool import CodedTool

from _config import ensure_work_dir, get_repo_by_name, resolve_fix_branch_name


class GitCloneAndBranch(CodedTool):
    """Clone a pilot repo and create a fix branch."""

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> Any:
        repo_name = args.get("repo_name")
        branch_name, ignored_branch = resolve_fix_branch_name(repo_name, args)

        repo = get_repo_by_name(repo_name)
        if repo is None:
            return f"Unknown repo_name: {repo_name}"

        gh = repo["github"]
        clone_url = f"https://github.com/{gh['org']}/{gh['repo']}.git"
        if os.environ.get("GITHUB_TOKEN"):
            clone_url = (
                f"https://{os.environ['GITHUB_TOKEN']}@github.com/{gh['org']}/{gh['repo']}.git"
            )

        work_root = ensure_work_dir()
        target = work_root / repo_name
        default_branch = gh.get("default_branch", "main")

        if target.exists():
            await self._run(["git", "-C", str(target), "fetch", "origin"])
            # Prior runs may leave dirty files (e.g. VerifyFossaScan touching .fossa.yml).
            await self._run(["git", "-C", str(target), "reset", "--hard"])
            await self._run(["git", "-C", str(target), "clean", "-fd"])
        else:
            await self._run(["git", "clone", clone_url, str(target)])

        await self._run(["git", "-C", str(target), "checkout", default_branch])
        await self._run(["git", "-C", str(target), "reset", "--hard", f"origin/{default_branch}"])
        await self._run(["git", "-C", str(target), "checkout", "-B", branch_name])

        sly_data.setdefault("repo_paths", {})[repo_name] = str(target)
        sly_data.setdefault("repo_branches", {})[repo_name] = branch_name

        message = (
            f"Cloned {gh['org']}/{gh['repo']} to {target} on fresh branch {branch_name} "
            f"(from {default_branch})."
        )
        if ignored_branch:
            message += (
                f" Agent-provided branch_name `{ignored_branch}` was ignored "
                f"(set ALLOW_AGENT_BRANCH_NAME=true to override)."
            )
        return message

    @staticmethod
    async def _run_optional(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        return await asyncio.to_thread(
            subprocess.run,
            cmd,
            check=False,
            capture_output=True,
            text=True,
        )

    @staticmethod
    async def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        return await asyncio.to_thread(
            subprocess.run,
            cmd,
            check=True,
            capture_output=True,
            text=True,
        )


class GitCommitAndPush(CodedTool):
    """Commit dependency changes and push the fix branch."""

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> Any:
        repo_name = args.get("repo_name")
        commit_message = args.get("commit_message") or f"fix(fossa): security and license remediation for {repo_name}"

        repo_path = (sly_data.get("repo_paths") or {}).get(repo_name)
        branch_name = (sly_data.get("repo_branches") or {}).get(repo_name)
        if not repo_path:
            return f"No cloned repo found for {repo_name}. Run GitCloneAndBranch first."
        if not branch_name:
            return f"No branch recorded for {repo_name}. Run GitCloneAndBranch first."

        await GitCloneAndBranch._run(["git", "-C", repo_path, "add", "-A"])
        status = await GitCloneAndBranch._run(["git", "-C", repo_path, "status", "--porcelain"])
        if not status.stdout.strip():
            return f"No changes to commit for {repo_name}."

        await GitCloneAndBranch._run(["git", "-C", repo_path, "commit", "-m", commit_message])
        push_result = await GitCloneAndBranch._run_optional(
            ["git", "-C", repo_path, "push", "-u", "origin", branch_name]
        )
        if push_result.returncode != 0:
            return self._format_push_failure(repo_name, branch_name, push_result)

        sha_proc = await GitCloneAndBranch._run_optional(
            ["git", "-C", repo_path, "rev-parse", "HEAD"]
        )
        if sha_proc.returncode == 0:
            sly_data.setdefault("repo_commits", {})[repo_name] = sha_proc.stdout.strip()

        return f"Pushed branch {branch_name} for {repo_name}."

    @staticmethod
    def _format_push_failure(
        repo_name: str,
        branch_name: str,
        result: subprocess.CompletedProcess[str],
    ) -> str:
        detail = ((result.stderr or "") + "\n" + (result.stdout or "")).strip()
        detail = detail or f"git push exited with code {result.returncode}"
        lowered = detail.lower()

        if any(
            phrase in lowered
            for phrase in ("non-fast-forward", "fetch first", "rejected", "failed to push some refs")
        ):
            return (
                f"Git push FAILED for {repo_name} on branch `{branch_name}`: "
                "remote history diverged (non-fast-forward). "
                "This usually means a prior run reused the same branch name.\n\n"
                "Recovery: call GitCloneAndBranch again (creates a new timestamped branch), "
                "re-apply fixes with ApplyDependencyFix, then GitCommitAndPush.\n\n"
                f"Git output:\n{detail[:2000]}"
            )

        if "authentication failed" in lowered or "403" in detail or "401" in detail:
            return (
                f"Git push FAILED for {repo_name}: GitHub authentication failed. "
                "Check GITHUB_TOKEN in .env has repo push scope.\n\n"
                f"Git output:\n{detail[:2000]}"
            )

        return f"Git push FAILED for {repo_name} on branch `{branch_name}`:\n{detail[:2000]}"
