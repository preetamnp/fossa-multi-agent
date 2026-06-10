"""Store LLM-authored PR title and body before CreatePullRequest."""

from __future__ import annotations

from typing import Any

from neuro_san.interfaces.coded_tool import CodedTool


class SubmitPullRequestBody(CodedTool):
    """Persist draft PR title/body composed by the pr_author agent."""

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> Any:
        repo_name = args.get("repo_name")
        title = (args.get("title") or "").strip()
        body = (args.get("body") or "").strip()

        if not repo_name:
            return "repo_name is required."
        if not title:
            return "title is required."
        if not body:
            return "body is required (markdown)."

        sly_data.setdefault("pull_request_drafts", {})[repo_name] = {
            "title": title,
            "body": body,
        }
        return f"Stored PR draft for {repo_name}. Call CreatePullRequest with repo_name next."
