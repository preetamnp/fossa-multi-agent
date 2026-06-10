#!/usr/bin/env python3
"""Diagnose FOSSA branch revision indexing and v2/issues queries."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = ROOT / ".venv" / "bin" / "python"
if VENV_PYTHON.exists() and Path(sys.executable).resolve() != VENV_PYTHON.resolve():
    import os

    os.execv(VENV_PYTHON, [str(VENV_PYTHON), *sys.argv])

sys.path.insert(0, str(ROOT / "neuro-san" / "coded_tools" / "fossa_remediation"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=True)

import httpx

from _config import get_repo_by_name
from fossa_api import (
    fetch_vulnerability_issues,
    normalize_git_sha,
    resolve_branch_revision,
    revision_commit_sha,
)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="payment-service")
    parser.add_argument("--branch", required=True, help="Fix branch name in FOSSA/GitHub")
    parser.add_argument("--commit", help="Optional full or short git commit SHA")
    args = parser.parse_args()

    repo = get_repo_by_name(args.repo)
    if repo is None:
        print(f"Unknown repo: {args.repo}")
        return 1

    project = repo["fossa"]["project_locator"]
    commit = normalize_git_sha(args.commit) if args.commit else None

    async with httpx.AsyncClient(timeout=60) as client:
        entry = await resolve_branch_revision(client, project, args.branch, commit)
        if entry is None:
            print(f"Branch `{args.branch}` not found in GET /projects/.../revisions")
            print()
            print("Likely cause: FOSSA GitHub App has not scanned this branch yet.")
            print("  - Branch exists on GitHub but no draft PR was opened → no GitHub FOSSA scan.")
            print("  - `fossa analyze` CLI uploads to a separate custom+*/ project (not GitHub PR checks).")
            print()
            print("Fix: open a draft PR for this branch, wait ~2-5 min, then re-run this script.")
            if commit:
                print(f"  (searched for commit prefix `{commit[:12]}`)")
            return 1

        fossa_sha = revision_commit_sha(entry)
        print("Revision entry:")
        print(json.dumps(
            {
                "branch": args.branch,
                "revision": fossa_sha,
                "locator": entry.get("locator"),
                "resolved": entry.get("resolved"),
                "unresolved_issue_count": entry.get("unresolved_issue_count"),
                "source": entry.get("source"),
            },
            indent=2,
        ))

        vulns = await fetch_vulnerability_issues(client, project, fossa_sha, max_count=100)
        print(f"\nGET /v2/issues?category=vulnerability&scope[revision]={fossa_sha[:12]}...")
        print(f"  security vulnerabilities: {len(vulns)}")
        for item in vulns[:10]:
            print(f"  - {item.get('cve') or item.get('id')} severity={item.get('severity')}")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
