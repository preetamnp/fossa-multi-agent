#!/usr/bin/env python3
"""One-shot FOSSA remediation client with live console progress."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = ROOT / ".venv" / "bin" / "python"
if VENV_PYTHON.exists() and Path(sys.executable).resolve() != VENV_PYTHON.resolve():
    os.execv(VENV_PYTHON, [str(VENV_PYTHON), *sys.argv])

sys.path.insert(0, str(ROOT / "scripts"))

from console_progress import ConsoleProgressMessageProcessor  # noqa: E402

from neuro_san.client.agent_session_factory import AgentSessionFactory  # noqa: E402
from neuro_san.client.streaming_input_processor import StreamingInputProcessor  # noqa: E402
from neuro_san.internals.messages.origination import Origination  # noqa: E402


def _redact_sly_data(sly_data: dict[str, Any]) -> dict[str, Any]:
    redacted = json.loads(json.dumps(sly_data))
    llm_config = redacted.get("llm_config")
    if isinstance(llm_config, dict) and llm_config.get("openai_api_key"):
        key = llm_config["openai_api_key"]
        llm_config["openai_api_key"] = f"***{key[-4:]}" if len(key) > 4 else "***"
    return redacted


def main() -> int:
    parser = argparse.ArgumentParser(description="Run FOSSA remediation with live progress.")
    parser.add_argument("--agent", default="fossa_remediation")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--sly_data", default="{}")
    parser.add_argument("--verbose", action="store_true", help="Print extra agent messages")
    parser.add_argument("--no-progress", action="store_true", help="Disable live progress lines")
    args = parser.parse_args()

    sly_data = json.loads(args.sly_data)
    chat_filter = {"chat_filter_type": "MAXIMAL"}

    factory = AgentSessionFactory()
    session = factory.create_session("http", args.agent, hostname=args.host, port=args.port)

    empty: dict[str, Any] = {}
    response = session.function(empty)
    if response is None:
        print("ERROR: Could not reach agent server. Is ./scripts/run_server.sh running?", file=sys.stderr)
        return 1

    function = response.get("function", empty)
    initial_prompt = function.get("description")
    if initial_prompt:
        print(initial_prompt)

    print(f"Config: {json.dumps(_redact_sly_data(sly_data), sort_keys=True)}")
    print("")
    print("Live progress (pipeline steps stream as they run):")
    print("─" * 60)

    processors = []
    if not args.no_progress:
        processors.append(ConsoleProgressMessageProcessor(verbose=args.verbose))

    input_processor = StreamingInputProcessor(session=session)
    for processor in processors:
        input_processor.get_message_processor().add_processor(processor)

    state: dict[str, Any] = {
        "user_input": args.prompt,
        "sly_data": sly_data,
        "chat_filter": chat_filter,
        "num_input": 0,
    }

    state = input_processor.process_once(state)

    print("─" * 60)
    origin = state.get("origin_str") or Origination.get_full_name_from_origin([])
    print(f"\nResponse from {origin}:")
    print(state.get("last_chat_response") or "(no response)")

    returned = state.get("returned_sly_data")
    if returned:
        pr_url = None
        for repo_data in (returned.get("pull_requests") or {}).values():
            if isinstance(repo_data, dict) and repo_data.get("url"):
                pr_url = repo_data["url"]
                break
        if pr_url:
            print(f"\nDraft PR: {pr_url}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
