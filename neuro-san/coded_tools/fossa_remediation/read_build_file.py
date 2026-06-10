"""Read dependency/build files from the cloned repo for agent reasoning."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from neuro_san.interfaces.coded_tool import CodedTool

from _config import get_repo_by_name


class ReadBuildFile(CodedTool):
    """Return pom.xml or build.gradle excerpt so the agent can reason about dependency changes."""

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> Any:
        repo_name = args.get("repo_name")
        repo_path = (sly_data.get("repo_paths") or {}).get(repo_name)
        if not repo_path:
            return f"No cloned repo found for {repo_name}. Run GitCloneAndBranch first."

        repo = get_repo_by_name(repo_name)
        if repo is None:
            return f"Unknown repo_name: {repo_name}"

        build_tool = repo["build"].get("tool", "maven")
        filename = args.get("filename") or ("pom.xml" if build_tool == "maven" else "build.gradle")
        path = Path(repo_path) / filename
        if not path.exists():
            return f"{filename} not found in {repo_path}."

        content = path.read_text(encoding="utf-8")
        max_chars = int(args.get("max_chars") or 6000)
        excerpt = content[:max_chars]
        if len(content) > max_chars:
            excerpt += f"\n... truncated ({len(content) - max_chars} more chars)"

        return f"Contents of {filename} in {repo_name}:\n```xml\n{excerpt}\n```"
