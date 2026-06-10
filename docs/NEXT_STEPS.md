# Next steps — your proactive POC roadmap

## This week (you)

### Day 1–2: Credentials and config

1. Request from client (or use internal pilots):
   - FOSSA API token (Settings → API)
   - GitHub fine-grained PAT: `contents:write`, `pull_requests:write` on 2 repos
   - Mistral API key from [console.mistral.ai](https://console.mistral.ai)
2. Update `config/repos.yaml`:
   - Replace `your-org`, repo names, and `custom+YOUR_ORG_ID/...` locators
   - Confirm Maven vs Gradle and test commands match the repos
3. Run:
   ```bash
   ./scripts/setup.sh
   ./scripts/validate_setup.sh
   python scripts/dry_run_fossa.py
   ```

### Day 3–4: First end-to-end repo

4. Pick the **easier** repo first (usually a direct dependency bump with green tests)
5. Run full POC; if Devstral struggles with edits, manually verify one bump pattern and add a hint to `spring_boot_dev` instructions in `fossa_remediation.hocon`
6. Confirm draft PR + CI triggers on your GitHub org

### Day 5: Second repo + demo prep

7. Repeat for second repo
8. Rehearse `docs/DEMO_SCRIPT.md` once with screen share
9. Capture metrics: time to PR, findings fixed, CI pass rate

## Week 2: Harden for client presentation

- [ ] Add FOSSA project locator discovery script (optional)
- [ ] Handle Remediation Guidance 403 gracefully (already in CodedTool)
- [ ] Add retry limit logging for failed tests
- [ ] Optional: Neuro SAN Studio web UI for visual agent graph during demo

## Week 3: Phase 2 proposal deck

Pitch items for leadership:

| Capability | Business value |
|------------|----------------|
| Parallel 12-repo runs | Days → hours per FOSSA cycle |
| Scheduled monthly trigger | Proactive before audit deadlines |
| Slack / email report | SRE visibility without dashboard diving |
| Cloud Run Job wrapper | Fits existing GCP estate |
| Audit trail in sly_data | Compliance-friendly agent actions |

## Information to collect at client discovery call

1. Git host: GitHub Enterprise or GitLab?
2. Build: Maven, Gradle, or mixed? Parent BOM name?
3. FOSSA: cloud or self-hosted? Remediation Guidance enabled?
4. CI: GitHub Actions, Jenkins, Cloud Build?
5. Policy: draft PR only? Required reviewers? FOSSA rescan gate on PR?
6. Typical finding types: direct deps only, or frequent transitive/BOM changes?

## Your immediate checklist (printable)

```
[ ] config/repos.yaml — 2 real repos configured
[ ] .env — FOSSA + Mistral + GitHub tokens
[ ] dry_run_fossa.py — returns findings
[ ] run_server.sh + run_poc.sh — one repo PR opened
[ ] Second repo PR opened
[ ] DEMO_SCRIPT rehearsed
[ ] Leadership deck with architecture diagram
```
