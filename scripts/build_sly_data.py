#!/usr/bin/env python3
"""Emit default NSFlow / CLI sly_data JSON (dry_run, osv_lookup, full llm_config)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "neuro-san" / "coded_tools" / "fossa_remediation"))

from _config import build_default_sly_data  # noqa: E402


def main() -> int:
    try:
        payload = build_default_sly_data()
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
