"""Human-readable progress lines from Neuro SAN streaming messages."""

from __future__ import annotations

import re
import sys
from datetime import datetime
from typing import Any

from neuro_san.internals.messages.chat_message_type import ChatMessageType
from neuro_san.internals.messages.origination import Origination
from neuro_san.message_processing.message_processor import MessageProcessor

# Friendly labels for coded-tool steps in the remediation pipeline.
TOOL_LABELS: dict[str, str] = {
    "LoadRepoConfig": "Load repo configuration",
    "FetchFossaFindings": "Fetch FOSSA vulnerability findings",
    "GitCloneAndBranch": "Initialize workspace (clone and branch)",
    "PrepareRemediationContext": "Prepare remediation context",
    "FetchDependencyTree": "Fetch dependency tree",
    "ReadRepoFile": "Read file from workspace",
    "ReadBuildFile": "Read build file (pom.xml / build.gradle)",
    "LookupVulnerabilityFix": "Look up vulnerability fix (OSV / Maven)",
    "SubmitRemediationPlan": "Submit remediation plan (LLM draft)",
    "ValidateRemediationPlan": "Validate remediation plan",
    "RunOpenCode": "OpenCode: apply plan, test, draft PR",
    "ApplyDependencyFix": "Apply dependency version bumps",
    "CompileJava": "Compile Java project (skip tests)",
    "RunJavaTests": "Run Java unit tests",
    "DiagnoseTestFailures": "Diagnose test failures",
    "GitCommitAndPush": "Commit and push fix branch",
    "SummarizeRemediationForPR": "Summarize changes for pull request",
    "SubmitPullRequestBody": "Draft pull request description",
    "CreatePullRequest": "Create draft pull request",
    "VerifyFossaScan": "Verify FOSSA scan (wait for green Security Analysis)",
    "PlanRemediationActions": "Build rule-based remediation plan",
    "remediation_pipeline": "Run remediation pipeline",
    "fossa_orchestrator": "FOSSA orchestrator",
}

_RESULT_PREFIXES = (
    "Plan validation",
    "FOSSA verification",
    "Applied",
    "Tests ",
    "Created draft",
    "Committed",
    "Cloned",
    "Fetched",
    "Loaded",
    "Pushed",
    "Pull request",
    "ERROR",
    "FAILED",
    "PASSED",
    "SKIPPED",
)


def _short_tool_name(origin_str: str) -> str:
    if not origin_str:
        return "agent"
    return origin_str.split(".")[-1]


def _label_for_tool(tool_name: str) -> str:
    return TOOL_LABELS.get(tool_name, tool_name.replace("_", " "))


def _summarize_tool_output(output: str, max_lines: int = 4) -> str:
    if not output:
        return ""
    lines = [line.strip() for line in output.strip().splitlines() if line.strip()]
    if not lines:
        return ""
    head = lines[0]
    if len(lines) == 1:
        return head
    extra = min(len(lines) - 1, max_lines - 1)
    if extra <= 0:
        return head
    return head + "\n" + "\n".join(f"    {line}" for line in lines[1 : 1 + extra])


def _format_timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S")


class ConsoleProgressMessageProcessor(MessageProcessor):
    """Prints remediation pipeline progress to stderr as messages stream in."""

    def __init__(self, stream: Any = None, verbose: bool = False):
        self.stream = stream or sys.stderr
        self.verbose = verbose
        self._active_tools: set[str] = set()

    def _emit(self, line: str) -> None:
        print(line, file=self.stream, flush=True)

    def process_message(self, chat_message_dict: dict[str, Any], message_type: ChatMessageType):
        structure: dict[str, Any] | None = chat_message_dict.get("structure")
        text: str = chat_message_dict.get("text") or ""
        origin = chat_message_dict.get("origin")
        origin_str = Origination.get_full_name_from_origin(origin) or ""

        if message_type == ChatMessageType.AGENT_PROGRESS:
            self._handle_progress(structure, text, origin_str)
            return

        if structure is None:
            return

        if structure.get("tool_start"):
            self._handle_tool_start(structure, origin_str)
            return

        if structure.get("tool_end"):
            self._handle_tool_end(structure, origin_str)
            return

        if self.verbose and text.strip():
            tool = _short_tool_name(origin_str)
            self._emit(f"[{_format_timestamp()}] {tool}: {text.strip()[:200]}")

    def _handle_tool_start(self, structure: dict[str, Any], origin_str: str) -> None:
        tool_args = structure.get("tool_args") or {}
        tool_name = _short_tool_name(tool_args.get("origin_str") or origin_str)
        if tool_name in self._active_tools:
            return
        self._active_tools.add(tool_name)

        label = _label_for_tool(tool_name)
        repo_name = tool_args.get("repo_name")
        suffix = f" ({repo_name})" if repo_name else ""
        self._emit(f"[{_format_timestamp()}] → {label}{suffix}")

    def _handle_tool_end(self, structure: dict[str, Any], origin_str: str) -> None:
        tool_name = _short_tool_name(origin_str)
        self._active_tools.discard(tool_name)

        if structure.get("tool_error"):
            output = structure.get("tool_output") or structure.get("tool_error_message") or "tool error"
            summary = _summarize_tool_output(str(output), max_lines=3)
            self._emit(f"[{_format_timestamp()}] ✗ {tool_name} failed")
            if summary:
                for line in summary.splitlines():
                    self._emit(f"    {line}")
            return

        output = structure.get("tool_output")
        if not output or not isinstance(output, str):
            self._emit(f"[{_format_timestamp()}] ✓ {_label_for_tool(tool_name)}")
            return

        first_line = output.strip().splitlines()[0] if output.strip() else ""
        if any(first_line.startswith(prefix) for prefix in _RESULT_PREFIXES):
            summary = _summarize_tool_output(output, max_lines=5)
        else:
            summary = first_line[:160] + ("..." if len(first_line) > 160 else "")

        icon = "✓"
        if re.search(r"\b(FAILED|ERROR)\b", first_line, re.IGNORECASE):
            icon = "✗"
        elif re.search(r"\bSKIPPED\b", first_line, re.IGNORECASE):
            icon = "○"

        self._emit(f"[{_format_timestamp()}] {icon} {summary.splitlines()[0]}")
        for line in summary.splitlines()[1:]:
            self._emit(f"    {line.strip()}")

    def _handle_progress(
        self,
        structure: dict[str, Any] | None,
        text: str,
        origin_str: str,
    ) -> None:
        tool_name = _short_tool_name(origin_str)
        message = (text or "").strip()
        if structure:
            phase = structure.get("phase") or structure.get("step")
            detail = structure.get("detail") or structure.get("status")
            attempt = structure.get("attempt")
            parts = [p for p in (phase, detail, message) if p]
            if attempt is not None:
                parts.append(f"poll {attempt}")
            if parts:
                self._emit(f"[{_format_timestamp()}] … {tool_name}: {' — '.join(str(p) for p in parts)}")
                return
        if message:
            self._emit(f"[{_format_timestamp()}] … {tool_name}: {message[:200]}")
