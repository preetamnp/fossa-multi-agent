# Leadership demo script (15 minutes)

## Before the meeting

- [ ] `./scripts/validate_setup.sh` passes
- [ ] `python scripts/dry_run_fossa.py` returns real findings for both repos
- [ ] Neuro SAN server tested once end-to-end (even if only analyst step)
- [ ] Screen recording backup (~5 min) in case of live API issues
- [ ] FOSSA dashboard open in browser tab showing same CVEs

## Narrative arc

1. **Problem** (2 min) — 10–12 microservices/month, manual dependency bumps, repetitive CI work
2. **Approach** (3 min) — Multi-agent orchestration: plan (Mistral) + code (Devstral) + deterministic tools (FOSSA/git/CI)
3. **Live demo** (8 min) — Run workflow, show PRs
4. **Scale & guardrails** (2 min) — Parallel repos, draft PRs, existing CI unchanged

## Live demo steps

### Terminal 1 — start orchestrator

```bash
cd fossa-multi-agent
./scripts/run_server.sh
```

### Terminal 2 — trigger remediation

```bash
./scripts/run_poc.sh
```

### What to highlight while it runs

| Step | Agent | Talk track |
|------|-------|------------|
| Load repos | CodedTool | "Config-driven — no code deploy to add a microservice" |
| FOSSA fetch | fossa_analyst | "Pulls live findings from your FOSSA org" |
| Dispatch | dispatch_coordinator | "Each repo gets a coding agent — parallel at scale" |
| Fix + test | spring_boot_dev (Devstral) | "Repo-aware edits to pom.xml / Gradle, then mvn test" |
| PR | CreatePullRequest | "Draft PR for SRE review — no auto-merge" |
| Report | remediation_reporter | "Executive summary with links" |

### Show after completion

1. GitHub draft PR(s) with CVE context in description
2. Dependency diff in `pom.xml` or `build.gradle`
3. CI status on PR (if pipeline connected)
4. FOSSA dashboard — "rescan on PR branch clears finding"

## Slide: scale projection

| Today (POC) | Production target |
|-------------|-------------------|
| 2 repos | 12 repos |
| Manual trigger | Monthly FOSSA webhook / scheduler |
| Draft PR | Same + Slack summary to SRE |
| ~30 min | ~30 min wall-clock (parallel agents) |

## Q&A prep

**Why Neuro SAN vs a single coding agent?**  
Separation of concerns: orchestration, security API access, and coding are isolated. HOCON config lets SRE adjust workflow without redeploying Python.

**Why not FOSSA fossabot alone?**  
fossabot excels at dependency PR analysis. This adds cross-repo orchestration, custom CI integration, and client-specific workflow (Cloud Run, Java 21, draft PR policy).

**Is it safe for production?**  
POC is draft-PR-only. Phase 2 adds approval gates, audit logs, and rate limits.

**Cost?**  
Devstral Small is cost-efficient for dependency bumps; orchestration uses Mistral Large only for planning steps.

## If live demo fails

1. Show pre-recorded run
2. Walk through `fossa_remediation.hocon` agent graph
3. Run `python scripts/dry_run_fossa.py` to prove FOSSA connectivity
4. Show manual PR from a previous successful run
