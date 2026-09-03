# FOSSA Multi-Agent — draw.io Architecture Diagrams

Open these files in [diagrams.net](https://app.diagrams.net) (draw.io):

| File | C4 / view | Purpose |
|------|-----------|---------|
| [`01-system-context.drawio`](01-system-context.drawio) | System Context | SRE, remediation system, FOSSA, GitHub, Mistral, NSFlow |
| [`02-containers.drawio`](02-containers.drawio) | Containers | Agents, policy layer, execution layer, gates |
| [`03-workflow.drawio`](03-workflow.drawio) | Dynamic / workflow | 5 phases + sequence actors |
| [`04-deployment.drawio`](04-deployment.drawio) | Deployment | :8080 server, :4173 NSFlow, `.env`, `work/` |

## How to open

1. Go to https://app.diagrams.net
2. **File → Open from → Device**
3. Select any `.drawio` file from this folder

Or in VS Code / Cursor: install the **Draw.io Integration** extension and open the file directly.

## Export to Visio

1. Open diagram in draw.io
2. **File → Export as → VSDX…**
3. Open in Microsoft Visio

Other exports: **SVG**, **PNG**, **PDF** (good for slides).

## Regenerate from code

After architecture changes:

```bash
python scripts/generate_drawio_architecture.py
```

## Customize in draw.io

- **Arrange → Layout** — auto-align boxes
- **View → Layers** — split policy vs execution
- Add your **customer logo** and brand colors
- Use built-in **C4** shapes: **More Shapes → C4**

## Diagram set (recommended order for customer)

1. System Context — executive / security audience  
2. Containers — platform engineering review  
3. Workflow — demo walkthrough  
4. Deployment — ops / install discussion  
