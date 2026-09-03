"""Run Maven/Gradle compile and test commands in the repo workspace."""

from __future__ import annotations

import subprocess
from typing import Any

from neuro_san.interfaces.coded_tool import CodedTool

from _config import MAX_TEST_HEAL_ATTEMPTS, test_heal_attempts
from remediation_log import report_progress
from workspace import (
    extract_build_error_lines,
    format_tool_message,
    require_workspace,
    run_shell_command,
    store_tool_result,
)


async def _run_build_phase(
    args: dict[str, Any],
    sly_data: dict[str, Any],
    *,
    tool: str,
    phase: str,
    command: str,
    sly_result_key: str,
    timeout_seconds: int,
    progress_label: str,
) -> dict[str, Any]:
    repo_name = args.get("repo_name")
    ws, error = require_workspace(sly_data, repo_name)
    if error:
        return {"tool": tool, "repo_name": repo_name or "", "ok": False, "phase": phase, "message": error}

    assert ws is not None
    await report_progress(args, phase=progress_label, detail=f"`{command}` (Java {ws.java_version})")

    proc = await run_shell_command(ws, command, timeout_seconds=timeout_seconds)
    if isinstance(proc, subprocess.TimeoutExpired):
        result = {
            "tool": tool,
            "repo_name": repo_name,
            "ok": False,
            "phase": phase,
            "exit_code": -1,
            "errors": [f"Timed out after {timeout_seconds}s"],
            "command": command,
        }
        store_tool_result(sly_data, repo_name, tool, result)
        sly_data.setdefault(sly_result_key, {})[repo_name] = {
            "returncode": -1,
            "passed": False,
            "error_lines": result["errors"],
        }
        return result

    combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
    error_lines = extract_build_error_lines(combined)
    ok = proc.returncode == 0

    sly_data.setdefault(sly_result_key, {})[repo_name] = {
        "returncode": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-6000:],
        "stderr_tail": (proc.stderr or "")[-4000:],
        "error_lines": error_lines[:20],
        "passed": ok,
        "command": command,
    }

    result = {
        "tool": tool,
        "repo_name": repo_name,
        "ok": ok,
        "phase": phase,
        "exit_code": proc.returncode,
        "errors": error_lines[:20],
        "command": command,
        "log_tail": combined[-4000:],
    }
    store_tool_result(sly_data, repo_name, tool, result)
    return result


class CompileJava(CodedTool):
    """Compile the workspace project without running tests (fast feedback after dependency changes)."""

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> Any:
        repo_name = args.get("repo_name")
        ws, error = require_workspace(sly_data, repo_name)
        if error:
            return error
        assert ws is not None

        result = await _run_build_phase(
            args,
            sly_data,
            tool="CompileJava",
            phase="compile",
            command=ws.compile_command,
            sly_result_key="compile_results",
            timeout_seconds=int(args.get("timeout_seconds") or 600),
            progress_label="Compile",
        )
        if result.get("message"):
            return result["message"]
        if result.get("ok"):
            return f"Compile PASSED for {repo_name}."

        result["next_hint"] = "Fix compile errors before RunJavaTests (ReadRepoFile / ApplyDependencyFix)."
        return format_tool_message(result)


class RunJavaTests(CodedTool):
    """Execute configured test command in the cloned repository workspace."""

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> Any:
        repo_name = args.get("repo_name")
        ws, error = require_workspace(sly_data, repo_name)
        if error:
            return error
        assert ws is not None

        result = await _run_build_phase(
            args,
            sly_data,
            tool="RunJavaTests",
            phase="test",
            command=ws.test_command,
            sly_result_key="test_results",
            timeout_seconds=int(args.get("timeout_seconds") or 900),
            progress_label="Run tests",
        )
        if result.get("message"):
            return result["message"]
        if result.get("ok"):
            sly_data.setdefault("test_fix_attempts", {})[repo_name] = 0
            return f"Tests PASSED for {repo_name}."

        attempts = test_heal_attempts(sly_data, repo_name)
        if attempts >= MAX_TEST_HEAL_ATTEMPTS:
            result["next_hint"] = "Escalate to human review; do not open PR."
        else:
            result["next_hint"] = (
                f"NEXT: Call DiagnoseTestFailures, apply a fix with ApplyDependencyFix, "
                f"then CompileJava and RunJavaTests again "
                f"({attempts}/{MAX_TEST_HEAL_ATTEMPTS} self-heal attempt(s) used so far)."
            )
        return format_tool_message(result)
