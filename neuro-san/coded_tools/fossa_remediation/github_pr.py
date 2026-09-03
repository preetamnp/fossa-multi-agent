"""Create GitHub pull requests for FOSSA remediation branches."""

from __future__ import annotations

from typing import Any

import httpx

from neuro_san.interfaces.coded_tool import CodedTool

from _config import get_repo_by_name, github_headers, is_remediation_dry_run


class CreatePullRequest(CodedTool):
    """Open a draft PR from the fix branch to the default branch."""

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> Any:
        repo_name = args.get("repo_name")
        title = args.get("title") or (sly_data.get("pull_request_drafts") or {}).get(repo_name, {}).get("title")
        title = title or f"fix(fossa): security and license remediation — {repo_name}"
        body = args.get("body") or (sly_data.get("pull_request_drafts") or {}).get(repo_name, {}).get("body")
        body = body or self._default_body(repo_name, sly_data)
        draft = bool(args.get("draft", True))
        require_verify = args.get("require_verify")
        if require_verify is None:
            require_verify = not bool(args.get("trigger_fossa_scan"))

        repo = get_repo_by_name(repo_name)
        if repo is None:
            return f"Unknown repo_name: {repo_name}"

        branch_name = (sly_data.get("repo_branches") or {}).get(repo_name)
        if not branch_name:
            return f"No branch found for {repo_name}. Run GitCloneAndBranch and GitCommitAndPush first."

        verify = (sly_data.get("fossa_verify") or {}).get(repo_name)
        dry_run = is_remediation_dry_run(sly_data)
        if require_verify and not dry_run and (not verify or not verify.get("passed")):
            return (
                f"FOSSA verification not passed for {repo_name}. "
                "Run VerifyFossaScan after opening a draft PR (GitHub App scan), "
                "or set REMEDIATION_DRY_RUN=true for POC runs that skip verify."
            )

        existing = (sly_data.get("pull_requests") or {}).get(repo_name)
        if existing and existing.get("url"):
            return f"PR already open for {repo_name}: {existing['url']}"

        gh = repo["github"]
        url = f"https://api.github.com/repos/{gh['org']}/{gh['repo']}/pulls"
        payload = {
            "title": title,
            "body": body,
            "head": branch_name,
            "base": gh.get("default_branch", "main"),
            "draft": draft,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, headers=github_headers(), json=payload)
            if response.status_code == 422:
                existing_url = await self._find_existing_pr(client, gh, branch_name)
                if existing_url:
                    sly_data.setdefault("pull_requests", {})[repo_name] = {"url": existing_url}
                    return (
                        f"PR already exists for {repo_name} branch `{branch_name}`: {existing_url}. "
                        "Use VerifyFossaScan to wait for GitHub FOSSA scan."
                    )
                return f"PR may already exist for {repo_name}: {response.text}"
            response.raise_for_status()
            pr = response.json()

        sly_data.setdefault("pull_requests", {})[repo_name] = {
            "number": pr.get("number"),
            "url": pr.get("html_url"),
        }

        return f"Opened PR #{pr.get('number')} for {repo_name}: {pr.get('html_url')}"

    @staticmethod
    async def _find_existing_pr(
        client: httpx.AsyncClient,
        gh: dict[str, Any],
        branch_name: str,
    ) -> str | None:
        url = f"https://api.github.com/repos/{gh['org']}/{gh['repo']}/pulls"
        response = await client.get(
            url,
            headers=github_headers(),
            params={"head": f"{gh['org']}:{branch_name}", "state": "open"},
        )
        if response.status_code != 200:
            return None
        pulls = response.json()
        if pulls and isinstance(pulls, list):
            return pulls[0].get("html_url")
        return None

    @staticmethod
    def _default_body(repo_name: str, sly_data: dict[str, Any]) -> str:
        findings = [
            f for f in (sly_data.get("fossa_findings") or []) if f.get("repo") == repo_name
        ]
        branch_name = (sly_data.get("repo_branches") or {}).get(repo_name, f"fix/fossa-auto-{repo_name}")
        lines = [
            "## FOSSA remediation (AI agent POC)",
            "",
            f"Automated dependency updates on branch `{branch_name}` to address FOSSA findings.",
            "",
            "### Security findings addressed",
        ]
        vulns = [f for f in findings if f.get("category") != "licensing"]
        licenses = [f for f in findings if f.get("category") == "licensing"]

        if vulns:
            for item in vulns:
                lines.append(
                    f"- **{item.get('cve', 'CVE')}** — `{item.get('package', 'package')}` "
                    f"({item.get('severity', 'severity')})"
                )
        else:
            lines.append("- Version bumps for known vulnerable direct dependencies.")

        lines.extend(["", "### License findings addressed"])
        if licenses:
            for item in licenses:
                lines.append(
                    f"- **{item.get('license', 'license')}** — `{item.get('package', 'package')}` "
                    f"({item.get('severity', 'severity')})"
                )
        else:
            lines.append("- Removed/replaced dependencies with non-compliant licenses.")

        fixes = (sly_data.get("dependency_fixes") or {}).get(repo_name) or []
        if fixes:
            lines.extend(["", "### Changes applied", ""])
            for action in fixes:
                lines.append(f"- {action}")

        meta = (sly_data.get("remediation_plan_meta") or {}).get(repo_name) or {}
        if meta.get("strategy_summary"):
            lines.extend(["", "### Agent strategy", meta["strategy_summary"]])

        human_queue = (sly_data.get("human_review_queue") or {}).get(repo_name) or []
        if human_queue:
            lines.extend(
                [
                    "",
                    "### Requires human approval (not auto-applied)",
                    "These changes were blocked by remediation policy (breaking / BOM / denylist):",
                    "",
                ]
            )
            for item in human_queue:
                coord = f"{item.get('group_id')}:{item.get('artifact_id')}"
                detail = item.get("target_version") or item.get("replacement_coordinate") or item.get("action")
                reason = item.get("risk_reason") or "human_required"
                lines.append(f"- `{coord}` → `{detail}` — {reason}")

        verify = (sly_data.get("fossa_verify") or {}).get(repo_name) or {}
        if verify.get("passed"):
            lines.extend(
                [
                    "",
                    "### FOSSA branch verification",
                    f"- Passed on revision `{verify.get('revision', branch_name)}`",
                    f"- Critical/high vulnerabilities on branch: **{verify.get('vulnerability_count', 0)}**",
                ]
            )
        elif verify.get("skipped"):
            lines.extend(
                [
                    "",
                    "### FOSSA branch verification",
                    "- Skipped (POC dry run — set `REMEDIATION_DRY_RUN=false` and re-run verify before merge)",
                ]
            )

        lines.extend(
            [
                "",
                "### Checklist",
                "- [x] FOSSA rescan passed on fix branch"
                if verify.get("passed")
                else "- [ ] FOSSA rescan passed on fix branch (skipped in POC dry run)",
                "- [ ] CI pipeline green",
                "- [ ] SRE review",
                "",
                "_Generated by Neuro SAN multi-agent FOSSA remediation POC._",
            ]
        )
        return "\n".join(lines)
