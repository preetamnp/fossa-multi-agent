#!/usr/bin/env python3
"""Run payment-service FOSSA remediation without LLM (deterministic rule-based planner)."""

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

from _config import is_remediation_dry_run  # noqa: E402
from apply_dependency_fix import ApplyDependencyFix  # noqa: E402
from diagnose_test_failures import DiagnoseTestFailures  # noqa: E402
from fetch_fossa_findings import FetchFossaFindings  # noqa: E402
from github_pr import CreatePullRequest  # noqa: E402
from git_ops import GitCloneAndBranch, GitCommitAndPush  # noqa: E402
from java_build import CompileJava, RunJavaTests  # noqa: E402
from load_repo_config import LoadRepoConfig  # noqa: E402
from plan_remediation import PlanRemediationActions  # noqa: E402
from verify_fossa_scan import VerifyFossaScan  # noqa: E402

REPO = "payment-service"
MAX_TEST_HEAL = 3


async def run_step(name: str, tool, args: dict, sly_data: dict) -> str:
    print(f"→ {name}")
    result = await tool.async_invoke(args, sly_data)
    print(f"  {result}\n")
    return result


async def main() -> int:
    sly_data: dict = {"dry_run": is_remediation_dry_run()}
    print(f"=== Deterministic FOSSA remediation: {REPO} ===\n")
    if sly_data["dry_run"]:
        print("POC dry run: FOSSA verify skipped (REMEDIATION_DRY_RUN=false to require verify).\n")
    else:
        print("Production mode: FOSSA verify required before PR.\n")
    print("Uses rule-based PlanRemediationActions (LLM agent path uses remediation_strategist).\n")

    await run_step("LoadRepoConfig", LoadRepoConfig(), {}, sly_data)
    await run_step("FetchFossaFindings", FetchFossaFindings(), {"repo_name": REPO, "max_count": 20}, sly_data)
    await run_step("GitCloneAndBranch", GitCloneAndBranch(), {"repo_name": REPO}, sly_data)
    await run_step("PlanRemediationActions", PlanRemediationActions(), {"repo_name": REPO}, sly_data)

    if not (sly_data.get("remediation_plan") or {}).get(REPO):
        print("ERROR: No remediation plan could be built from FOSSA findings.")
        return 1

    await run_step("ApplyDependencyFix", ApplyDependencyFix(), {"repo_name": REPO}, sly_data)
    await run_step("CompileJava", CompileJava(), {"repo_name": REPO}, sly_data)
    compile = (sly_data.get("compile_results") or {}).get(REPO, {})
    if not compile.get("passed"):
        print("ERROR: Compile failed after applying dependency fixes.")
        return 1

    tests = RunJavaTests()
    diagnose = DiagnoseTestFailures()
    apply = ApplyDependencyFix()

    for attempt in range(1, MAX_TEST_HEAL + 1):
        result = await run_step("RunJavaTests", tests, {"repo_name": REPO}, sly_data)
        if (sly_data.get("test_results") or {}).get(REPO, {}).get("passed"):
            break

        if attempt == MAX_TEST_HEAL:
            print(f"ERROR: Tests still failing after {MAX_TEST_HEAL} self-heal attempts.")
            return 1

        await run_step("DiagnoseTestFailures", diagnose, {"repo_name": REPO}, sly_data)
        await run_step(
            "ApplyDependencyFix (test fixes)",
            apply,
            {"repo_name": REPO, "apply_test_fixes": True},
            sly_data,
        )
        await run_step("CompileJava", CompileJava(), {"repo_name": REPO}, sly_data)

    await run_step(
        "GitCommitAndPush",
        GitCommitAndPush(),
        {"repo_name": REPO, "commit_message": f"fix(fossa): remediate findings for {REPO}"},
        sly_data,
    )

    verify_result = await run_step(
        "VerifyFossaScan",
        VerifyFossaScan(),
        {"repo_name": REPO, "max_wait_seconds": int(os.environ.get("FOSSA_VERIFY_MAX_WAIT_SECONDS", "600"))},
        sly_data,
    )
    verify = (sly_data.get("fossa_verify") or {}).get(REPO, {})
    if verify.get("skipped"):
        pass
    elif not verify.get("passed"):
        print("ERROR: FOSSA branch verification did not pass. PR will not be created.")
        print(f"  {verify_result}")
        return 1

    await run_step("CreatePullRequest", CreatePullRequest(), {"repo_name": REPO, "draft": True}, sly_data)

    pr = (sly_data.get("pull_requests") or {}).get(REPO)
    if pr:
        print(f"SUCCESS — Draft PR: {pr.get('url')}")
        return 0

    print("Pipeline finished but no PR URL in sly_data. Check logs above.")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
