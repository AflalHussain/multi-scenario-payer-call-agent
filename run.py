#!/usr/bin/env python3
"""
Single entry point for running a payer call from the command line.

Usage:
    # Silent (default) — prints JSON result only
    python run.py --scenario scenarios/benefits_verification.yaml \
                  --fixture  fixtures/benefits_clean.yaml \
                  --member-id MBR-SYNTH-001

    # Live real-time conversation view
    python run.py --scenario scenarios/benefits_verification.yaml \
                  --fixture  fixtures/benefits_clean.yaml \
                  --member-id MBR-SYNTH-001 \
                  --live

    # Real OpenRouter LLM + live view
    python run.py --scenario scenarios/benefits_verification.yaml \
                  --fixture  fixtures/benefits_clean.yaml \
                  --member-id MBR-SYNTH-001 \
                  --llm openrouter --live
"""
import argparse
import json
import sys
from core.agent import PayerCallAgent
from core.live_logger import LiveLogger
from llm.stub import StubLLM
from llm.openrouter import OpenRouterLLM


def main():
    parser = argparse.ArgumentParser(description="Run a payer call agent scenario")
    parser.add_argument("--scenario",  required=True, help="Path to scenario YAML")
    parser.add_argument("--fixture",   required=True, help="Path to fixture YAML")
    parser.add_argument("--member-id", default=None,  help="Synthetic member ID (will be masked)")
    parser.add_argument(
        "--llm",
        choices=["stub", "openrouter"],
        default="stub",
        help="LLM backend: 'stub' (default) or 'openrouter'",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Stream the call live with delays and coloured output",
    )
    args = parser.parse_args()

    llm    = OpenRouterLLM() if args.llm == "openrouter" else StubLLM()
    logger = LiveLogger(enabled=args.live)

    agent  = PayerCallAgent(llm=llm, logger=logger)
    result = agent.run(args.scenario, args.fixture, member_id=args.member_id)

    print(json.dumps(result.to_dict(), indent=2))
    sys.exit(0 if result.status.value == "complete" else 1)


if __name__ == "__main__":
    main()
