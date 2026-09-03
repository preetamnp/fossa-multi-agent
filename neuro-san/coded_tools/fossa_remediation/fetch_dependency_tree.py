"""Fetch Maven/Gradle dependency tree for agent reasoning on transitive dependencies."""

from __future__ import annotations

import subprocess
from typing import Any

from neuro_san.interfaces.coded_tool import CodedTool

from workspace import format_tool_message, require_workspace, run_argv_command, store_tool_result


class FetchDependencyTree(CodedTool):
    """Run mvn dependency:tree or gradle dependencies and return a truncated excerpt."""

    DEFAULT_MAX_LINES = 120

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> Any:
        repo_name = args.get("repo_name")
        ws, error = require_workspace(sly_data, repo_name)
        if error:
            return error
        assert ws is not None

        if not ws.deps_command:
            return f"Unsupported build tool: {ws.build_tool}"

        max_lines = int(args.get("max_lines") or self.DEFAULT_MAX_LINES)
        proc = await run_argv_command(
            ws,
            ws.deps_command,
            timeout_seconds=int(args.get("timeout_seconds") or 300),
        )
        if isinstance(proc, subprocess.TimeoutExpired):
            result = {
                "tool": "FetchDependencyTree",
                "repo_name": repo_name,
                "ok": False,
                "phase": "dependency_tree",
                "exit_code": -1,
                "errors": ["dependency tree command timed out"],
            }
            store_tool_result(sly_data, repo_name, "FetchDependencyTree", result)
            return format_tool_message(result)

        output = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0:
            tail = "\n".join(output.splitlines()[-20:])
            result = {
                "tool": "FetchDependencyTree",
                "repo_name": repo_name,
                "ok": False,
                "phase": "dependency_tree",
                "exit_code": proc.returncode,
                "errors": tail.splitlines()[-10:] or [f"exit {proc.returncode}"],
                "log_tail": tail,
            }
            store_tool_result(sly_data, repo_name, "FetchDependencyTree", result)
            return f"dependency tree failed for {repo_name} (exit {proc.returncode}):\n{tail}"

        lines = output.splitlines()
        excerpt = "\n".join(lines[:max_lines])
        if len(lines) > max_lines:
            excerpt += f"\n... truncated ({len(lines) - max_lines} more lines)"

        sly_data.setdefault("dependency_trees", {})[repo_name] = excerpt
        store_tool_result(
            sly_data,
            repo_name,
            "FetchDependencyTree",
            {
                "tool": "FetchDependencyTree",
                "repo_name": repo_name,
                "ok": True,
                "phase": "dependency_tree",
                "line_count": len(lines),
            },
        )
        return f"Dependency tree for {repo_name}:\n```\n{excerpt}\n```"
