"""Workspace session layer for Category A coded tools (Cursor-like executors).

Agents pass repo_name only; tools resolve clone root, build commands, and safe paths from
sly_data + config/repos.yaml. Results are stored as structured ToolResult dicts.
"""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from _config import get_repo_by_name


@dataclass(frozen=True)
class Workspace:
    """Resolved clone session for one pilot repo."""

    repo_name: str
    root: Path
    branch: str | None
    build_tool: str
    java_version: str
    test_command: str
    compile_command: str
    deps_command: list[str]
    dependency_files: tuple[str, ...]


def default_compile_command(build_tool: str) -> str:
    if build_tool == "maven":
        return "./mvnw -q -DskipTests compile"
    if build_tool == "gradle":
        return "./gradlew -q compileJava"
    return ""


def default_deps_command(build_tool: str) -> list[str]:
    if build_tool == "maven":
        return ["./mvnw", "-q", "dependency:tree", "-Dverbose=false"]
    if build_tool == "gradle":
        return ["./gradlew", "-q", "dependencies", "--configuration", "compileClasspath"]
    return []


def default_build_filename(build_tool: str) -> str:
    return "pom.xml" if build_tool == "maven" else "build.gradle"


def build_workspace_from_repo(repo_name: str, root: Path, branch: str | None) -> Workspace | None:
    repo = get_repo_by_name(repo_name)
    if repo is None:
        return None

    build = repo.get("build") or {}
    build_tool = build.get("tool", "maven")
    dependency_files = tuple(build.get("dependency_files") or [default_build_filename(build_tool)])

    return Workspace(
        repo_name=repo_name,
        root=root,
        branch=branch,
        build_tool=build_tool,
        java_version=str(build.get("java_version", "21")),
        test_command=build.get("test_command") or ("./mvnw test" if build_tool == "maven" else "./gradlew test"),
        compile_command=build.get("compile_command") or default_compile_command(build_tool),
        deps_command=list(build.get("deps_command") or default_deps_command(build_tool)),
        dependency_files=dependency_files,
    )


def register_workspace(
    sly_data: dict[str, Any],
    repo_name: str,
    root: Path | str,
    branch: str | None,
) -> Workspace | None:
    """Record workspace session state (and legacy repo_paths/repo_branches keys)."""
    ws = build_workspace_from_repo(repo_name, Path(root), branch)
    if ws is None:
        return None

    payload = {
        "root": str(ws.root),
        "branch": ws.branch,
        "build_tool": ws.build_tool,
        "java_version": ws.java_version,
        "test_command": ws.test_command,
        "compile_command": ws.compile_command,
        "deps_command": ws.deps_command,
        "dependency_files": list(ws.dependency_files),
    }
    sly_data.setdefault("workspaces", {})[repo_name] = payload
    sly_data.setdefault("repo_paths", {})[repo_name] = str(ws.root)
    if branch:
        sly_data.setdefault("repo_branches", {})[repo_name] = branch
    return ws


def require_workspace(sly_data: dict[str, Any], repo_name: str | None) -> tuple[Workspace | None, str | None]:
    """Resolve workspace for repo_name; hydrate from legacy keys if needed."""
    if not repo_name:
        return None, "repo_name is required."

    repo = get_repo_by_name(repo_name)
    if repo is None:
        return None, f"Unknown repo_name: {repo_name}"

    stored = (sly_data.get("workspaces") or {}).get(repo_name)
    root_str = (stored or {}).get("root") or (sly_data.get("repo_paths") or {}).get(repo_name)
    if not root_str:
        return None, f"No workspace for {repo_name}. Run GitCloneAndBranch first."

    branch = (stored or {}).get("branch") or (sly_data.get("repo_branches") or {}).get(repo_name)
    ws = build_workspace_from_repo(repo_name, Path(root_str), branch)
    if ws is None:
        return None, f"Unknown repo_name: {repo_name}"

    if not stored:
        register_workspace(sly_data, repo_name, ws.root, ws.branch)
    return ws, None


def resolve_relative_path(root: Path, relative_path: str) -> tuple[Path | None, str | None]:
    """Resolve a repo-relative path; reject traversal outside root."""
    rel = (relative_path or "").strip().replace("\\", "/")
    if not rel:
        return None, "relative_path is required."
    if rel.startswith("/") or re.match(r"^[A-Za-z]:", rel):
        return None, f"Absolute paths are not allowed: {relative_path}"

    candidate = (root / rel).resolve()
    root_resolved = root.resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError:
        return None, f"Path escapes workspace root: {relative_path}"
    return candidate, None


def build_env(java_version: str) -> dict[str, str]:
    env = os.environ.copy()
    env["FOSSA_POC_JAVA_VERSION"] = java_version
    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        env["JAVA_HOME"] = java_home
    return env


async def run_shell_command(
    ws: Workspace,
    command: str,
    *,
    timeout_seconds: int = 900,
) -> subprocess.CompletedProcess[str] | subprocess.TimeoutExpired:
    try:
        return await asyncio.to_thread(
            subprocess.run,
            command,
            shell=True,
            cwd=str(ws.root),
            capture_output=True,
            text=True,
            env=build_env(ws.java_version),
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        return exc


async def run_argv_command(
    ws: Workspace,
    argv: list[str],
    *,
    timeout_seconds: int = 300,
) -> subprocess.CompletedProcess[str] | subprocess.TimeoutExpired:
    try:
        return await asyncio.to_thread(
            subprocess.run,
            argv,
            cwd=str(ws.root),
            capture_output=True,
            text=True,
            env=build_env(ws.java_version),
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return exc


def extract_build_error_lines(log_text: str) -> list[str]:
    lines: list[str] = []
    patterns = [
        r"\[ERROR\][^\n]+",
        r"ClassNotFoundException[^\n]+",
        r"NoClassDefFoundError[^\n]+",
        r"NoSuchMethodError[^\n]+",
        r"Failed to execute goal[^\n]+",
        r"BUILD FAILURE[^\n]*",
        r"Tests run:[^\n]+Failures:[1-9][^\n]*",
        r"Compilation failure[^\n]*",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, log_text):
            line = match.group(0).strip()
            if line not in lines:
                lines.append(line[:300])
    if not lines:
        for line in log_text.splitlines():
            if "error" in line.lower() or "exception" in line.lower():
                lines.append(line.strip()[:300])
    return lines


def store_tool_result(
    sly_data: dict[str, Any],
    repo_name: str,
    tool: str,
    result: dict[str, Any],
) -> None:
    sly_data.setdefault("last_tool_result", {})[repo_name] = {"tool": tool, **result}
    sly_data.setdefault("tool_results", {}).setdefault(repo_name, []).append({"tool": tool, **result})


def format_error_summary(error_lines: list[str], *, max_lines: int = 10) -> str:
    if not error_lines:
        return "  - (see log tail in last_tool_result)"
    return "\n".join(f"  - {line}" for line in error_lines[:max_lines])


def format_tool_message(result: dict[str, Any]) -> str:
    """Human-readable chat message from a ToolResult dict."""
    tool = result.get("tool", "workspace")
    repo_name = result.get("repo_name", "")
    ok = result.get("ok", False)
    phase = result.get("phase", tool)

    if ok:
        return result.get("message") or f"{phase} PASSED for {repo_name}."

    summary = format_error_summary(result.get("errors") or [])
    lines = [
        f"{phase} FAILED for {repo_name} (exit {result.get('exit_code', '?')}).",
        f"Key errors:\n{summary}",
    ]
    if result.get("next_hint"):
        lines.append(str(result["next_hint"]))
    return "\n".join(lines)
