#!/usr/bin/env python3
"""Generate draw.io architecture diagrams for the FOSSA multi-agent POC."""

from __future__ import annotations

import html
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs" / "diagrams"


def esc(text: str) -> str:
    return html.escape(text, quote=True)


def cell(
    cid: str,
    value: str,
    x: float,
    y: float,
    w: float,
    h: float,
    style: str,
    parent: str = "1",
    vertex: bool = True,
) -> str:
    if vertex:
        return (
            f'<mxCell id="{cid}" value="{esc(value)}" style="{style}" vertex="1" parent="{parent}">'
            f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>'
        )
    return ""


def edge(eid: str, source: str, target: str, label: str = "", style: str | None = None) -> str:
    base = style or "edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;strokeColor=#0D9488;strokeWidth=2;"
    if label:
        base += "endArrow=block;endFill=1;"
        val = esc(label)
    else:
        val = ""
    return (
        f'<mxCell id="{eid}" value="{val}" style="{base}" edge="1" parent="1" source="{source}" target="{target}">'
        f'<mxGeometry relative="1" as="geometry"/></mxCell>'
    )


def wrap_diagram(name: str, page_w: int, page_h: int, body: str) -> str:
    return f"""<mxfile host="app.diagrams.net" modified="2026-08-30T00:00:00.000Z" agent="fossa-multi-agent" version="24.7.17" type="device">
  <diagram name="{esc(name)}" id="{uuid.uuid4()}">
    <mxGraphModel dx="1200" dy="800" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="{page_w}" pageHeight="{page_h}" math="0" shadow="0">
      <root>
        <mxCell id="0"/>
        <mxCell id="1" parent="0"/>
{body}
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
"""


# Styles
S_TITLE = "text;html=1;strokeColor=none;fillColor=none;align=left;verticalAlign=middle;whiteSpace=wrap;rounded=0;fontSize=18;fontStyle=1;fontColor=#0B1F3A;"
S_SUB = "text;html=1;strokeColor=none;fillColor=none;align=left;verticalAlign=middle;whiteSpace=wrap;rounded=0;fontSize=11;fontColor=#5A6A7A;"
S_PERSON = "shape=umlActor;verticalLabelPosition=bottom;verticalAlign=top;html=1;outlineConnect=0;fillColor=#0B1F3A;fontColor=#FFFFFF;strokeColor=#0B1F3A;"
S_SYSTEM = "rounded=1;whiteSpace=wrap;html=1;fillColor=#0D9488;strokeColor=#0B1F3A;fontColor=#FFFFFF;fontStyle=1;fontSize=12;"
S_EXT = "rounded=1;whiteSpace=wrap;html=1;fillColor=#F4F7F9;strokeColor=#5A6A7A;fontColor=#1A1A1A;fontSize=11;"
S_BOUNDARY = "rounded=0;whiteSpace=wrap;html=1;fillColor=none;strokeColor=#0B1F3A;dashed=1;dashPattern=8 8;strokeWidth=2;fontColor=#0B1F3A;fontStyle=1;fontSize=13;verticalAlign=top;align=left;spacingLeft=8;spacingTop=8;"
S_CONTAINER = "rounded=1;whiteSpace=wrap;html=1;fillColor=#DAE8FC;strokeColor=#6C8EBF;fontColor=#1A1A1A;fontSize=11;align=center;"
S_CONTAINER_TEAL = "rounded=1;whiteSpace=wrap;html=1;fillColor=#D5E8D4;strokeColor=#82B366;fontColor=#1A1A1A;fontSize=11;align=center;"
S_CONTAINER_AMBER = "rounded=1;whiteSpace=wrap;html=1;fillColor=#FFF2CC;strokeColor=#D6B656;fontColor=#1A1A1A;fontSize=11;align=center;"
S_GATE = "rounded=1;whiteSpace=wrap;html=1;fillColor=#F8CECC;strokeColor=#B85450;fontColor=#1A1A1A;fontSize=10;align=center;"
S_PHASE = "rounded=1;whiteSpace=wrap;html=1;fillColor=#0D9488;strokeColor=#0B1F3A;fontColor=#FFFFFF;fontStyle=1;fontSize=11;align=center;"
S_NOTE = "shape=note;whiteSpace=wrap;html=1;backgroundOutline=1;fillColor=#FFF9E6;strokeColor=#B8860B;fontSize=10;align=left;spacingLeft=6;"


