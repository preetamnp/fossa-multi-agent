"""Progress reporting helpers for remediation coded tools."""

from __future__ import annotations

from typing import Any

from neuro_san.interfaces.agent_progress_reporter import AgentProgressReporter


async def report_progress(
    args: dict[str, Any],
    *,
    phase: str,
    detail: str = "",
    attempt: int | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Send a structured progress update to the streaming client."""
    reporter: AgentProgressReporter | None = args.get("progress_reporter")
    if reporter is None:
        return

    structure: dict[str, Any] = {"phase": phase}
    if detail:
        structure["detail"] = detail
    if attempt is not None:
        structure["attempt"] = attempt
    if extra:
        structure.update(extra)

    await reporter.async_report_progress(structure)
