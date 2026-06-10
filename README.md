# FOSSA Multi-Agent Remediation POC

Proactive proof-of-concept: **Neuro SAN** orchestrates **Mistral** (planning) and **Devstral** (coding) to remediate FOSSA findings across **2 Spring Boot microservices**, run tests, and open **draft PRs**.

## Architecture

```
fossa_orchestrator (Mistral Large)
    → fossa_analyst (FOSSA API CodedTools)
    → dispatch_coordinator
        → spring_boot_dev × 2 repos (Devstral)
            → git clone → fix deps → mvn/gradle test → draft PR
    → remediation_reporter (executive summary)
```

## Quick start

```bash
# 1. Bootstrap
chmod +x scripts/*.sh
./scripts/setup.sh

# 2. Create sample repos + FOSSA (no client repos needed)
export GITHUB_ORG=your-github-username
./scripts/bootstrap_sample_repos.sh
# Import repos in FOSSA — see docs/FOSSA_SETUP.md
python scripts/fetch_fossa_locators.py --write --github-org $GITHUB_ORG

# 3. Validate
./scripts/validate_setup.sh
python scripts/dry_run_fossa.py

# 4. Run (two terminals)
./scripts/run_server.sh          # terminal 1
./scripts/run_poc.sh             # terminal 2
```

## What you need from the client

| Item | Purpose |
|------|---------|
| FOSSA API token | Fetch vulnerabilities + remediation guidance |
| 2 pilot repo names | `payment-service`, `user-service` (or your picks) |
| FOSSA project locators | Map repo → FOSSA project |
| GitHub PAT | Clone, push branch, open draft PR |
| Mistral API key | Orchestration + Devstral coding |

## Project layout

```
config/repos.yaml              # 2-repo mapping (FOSSA ↔ GitHub ↔ build)
neuro-san/registries/
  fossa_remediation.hocon      # Agent network (HOCON)
  mistral_llm_info.hocon       # Mistral / Devstral model registry
neuro-san/coded_tools/fossa_remediation/
  fetch_fossa_findings.py      # FOSSA Issues + Remediation Guidance API
  git_ops.py                   # Clone, branch, commit, push
  java_build.py                # mvnw / gradlew test
  github_pr.py                 # Draft PR creation
scripts/                       # setup, validate, server, POC runner
docs/DEMO_SCRIPT.md            # 15-minute leadership demo script
docs/NEXT_STEPS.md             # Week 2–3 roadmap
```

## Demo prompt

```
Remediate critical and high FOSSA vulnerabilities for all configured pilot repos.
Open draft PRs only. Summarize PR links and test results.
```

## Guardrails (enterprise)

- Draft PRs only — no merge, no Cloud Run deploy
- Secrets in `.env` / sly_data — never in agent prompts
- Existing CI runs on PR branches unchanged
- Human SRE review before merge

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `FOSSA_API_TOKEN is not set` | Fill `.env` |
| `Remediation Guidance API ... not enabled` | Use Issues API findings only (POC still works) |
| `YOUR_ORG_ID` in repos.yaml | Replace with real FOSSA locators |
| Mistral model errors | Confirm `MISTRAL_API_KEY`; check [Mistral model names](https://docs.mistral.ai/getting-started/models/) |
| Tests fail after bump | Dev agent retries once; review `work/<repo>` locally |

## References

- [Neuro SAN](https://github.com/cognizant-ai-lab/neuro-san)
- [FOSSA Issues API](https://docs.fossa.com/docs/issues-api-configuration)
- [FOSSA Remediation Guidance](https://docs.fossa.com/docs/remediation-guidance)
- [Mistral Devstral](https://docs.mistral.ai/models/devstral-small-2505)
