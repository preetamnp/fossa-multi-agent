"""Fetch Maven/Gradle dependency tree for agent reasoning on transitive dependencies."""

from __future__ import annotations

import asyncio
import os
import subprocess
from typing import Any

from neuro_san.interfaces.coded_tool import CodedTool

from _config import get_repo_by_name


class FetchDependencyTree(CodedTool):
    """Run mvn dependency:tree or gradle dependencies and return a truncated excerpt."""

    DEFAULT_MAX_LINES = 120

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> Any:
        repo_name = args.get("repo_name")
        if not repo_name:
            return "repo_name is required."

        repo_path = (sly_data.get("repo_paths") or {}).get(repo_name)
        if not repo_path:
            return f"No cloned repo for {repo_name}. Run GitCloneAndBranch first."

        repo = get_repo_by_name(repo_name)
        if repo is None:
            return f"Unknown repo_name: {repo_name}"

        build_tool = repo["build"].get("tool", "maven")
        max_lines = int(args.get("max_lines") or self.DEFAULT_MAX_LINES)

        if build_tool == "maven":
            cmd = ["./mvnw", "-q", "dependency:tree", "-Dverbose=false"]
        elif build_tool == "gradle":
            cmd = ["./gradlew", "-q", "dependencies", "--configuration", "compileClasspath"]
        else:
            return f"Unsupported build tool: {build_tool}"

        env = os.environ.copy()
        java_home = os.environ.get("JAVA_HOME")
        if java_home:
            env["JAVA_HOME"] = java_home

        try:
            proc = await asyncio.to_thread(
                subprocess.run,
                cmd,
                cwd=repo_path,
                capture_output=True,
                text=True,
                env=env,
                timeout=int(args.get("timeout_seconds") or 300),
                check=False,
            )
        except subprocess.TimeoutExpired:
            return f"dependency tree command timed out for {repo_name}."

        output = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0:
            tail = "\n".join(output.splitlines()[-20:])
            return f"dependency tree failed for {repo_name} (exit {proc.returncode}):\n{tail}"

        lines = output.splitlines()
        excerpt = "\n".join(lines[:max_lines])
        if len(lines) > max_lines:
            excerpt += f"\n... truncated ({len(lines) - max_lines} more lines)"

        sly_data.setdefault("dependency_trees", {})[repo_name] = excerpt
        return f"Dependency tree for {repo_name}:\n```\n{excerpt}\n```"
