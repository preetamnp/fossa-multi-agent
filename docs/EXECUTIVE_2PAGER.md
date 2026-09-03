# FOSSA Multi-Agent Remediation — Executive 2-Pager

**File:** `docs/FOSSA_Remediation_Executive_2Pager.pptx` (2 slides · print or PDF as 2 pages)  
**Regenerate:** `python scripts/generate_executive_2pager.py`

---

## Page 1 — Problem + Architecture

### Manual vs multi-agent

```mermaid
flowchart TB
  subgraph manual [MANUAL]
    M1[Repo + CVEs] --> M2[Clone]
    M2 --> M3[Research versions]
    M3 --> M4[Edit pom / Gradle]
    M4 --> M5[Run tests]
    M5 --> M6[Open PR]
    M6 --> M7[Wait FOSSA]
    M7 --> M8[Repeat × 10–12 services]
  end

  subgraph agent [MULTI-AGENT]
    A1[One prompt] --> A2[Fetch FOSSA]
    A2 --> A3[Plan + validate]
    A3 --> A4[Apply + test]
    A4 --> A5[Draft PR]
    A5 --> A6[Verify FOSSA]
    A6 --> A7[SRE review]
  end
```

### System architecture

```mermaid
flowchart TB
  User[SRE / Platform] --> Orch[fossa_orchestrator]
  Orch --> Pipe[remediation_pipeline · Devstral]
  Pipe --> Policy[Fetch FOSSA · Plan · Validate]
  Policy --> Exec[Apply · Compile · Test · Git · PR]
  Exec --> Verify[VerifyFossaScan]
  Verify --> User

  FOSSA[(FOSSA API)] --- Policy
  GH[(GitHub)] --- Exec
  GH --- Verify
  Config[(repos.yaml)] --- Policy
```

---

## Page 2 — Workflow + Governance

### 5-phase workflow

```mermaid
flowchart LR
  P1[1 DISCOVER] --> P2[2 PLAN]
  P2 --> P3[3 VALIDATE]
  P3 --> P4[4 EXECUTE]
  P4 --> P5[5 VERIFY]
```

### Policy gates

| Gate | Blocks |
|------|--------|
| ValidateRemediationPlan | Wrong versions, skipped CVEs |
| RunJavaTests | PR when tests fail |
| VerifyFossaScan | Success with open security vulns |
| CreatePullRequest | Auto-merge (draft only) |

### Sequence

```mermaid
sequenceDiagram
  participant U as SRE
  participant O as Orchestrator
  participant P as Pipeline
  participant T as Coded Tools
  participant GH as GitHub
  participant F as FOSSA

  U->>O: Remediate payment-service
  O->>P: Start pipeline
  P->>T: Fetch · Plan · Validate · Apply · Test
  T->>GH: Draft PR
  T->>F: Verify branch scan
  P-->>U: PR URL + summary
  U->>GH: Review & merge
```