def system_context() -> str:
    cells = [
        cell("t1", "C4 System Context — FOSSA Multi-Agent Remediation", 40, 20, 700, 40, S_TITLE),
        cell("t2", "Working POC · Neuro SAN + Mistral Devstral · Spring Boot pilot repos", 40, 55, 700, 30, S_SUB),
        cell("p_sre", "SRE / Platform Engineer", 80, 280, 60, 100, S_PERSON),
        cell("sys", "FOSSA Remediation System&#xa;[Software System]&#xa;&#xa;Automates CVE remediation&#xa;with policy gates", 320, 250, 280, 120, S_SYSTEM),
        cell("fossa", "FOSSA&#xa;[External]&#xa;Issues API + GitHub scan", 720, 180, 200, 80, S_EXT),
        cell("github", "GitHub&#xa;[External]&#xa;Repos + draft PRs", 720, 300, 200, 80, S_EXT),
        cell("mistral", "Mistral API&#xa;[External]&#xa;Devstral LLM", 720, 420, 200, 80, S_EXT),
        cell("nsflow", "NSFlow Studio&#xa;[External UI]&#xa;localhost:4173", 80, 450, 160, 70, S_EXT),
        edge("e1", "p_sre", "sys", "Remediate repo (natural language)"),
        edge("e2", "sys", "fossa", "Fetch CVEs / verify scan"),
        edge("e3", "sys", "github", "Clone · push · draft PR"),
        edge("e4", "sys", "mistral", "Plan + tool routing"),
        edge("e5", "p_sre", "nsflow", "Live demo / trace"),
        edge("e6", "nsflow", "sys", "HTTP :8080", "edgeStyle=orthogonalEdgeStyle;rounded=0;dashed=1;strokeColor=#5A6A7A;"),
        cell(
            "note1",
            "Human-in-the-loop: draft PR only — SRE reviews and merges",
            320, 400, 280, 50,
            S_NOTE,
        ),
    ]
    return wrap_diagram("1 - System Context", 1100, 600, "\n        ".join(cells))


