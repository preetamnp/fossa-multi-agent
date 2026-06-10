#!/usr/bin/env python3
"""Verify FOSSA API connectivity for configured pilot repos (no agent run)."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = ROOT / ".venv" / "bin" / "python"
if VENV_PYTHON.exists() and Path(sys.executable).resolve() != VENV_PYTHON.resolve():
    os.execv(VENV_PYTHON, [str(VENV_PYTHON), *sys.argv])

sys.path.insert(0, str(ROOT / "neuro-san" / "coded_tools" / "fossa_remediation"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=True)

from fetch_fossa_findings import FetchFossaFindings  # noqa: E402
from load_repo_config import LoadRepoConfig  # noqa: E402


async def main() -> int:
    print("=== FOSSA dry run ===\n")

    sly_data: dict = {}
    config_tool = LoadRepoConfig()
    print(await config_tool.async_invoke({}, sly_data))
    print()

    if not os.environ.get("FOSSA_API_TOKEN"):
        print("ERROR: FOSSA_API_TOKEN not set in .env")
        return 1

    findings_tool = FetchFossaFindings()
    result = await findings_tool.async_invoke({"max_count": 5}, sly_data)
    print(result)
    print()

    findings = sly_data.get("fossa_findings") or []
    if findings:
        print(f"Ready for POC: {len(findings)} finding(s) retrieved.")
        return 0

    print("No findings returned. Check project locators in config/repos.yaml or severity filters.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
