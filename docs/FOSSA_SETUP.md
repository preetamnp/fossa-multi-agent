# FOSSA setup for POC sample repos

This guide walks you through creating GitHub repos, registering them in FOSSA, and wiring them into `config/repos.yaml`.

## Overview

```
sample-repos/payment-service  ──push──▶  GitHub  ──import──▶  FOSSA project
sample-repos/user-service     ──push──▶  GitHub  ──import──▶  FOSSA project
                                      │
                                      └── locators ──▶ config/repos.yaml
```

Each sample repo ships with **intentionally vulnerable** dependencies so FOSSA will report findings without waiting for a client environment.

| Repo | Build | Vulnerable deps (demo) |
|------|-------|-------------------------|
| payment-service | Maven | commons-text 1.9, snakeyaml 1.33 |
| user-service | Gradle | commons-text 1.9, snakeyaml 1.33 |

---

## Prerequisites

- [FOSSA account](https://app.fossa.com) (free trial works for POC)
- [FOSSA API token](https://app.fossa.com/account/settings) → add to `.env` as `FOSSA_API_TOKEN`
- [GitHub account](https://github.com) + `GITHUB_TOKEN` in `.env`
- [GitHub CLI](https://cli.github.com/) (`gh`) — recommended for one-command repo creation
- Java 21 installed locally
- Optional: [FOSSA CLI](https://github.com/fossas/fossa-cli) for local scans

---

## Step A — Create GitHub repositories

### Option 1: Automated (recommended)

From the project root:

```bash
# Set your GitHub username or org
export GITHUB_ORG=your-github-username

./scripts/bootstrap_sample_repos.sh
```

This script will:

1. Initialize git in both sample repos
2. Create **public** GitHub repos `payment-service` and `user-service` (via `gh`)
3. Push `main` branch
4. Print next steps for FOSSA

### Option 2: Manual

For each repo under `sample-repos/`:

```bash
cd sample-repos/payment-service
git init
git add .
git commit -m "Initial commit: FOSSA POC payment-service"
git branch -M main
git remote add origin https://github.com/YOUR_USER/payment-service.git
git push -u origin main
```

Repeat for `sample-repos/user-service`.

---

## Step B — Register projects in FOSSA

Use **GitHub import only** for this POC. Do not run `fossa analyze` on pilot repos — it creates a duplicate FOSSA project.

| FOSSA UI icon | Source | Locator example | Use for POC? |
|---------------|--------|-----------------|--------------|
| Truck / GitHub | GitHub App import | `git+github.com/you/payment-service` | **Yes** — PR checks + agent API |
| Cloud upload | `fossa analyze` CLI | `custom+62452/git+github.com/you/payment-service` | **No** — delete if created by mistake |

### One project per repo (avoid duplicates)

1. **Import via GitHub** (Step B below) — keep this project.
2. **Do not run** `fossa analyze` on payment-service / user-service (README examples are for local experiments only).
3. If you already have two `payment-service` rows in FOSSA: open the **cloud-upload** project → **Settings** → delete/archive it. Keep the **GitHub/truck** project.
4. Confirm `config/repos.yaml` uses the `git+github.com/...` locator (not `custom+...`):

```bash
python scripts/fetch_fossa_locators.py   # prefers git+github locators when both exist
```

You can use the **FOSSA web UI** or skip CLI entirely for the agent POC.

### Option 1: FOSSA web UI (easiest for first-time setup)

1. Log in to [app.fossa.com](https://app.fossa.com)
2. Click **Add Project** → **Import from GitHub**
3. Authorize GitHub if prompted
4. Select `payment-service` → import
5. Repeat for `user-service`
6. Wait for the first analysis to complete (usually 2–5 minutes per repo)

### Option 2: FOSSA CLI (not recommended for this POC)

> **Warning:** `fossa analyze` creates a **second** FOSSA project (`custom+*/git+github.com/...`) that does not drive GitHub PR checks. Use Option 1 only unless you need local CLI experiments.

Install CLI:

```bash
# macOS
brew install fossa

# or curl installer from https://github.com/fossas/fossa-cli
```

Authenticate (uses `FOSSA_API_TOKEN`):

```bash
export FOSSA_API_KEY="$FOSSA_API_TOKEN"   # CLI uses FOSSA_API_KEY

cd sample-repos/payment-service
fossa analyze --project payment-service
fossa test

cd ../user-service
fossa analyze --project user-service
fossa test
```

Each repo already contains a `.fossa.yml` with `project.name` matching the repo name.

---

## Step C — Find FOSSA project locators

FOSSA locators look like: `custom+<orgId>/payment-service`

### Option 1: From the FOSSA UI

1. Open the project in FOSSA
2. Check the browser URL — it often contains the locator or project ID
3. Or go to **Project Settings** → note the project identifier

### Option 2: FOSSA API (automated)

With `FOSSA_API_TOKEN` in `.env`:

```bash
python scripts/fetch_fossa_locators.py
```

This lists FOSSA projects and prints the exact `project_locator` values to paste into `config/repos.yaml`.

Example API call manually:

```bash
curl -s -H "Authorization: Bearer $FOSSA_API_TOKEN" \
  "https://app.fossa.com/api/projects?count=50" | python -m json.tool
```

Look for entries where `title` matches `payment-service` / `user-service`. The `locator` field is what you need.

---

## Step D — Update `config/repos.yaml`

Edit `config/repos.yaml`:

```yaml
repos:
  - name: payment-service
    github:
      org: your-github-username      # ← your GitHub user or org
      repo: payment-service
    fossa:
      project_locator: "custom+12345/payment-service"   # ← from Step C

  - name: user-service
    github:
      org: your-github-username
      repo: user-service
    fossa:
      project_locator: "custom+12345/user-service"
```

Or run the helper (after locators are known):

```bash
export GITHUB_ORG=your-github-username
python scripts/fetch_fossa_locators.py --write
```

---

## Step E — Verify FOSSA findings

```bash
./scripts/validate_setup.sh
python scripts/dry_run_fossa.py
```

Expected output (similar):

```
Found 2 vulnerability issue(s):
- [payment-service] CVE-2022-42889 package=commons-text severity=high
- [user-service] CVE-2022-42889 package=commons-text severity=high
```

If zero findings:

- Confirm FOSSA analysis finished (green check in UI)
- Confirm `project_locator` in `repos.yaml` matches FOSSA exactly
- Try lowering severity filter in `dry_run_fossa.py` or wait for scan completion

---

## Step F — Run the agent POC

```bash
# Terminal 1
./scripts/run_server.sh

# Terminal 2
./scripts/run_poc.sh
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `gh: command not found` | Install GitHub CLI or create repos manually in github.com |
| FOSSA can't see GitHub repos | Re-authorize GitHub integration in FOSSA settings |
| `403` on Remediation Guidance | Normal on trial — Issues API still works for POC |
| Two `payment-service` projects in FOSSA | CLI `fossa analyze` created a duplicate — delete the cloud-upload project; keep GitHub/truck project; never run CLI analyze on pilot repos |
| Maven/Gradle wrapper missing | Run `./scripts/bootstrap_sample_repos.sh` (generates wrappers) |
| Tests fail locally | Ensure Java 21: `java -version` |

---

## Security note

These repos contain **known vulnerable dependencies on purpose**. Keep them:

- Public only if acceptable for a demo org
- Never deployed to Cloud Run or production
- Fixed by the agent POC (bump commons-text → 1.10.0+, snakeyaml → 2.0+)