def containers() -> str:
    cells = [
        cell("t1", "C4 Containers — FOSSA Remediation System", 40, 20, 900, 40, S_TITLE),
        cell("t2", "LLM decides · Python coded tools enforce · secrets in .env / sly_data", 40, 55, 900, 30, S_SUB),
        cell("boundary", "FOSSA Remediation System [Neuro SAN HTTP :8080]", 60, 100, 980, 520, S_BOUNDARY),
        cell("p_sre", "SRE", 20, 260, 50, 80, S_PERSON),
        cell("nsflow", "NSFlow / CLI Client", 20, 380, 50, 80, S_PERSON),
        # Row 1 agents
        cell("orch", "fossa_orchestrator&#xa;[Agent · Front man]&#xa;Delegates to pipeline", 120, 140, 200, 90, S_CONTAINER),
        cell("pipe", "remediation_pipeline&#xa;[Agent · LLM]&#xa;Mistral Devstral&#xa;Plans + invokes tools", 360, 140, 220, 90, S_CONTAINER_TEAL),
        cell("hocon", "fossa_remediation.hocon&#xa;[Config]&#xa;Workflow + instructions", 620, 140, 180, 90, S_CONTAINER_AMBER),
        cell("repos", "config/repos.yaml&#xa;[Config]&#xa;pilot repos + build cmds", 830, 140, 180, 90, S_CONTAINER_AMBER),
        # Layer: Policy
        cell("lp", "POLICY LAYER [Coded Tools]", 120, 260, 890, 30, "text;html=1;strokeColor=none;fillColor=none;fontStyle=1;fontColor=#B8860B;align=left;"),
        cell("fetch", "FetchFossaFindings", 120, 300, 130, 55, S_CONTAINER),
        cell("plan", "SubmitRemediationPlan", 270, 300, 150, 55, S_CONTAINER),
        cell("val", "ValidateRemediationPlan&#xa;[GATE]", 440, 300, 150, 55, S_GATE),
        cell("lookup", "LookupVulnerabilityFix", 610, 300, 140, 55, S_CONTAINER),
        cell("ctx", "PrepareRemediationContext", 770, 300, 160, 55, S_CONTAINER),
        # Layer: Execution
        cell("le", "EXECUTION LAYER [Coded Tools + workspace.py]", 120, 380, 890, 30, "text;html=1;strokeColor=none;fillColor=none;fontStyle=1;fontColor=#1A736E;align=left;"),
        cell("git", "GitCloneAndBranch", 120, 420, 130, 55, S_CONTAINER),
        cell("apply", "ApplyDependencyFix", 270, 420, 130, 55, S_CONTAINER),
        cell("compile", "CompileJava", 420, 420, 110, 55, S_CONTAINER),
        cell("test", "RunJavaTests", 550, 420, 110, 55, S_CONTAINER),
        cell("diag", "DiagnoseTestFailures", 680, 420, 140, 55, S_CONTAINER),
        cell("commit", "GitCommitAndPush", 840, 420, 130, 55, S_CONTAINER),
        # Layer: Ship + Verify
        cell("pr", "CreatePullRequest&#xa;draft only", 270, 500, 130, 55, S_CONTAINER),
        cell("verify", "VerifyFossaScan&#xa;[GATE · 0 sec vulns]", 440, 500, 150, 55, S_GATE),
        cell("workspace", "workspace.py&#xa;Clone root · Maven/Gradle", 620, 500, 160, 55, S_CONTAINER_AMBER),
        cell("workdir", "work/&#xa;[Local clone]", 810, 500, 120, 55, S_EXT),
        # External bottom
        cell("fossa", "FOSSA API", 120, 590, 120, 50, S_EXT),
        cell("github", "GitHub API", 270, 590, 120, 50, S_EXT),
        cell("mvn", "Maven / Gradle", 420, 590, 120, 50, S_EXT),
        # Edges
        edge("c1", "p_sre", "orch"),
        edge("c2", "nsflow", "orch", "", "edgeStyle=orthogonalEdgeStyle;dashed=1;strokeColor=#5A6A7A;"),
        edge("c3", "orch", "pipe"),
        edge("c4", "pipe", "fetch"),
        edge("c5", "pipe", "val"),
        edge("c6", "pipe", "apply"),
        edge("c7", "pipe", "verify"),
        edge("c8", "fetch", "fossa"),
        edge("c9", "commit", "github"),
        edge("c10", "verify", "fossa"),
        edge("c11", "git", "workdir"),
        edge("c12", "hocon", "pipe", "defines", "edgeStyle=orthogonalEdgeStyle;dashed=1;strokeColor=#D6B656;"),
        cell(
            "n_opencode",
            "Customer option: replace execution layer with OpenCode CLI&#xa;(plan still validated · VerifyFossaScan stays coded tool)",
            620, 590, 310, 50,
            S_NOTE,
        ),
    ]
    return wrap_diagram("2 - Containers", 1100, 700, "\n        ".join(cells))


