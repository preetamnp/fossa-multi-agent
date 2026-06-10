#!/usr/bin/env python3
"""List FOSSA projects and optionally update config/repos.yaml with locators."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = ROOT / ".venv" / "bin" / "python"
if VENV_PYTHON.exists() and Path(sys.executable).resolve() != VENV_PYTHON.resolve():
    os.execv(VENV_PYTHON, [str(VENV_PYTHON), *sys.argv])

import argparse
import httpx
import yaml
from dotenv import load_dotenv

REPOS_YAML = ROOT / "config" / "repos.yaml"
POC_REPO_NAMES = {"payment-service", "user-service"}


def load_env() -> None:
    load_dotenv(ROOT / ".env", override=True)


def fossa_token() -> str:
    return (
        os.environ.get("FOSSA_API_TOKEN", "").strip()
        or os.environ.get("FOSSA_API_KEY", "").strip()
    )


def fetch_projects(token: str) -> list[dict]:
    headers = {"Authorization": f"Bearer {token}"}
    base = os.environ.get("FOSSA_API_BASE", "https://app.fossa.com/api").rstrip("/")
    projects: list[dict] = []
    offset = 0
    count = 50

    with httpx.Client(timeout=60.0) as client:
        while True:
            response = client.get(
                f"{base}/projects",
                headers=headers,
                params={"count": count, "offset": offset},
            )
            response.raise_for_status()
            batch = response.json()
            if not batch:
                break
            projects.extend(batch)
            if len(batch) < count:
                break
            offset += count

    return projects


def project_name(project: dict) -> str:
    return (
        project.get("title")
        or project.get("name")
        or project.get("loc", {}).get("name")
        or ""
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch FOSSA project locators for POC repos")
    parser.add_argument(
        "--write",
        action="store_true",
        help="Update config/repos.yaml with matched locators and GITHUB_ORG",
    )
    parser.add_argument(
        "--github-org",
        default=os.environ.get("GITHUB_ORG", ""),
        help="GitHub username/org for repos.yaml (default: GITHUB_ORG env var)",
    )
    args = parser.parse_args()

    load_env()
    token = fossa_token()
    if not token:
        print("ERROR: FOSSA_API_TOKEN not set in .env")
        print("  Tip: if using conda/base, ensure .env has FOSSA_API_TOKEN=your-token")
        return 1

    try:
        projects = fetch_projects(token)
    except httpx.HTTPError as exc:
        print(f"ERROR calling FOSSA API: {exc}")
        return 1

    if not projects:
        print("No FOSSA projects found. Import sample repos in FOSSA first.")
        print("See docs/FOSSA_SETUP.md")
        return 1

    print(f"Found {len(projects)} FOSSA project(s):\n")
    matches: dict[str, str] = {}

    def locator_rank(locator: str) -> tuple[int, str]:
        """Prefer GitHub-imported locators over CLI custom+ duplicates."""
        if locator.startswith("git+github.com/"):
            return (0, locator)
        if "/git+github.com/" in locator or locator.startswith("custom+"):
            return (1, locator)
        return (2, locator)

    for project in projects:
        name = project_name(project)
        locator = project.get("locator")
        if not locator and project.get("loc"):
            loc = project["loc"]
            fetcher = loc.get("fetcher") or "custom"
            package = loc.get("package") or loc.get("name") or ""
            revision = loc.get("revision")
            locator = f"{fetcher}+{package}" + (f"${revision}" if revision else "")

        title = name or "(untitled)"
        marker = "  ← POC match" if title in POC_REPO_NAMES else ""
        print(f"  {title}")
        print(f"    locator: {locator}{marker}")
        print()

        if title in POC_REPO_NAMES and isinstance(locator, str) and locator:
            existing = matches.get(title)
            if not existing or locator_rank(locator) < locator_rank(existing):
                matches[title] = locator

    if not matches:
        print("No payment-service / user-service projects found yet.")
        print("Import sample repos in FOSSA, wait for scan, then re-run this script.")
        return 0

    print("Matched POC projects:")
    for name, locator in matches.items():
        print(f"  {name}: {locator}")

    if not args.write:
        print("\nTo update config/repos.yaml automatically:")
        github_org = args.github_org or "YOUR_GITHUB_USER"
        print(f"  export GITHUB_ORG={github_org}")
        print("  python scripts/fetch_fossa_locators.py --write")
        return 0

    github_org = args.github_org
    if not github_org:
        print("ERROR: pass --github-org or set GITHUB_ORG for --write")
        return 1

    with REPOS_YAML.open(encoding="utf-8") as handle:
        config = yaml.safe_load(handle)

    for repo in config.get("repos", []):
        name = repo.get("name")
        if name in matches:
            repo.setdefault("fossa", {})["project_locator"] = matches[name]
            repo.setdefault("github", {})["org"] = github_org
            repo.setdefault("github", {})["repo"] = name

    with REPOS_YAML.open("w", encoding="utf-8") as handle:
        yaml.dump(config, handle, default_flow_style=False, sort_keys=False)

    print(f"\nUpdated {REPOS_YAML}")
    print("Run: python scripts/dry_run_fossa.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
