# Remediation policy gates (Mode B)

**Branch:** `feature/remediation-policy-gates`  
**Config:** [`config/remediation_policy.yaml`](../config/remediation_policy.yaml)

## Behavior

After `SubmitRemediationPlan` → `ValidateRemediationPlan`:

1. Existing checks still run (FOSSA versions, CVE coverage, licensing deferrals only).
2. Each action is classified as **AUTO** or **HUMAN** using the policy file.
3. **AUTO** actions are stored in `sly_data["remediation_plan"]` and applied by `ApplyDependencyFix`.
4. **HUMAN** actions go to `sly_data["human_review_queue"]` — not applied.
5. PR summary / default PR body lists the human queue.

Security findings on HUMAN deps are treated as **escalated** (not deferred licensing). They still count as “addressed” for coverage so validation can PASS while blocking auto-apply.

## Heuristics (defaults)

| Rule | Effect |
|------|--------|
| Major version bump (`2.x` → `3.x`) | HUMAN |
| `require_human_approval` coordinates / globs | HUMAN |
| `*-bom` / `*-dependencies` artifact globs | HUMAN |
| `remove` / `replace` | HUMAN |
| Patch/minor on allowlisted-safe deps | AUTO |

## Modes (`on_human_required.mode`)

| Mode | Behavior |
|------|----------|
| `hold_and_report` (default) | Split plan; apply AUTO; queue HUMAN |
| `fail_run` | Validation FAILS if any HUMAN action exists |

## Defense in depth

`ApplyDependencyFix` re-classifies and **refuses** any non-AUTO action even if it appears in the plan.

## Tests

```bash
python tests/test_remediation_policy.py
```

## Tune for a customer

Edit `config/remediation_policy.yaml`:

- Add coordinates to `require_human_approval`
- Set `major_bump_requires_approval: false` only if you accept major auto-bumps
- Optionally set `auto_apply_allowed` to a strict allowlist (everything else → HUMAN)
