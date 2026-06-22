#!/usr/bin/env python3
"""Run chatbot E2E scenarios independently and keep per-scenario logs."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


DEFAULT_SCENARIOS = [
    "basic",
    "full_journey",
    "two_siblings",
    "requirements_only",
    "quick_lead",
    "price_seeker",
    "impossible_age",
    "weekend_booking",
    "prompt_injection",
    "talk_to_human",
    "english_speaker",
    "wall_of_text",
    "cancel_no_appointment",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run chatbot E2E scenarios with isolation.")
    parser.add_argument("scenarios", nargs="*", default=DEFAULT_SCENARIOS)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument(
        "--org-id",
        default=os.getenv("TEST_ORG_ID", "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"),
    )
    args = parser.parse_args()

    repo = Path(__file__).resolve().parents[1]
    log_dir = repo / "test_logs" / f"e2e_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    log_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["TEST_ORG_ID"] = args.org_id
    env["WHATSAPP_DRY_RUN"] = "true"

    results = []
    for scenario in args.scenarios:
        log_path = log_dir / f"{scenario}.log"
        print(f"=== {scenario} ===")
        try:
            completed = subprocess.run(
                [sys.executable, "test_chat.py", "--scenario", scenario],
                cwd=repo,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=args.timeout,
            )
            log_path.write_text(completed.stdout, encoding="utf-8")
            status = "PASS" if completed.returncode == 0 else f"FAIL({completed.returncode})"
        except subprocess.TimeoutExpired as exc:
            output = exc.stdout or ""
            if isinstance(output, bytes):
                output = output.decode("utf-8", errors="replace")
            log_path.write_text(output + "\n[TIMEOUT]\n", encoding="utf-8")
            status = "TIMEOUT"

        results.append((scenario, status, log_path))
        print(f"{scenario}: {status} -> {log_path}")

    print("\nSummary")
    for scenario, status, log_path in results:
        print(f"{scenario:24} {status:12} {log_path}")

    return 1 if any(status != "PASS" for _, status, _ in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
