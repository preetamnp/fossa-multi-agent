"""Run Maven/Gradle tests for remediated Spring Boot services."""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
from typing import Any

from neuro_san.interfaces.coded_tool import CodedTool

from _config import get_repo_by_name
from remediation_log import report_progress


class RunJavaTests(CodedTool):
    """Execute configured test command in the cloned repository."""

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> Any:
        repo_name = args.get("repo_name")
        repo_path = (sly_data.get("repo_paths") or {}).get(repo_name)
        if not repo_path:
            return f"No cloned repo found for {repo_name}. Run GitCloneAndBranch first."

        repo = get_repo_by_name(repo_name)
        if repo is None:
            return f"Unknown repo_name: {repo_name}"

        test_command = repo["build"].get("test_command", "./mvnw test")
        java_version = repo["build"].get("java_version", "21")

        await report_progress(
            args,
            phase="Run tests",
            detail=f"`{test_command}` (Java {java_version})",
        )

        env = os.environ.copy()
        env["FOSSA_POC_JAVA_VERSION"] = java_version

        try:
            result = await asyncio.to_thread(
                subprocess.run,
                test_command,
                shell=True,
                cwd=repo_path,
                capture_output=True,
                text=True,
                env=env,
                timeout=int(args.get("timeout_seconds") or 900),
            )
        except subprocess.TimeoutExpired:
            return f"Tests timed out for {repo_name} after {args.get('timeout_seconds', 900)}s."

        combined = (result.stdout or "") + "\n" + (result.stderr or "")
        error_lines = self._extract_error_lines(combined)

        sly_data.setdefault("test_results", {})[repo_name] = {
            "returncode": result.returncode,
            "stdout_tail": (result.stdout or "")[-6000:],
            "stderr_tail": (result.stderr or "")[-4000:],
            "error_lines": error_lines[:20],
            "passed": result.returncode == 0,
        }

        if result.returncode == 0:
            sly_data.setdefault("test_fix_attempts", {})[repo_name] = 0
            return f"Tests PASSED for {repo_name}."

        summary = "\n".join(f"  - {line}" for line in error_lines[:10]) or "  - (see build log tail in test_results)"
        return (
            f"Tests FAILED for {repo_name} (exit {result.returncode}).\n"
            f"Key errors:\n{summary}\n\n"
            "NEXT: Call DiagnoseTestFailures, reason about the cause, apply a fix with ApplyDependencyFix, "
            "then call RunJavaTests again (up to 3 self-heal attempts)."
        )

    @staticmethod
    def _extract_error_lines(log_text: str) -> list[str]:
        lines: list[str] = []
        patterns = [
            r"\[ERROR\][^\n]+",
            r"ClassNotFoundException[^\n]+",
            r"NoClassDefFoundError[^\n]+",
            r"NoSuchMethodError[^\n]+",
            r"Failed to execute goal[^\n]+",
            r"BUILD FAILURE[^\n]*",
            r"Tests run:[^\n]+Failures:[1-9][^\n]*",
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
