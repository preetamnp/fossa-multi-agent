# Neuro SAN Future Backlog — FOSSA Multi-Agent Remediation

**Status:** Future plan only. **Productionizing the current POC is the priority.**  
**Baseline branch:** `fossa-before-open-code` (`e055da3` — workspace-backed coded tools, no OpenCode)  
**Installed neuro-san:** ~0.6.58 (pin in `requirements.txt`: `neuro-san>=0.6.50`)  
**Upstream (as of Aug 2026):** ~0.6.98  

Do **not** pull these items into the critical path until Phase 0–2 of productionization are done (stable runs, secrets, runbook, ≥80% success on pilots).

Related docs:

- Production / evaluation steps: conversation plan (evaluate → harden → scale → deploy)
- Architecture diagrams: [`docs/diagrams/README.md`](diagrams/README.md)
- Executive 2-pager: [`docs/FOSSA_Remediation_Executive_2Pager.pptx`](FOSSA_Remediation_Executive_2Pager.pptx)

---

## Priority order

```text
NOW     Productionize POC
        (gates, secrets, runbook, 80% success, Cloud Run/VM)

THEN    Tier A: upgrade + Langfuse + light middleware + tool path lock + CI tests

THEN    Tier B: model split + tool-selector middleware + schedule/webhook + MCP expose

LATER   Tier C: customer coding agent / enterprise MCP / auth / multi-tenant
```

---

## What’s new / strong in Neuro SAN (relevant to this project)

| Capability | What it is | Why it matters for FOSSA |
|------------|------------|--------------------------|
| **Agent middleware (HOCON)** | Cross-cutting hooks around model/tool calls | Logging, PII redaction, retries, tool filtering without rewriting agents |
| **MCP (server + client)** | Expose your network as MCP tools; call external MCP servers | Trigger from CI / ServiceNow / OpenCode; pull enterprise tools |
| **Observability** | Langfuse / LangSmith / Phoenix / HoneyHive | Production traces per agent + tool |
| **Load / regression test framework** | Record/playback LLM + load tests | Prove reliability before monthly batch |
| **AGENT_TOOL_PATH_ONLY** | Restrict coded-tool resolution | Security hardening in prod |
| **Event / periodic agents** | Scheduled agent runs | Monthly FOSSA cycle without a custom cron wrapper |
| **Multi-instance / storage** | S3/Azure reservations, instance ids, single-leader checks | Scale beyond one laptop |
| **Fallback / per-agent LLMs** | Different models + fallbacks in config | Cheap orchestrator, strong planner |
| **BYOK + auth (OpenFGA)** | Client-provided keys; network auth | Customer-owned tokens / tenancy |
| **sly_data policies** | Explicit allowlists to/from externals | Safer when wiring OpenCode / MCP |
| **Assessor / data-driven tests** | Classify failure modes | Continuous evaluation of the agent network |
| **Repo split coming** | `neuro_san.service` → separate package | Plan upgrades carefully for Cloud Run |

References:

- [Neuro SAN README](https://github.com/cognizant-ai-lab/neuro-san)
- [Middleware blog](https://www.cognizant.com/us/en/ai-lab/blog/neuro-san-agent-middleware)
- [Apache 2.0 & MCP update](https://www.cognizant.com/us/en/ai-lab/blog/neuro-san-updates-apache-2-mcp-integration)
- [Releases](https://github.com/cognizant-ai-lab/neuro-san/releases)

---

## Tier A — High value, low risk (after production stabilizes)

| # | Item | Action |
|---|------|--------|
| A1 | **Upgrade neuro-san** | Bump 0.6.58 → current on a branch; re-run evaluation scorecard |
| A2 | **Observability (Langfuse)** | One trace per remediation: plan → validate → apply → test → PR → verify |
| A3 | **Middleware on `remediation_pipeline`** | Tool-call audit / structured logging; optional PII redaction; summarization for long heal loops |
| A4 | **`AGENT_TOOL_PATH_ONLY=true`** | Lock coded-tool resolution in production |
| A5 | **Data-driven agent tests** | HOCON/network tests + optional LLM record/playback for CI |

**Exit gate:** Prod runs unchanged; traces and CI tests exist; upgrade validated.

---

## Tier B — Effectiveness / scale

| # | Item | Action |
|---|------|--------|
| B1 | **Per-agent LLM split** | Orchestrator small/cheap; pipeline stronger (Devstral 2 / Claude Sonnet); fallbacks if primary LLM is down |
| B2 | **`LlmConfigToolSelectorMiddleware`** | Shrink ~19-tool list to phase-relevant tools (fewer tokens, fewer wrong-tool calls) |
| B3 | **Periodic / event agent** | Monthly schedule or FOSSA webhook → start remediation |
| B4 | **MCP server mode** | Expose `fossa_remediation` so GitHub Actions / ServiceNow / portal can call it as a tool |
| B5 | **Parallel multi-repo** | One invocation per repo with `work/<repo>` isolation; load-test with Neuro SAN load framework |

**Exit gate:** Monthly cycle runnable without manual `./scripts/run_poc.sh` babysitting.

---

## Tier C — Ecosystem / customer fit (later)

| # | Item | Action |
|---|------|--------|
| C1 | **MCP client** | GitHub/Jira/Slack MCP where useful; keep FOSSA + `VerifyFossaScan` as coded tools |
| C2 | **OpenCode / Claude Code as execution worker** | Only after policy path is prod-proven (plan/validate/verify stay Neuro SAN) |
| C3 | **External agent networks / A2A** | Separate “heal” or “PR author” network if the graph grows |
| C4 | **BYOK + OpenFGA** | Customer API keys and who can run which network |
| C5 | **Temporary networks (reservations)** | Short-lived per-run networks for isolation (advanced) |

---

## Explicitly do **not** pull in before production

| Tempting feature | Why wait |
|------------------|----------|
| OpenCode / MCP coding agents | Adds non-determinism; reverted off the production baseline |
| Large middleware stack | Harder to debug first prod failures |
| Multi-cloud reservation storage | Overkill for 2–12 repos on one service |
| Full Assessor + LLM-as-judge suite | Needs a stable happy path first |
| Jumping to bleeding-edge mid-prod cutover | Upgrade on a branch after baseline metrics |

---

## Bottom line

Neuro SAN’s newest leverage for this project is not more agents — it is **middleware, observability, MCP exposure, scheduled runs, and test/load infrastructure** around the pipeline already built.

- **Production first** = make the current 2-agent + coded-tool path boring and reliable.  
- **Future effectiveness** = middleware + tracing + stronger planner model + MCP/scheduler — without weakening `ValidateRemediationPlan` / `VerifyFossaScan`.

---

## Checklist (printable)

```
AFTER PROD STABLE
[ ] A1 Upgrade neuro-san on branch + re-eval
[ ] A2 Langfuse (or equivalent) tracing
[ ] A3 Light middleware (audit / PII / summarize)
[ ] A4 AGENT_TOOL_PATH_ONLY in prod
[ ] A5 Data-driven agent tests in CI

SCALE
[ ] B1 Per-agent LLM + fallbacks
[ ] B2 Tool-selector middleware
[ ] B3 Schedule / FOSSA webhook
[ ] B4 MCP expose fossa_remediation
[ ] B5 Parallel multi-repo + load test

LATER
[ ] C1 Enterprise MCP clients
[ ] C2 OpenCode/Claude Code worker (optional)
[ ] C3 External / A2A networks
[ ] C4 BYOK + OpenFGA
[ ] C5 Temporary networks
```
