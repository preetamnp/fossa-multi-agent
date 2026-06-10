# Sample repos for FOSSA POC

Two minimal Spring Boot 21 microservices with **intentional vulnerable dependencies** so FOSSA reports findings without a client environment.

| Directory | Stack | Demo findings |
|-----------|-------|---------------|
| `payment-service/` | Maven | 7 security CVEs + 2 license violations (see each repo README) |
| `user-service/` | Gradle | Same intentional deps as payment-service |

## Create GitHub + FOSSA (Step 2)

```bash
export GITHUB_ORG=your-github-username
./scripts/bootstrap_sample_repos.sh
```

Then follow **[../docs/FOSSA_SETUP.md](../docs/FOSSA_SETUP.md)**.

**Do not use in production.**