def workflow() -> str:
    phases = [
        ("1 DISCOVER", "LoadRepoConfig\nFetchFossaFindings\nGitCloneAndBranch", 80, 120),
        ("2 PLAN", "PrepareContext\nFetchDependencyTree\nSubmitRemediationPlan", 280, 120),
        ("3 VALIDATE", "ValidateRemediationPlan\nCVE coverage\nFOSSA versions", 480, 120),
        ("4 EXECUTE", "ApplyDependencyFix\nCompileJava · RunJavaTests\nSelf-heal (max 3)", 680, 120),
        ("5 SHIP", "GitCommitAndPush\nCreatePullRequest (draft)\nVerifyFossaScan", 880, 120),
    ]
    cells = [
        cell("t1", "End-to-End Remediation Workflow", 40, 20, 700, 40, S_TITLE),
        cell("t2", "One prompt per repo · payment-service · user-service", 40, 55, 700, 30, S_SUB),
    ]
    prev = None
    for i, (title, body, x, y) in enumerate(phases):
        cid = f"ph{i}"
        cells.append(cell(cid, f"{title}&#xa;&#xa;{body}", x, y, 170, 130, S_PHASE))
        if prev:
            cells.append(edge(f"pe{i}", prev, cid))
        prev = cid

    cells.extend([
        cell("sre", "SRE", 40, 320, 50, 80, S_PERSON),
        cell("orch", "fossa_orchestrator", 140, 330, 140, 60, S_CONTAINER),
        cell("pipe", "remediation_pipeline", 320, 330, 160, 60, S_CONTAINER_TEAL),
        cell("tools", "Coded Tools (Python)", 520, 330, 140, 60, S_CONTAINER),
        cell("gh", "GitHub", 700, 330, 100, 60, S_EXT),
        cell("fossa", "FOSSA", 840, 330, 100, 60, S_EXT),
        edge("s1", "sre", "orch", "Remediate payment-service"),
        edge("s2", "orch", "pipe"),
        edge("s3", "pipe", "tools", "tool calls"),
        edge("s4", "tools", "gh", "draft PR"),
        edge("s5", "tools", "fossa", "verify"),
        edge("s6", "sre", "gh", "Review & merge", "edgeStyle=orthogonalEdgeStyle;strokeColor=#1E7A4A;strokeWidth=2;"),
        cell(
            "gates",
            "Policy gates: ValidateRemediationPlan · RunJavaTests · VerifyFossaScan · draft PR only",
            140, 430, 800, 40,
            S_NOTE,
        ),
        cell(
            "deploy",
            "Deploy: ./scripts/run_server.sh (:8080) · ./scripts/run_studio.sh (:4173) · ./scripts/run_poc.sh",
            140, 490, 800, 40,
            "rounded=1;whiteSpace=wrap;html=1;fillColor=#F4F7F9;strokeColor=#5A6A7A;fontSize=10;align=center;",
        ),
    ])
    return wrap_diagram("3 - Workflow", 1100, 600, "\n        ".join(cells))


def deployment() -> str:
    cells = [
        cell("t1", "Deployment View — Runtime Topology", 40, 20, 700, 40, S_TITLE),
        cell("host", "Developer / SRE Workstation", 80, 80, 920, 480, S_BOUNDARY),
        cell("t8080", "Neuro SAN Server&#xa;:8080&#xa;python -m neuro_san.service.main_loop", 120, 140, 220, 100, S_CONTAINER_TEAL),
        cell("t4173", "NSFlow Studio&#xa;:4173&#xa;run_studio.sh", 120, 280, 220, 80, S_CONTAINER),
        cell("env", ".env&#xa;FOSSA_API_TOKEN&#xa;GITHUB_TOKEN&#xa;MISTRAL_API_KEY", 120, 400, 220, 90, S_CONTAINER_AMBER),
        cell("coded", "Coded Tools&#xa;neuro-san/coded_tools/fossa_remediation/", 400, 140, 260, 100, S_CONTAINER),
        cell("hocon", "Agent Network&#xa;registries/fossa_remediation.hocon", 400, 280, 260, 80, S_CONTAINER_AMBER),
        cell("work", "Local workspace&#xa;work/&lt;repo&gt;/&#xa;git clone + fix branch", 400, 400, 260, 90, S_EXT),
        cell("logs", "Audit&#xa;logs/thinking_dir/&#xa;logs/server.log", 720, 140, 200, 100, S_CONTAINER),
        cell("fossa", "FOSSA Cloud&#xa;app.fossa.com", 720, 280, 200, 80, S_EXT),
        cell("github", "GitHub&#xa;repos + PR checks", 720, 400, 200, 80, S_EXT),
        cell("mistral", "Mistral API&#xa;api.mistral.ai", 720, 510, 200, 60, S_EXT),
        edge("d1", "t4173", "t8080", "HTTP client"),
        edge("d2", "t8080", "coded"),
        edge("d3", "coded", "work"),
        edge("d4", "coded", "fossa"),
        edge("d5", "coded", "github"),
        edge("d6", "t8080", "mistral"),
        edge("d7", "env", "t8080", "secrets", "edgeStyle=orthogonalEdgeStyle;dashed=1;strokeColor=#B8860B;"),
    ]
    return wrap_diagram("4 - Deployment", 1100, 650, "\n        ".join(cells))


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    files = {
        "01-system-context.drawio": system_context(),
        "02-containers.drawio": containers(),
        "03-workflow.drawio": workflow(),
        "04-deployment.drawio": deployment(),
    }
    for name, content in files.items():
        path = OUT_DIR / name
        path.write_text(content, encoding="utf-8")
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
