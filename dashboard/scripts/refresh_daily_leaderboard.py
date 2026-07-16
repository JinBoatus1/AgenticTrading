#!/usr/bin/env python3
"""Refresh the Daily Leaderboard for the last completed US weekday.

1. Recomputes cheap baselines (indices + rule-based strategies) for the daily window.
2. Optionally redeploys every ``llm_agent`` entry (real API calls — pass ``--models``).

Schedule nightly after US market close, e.g.:

    # Baselines only (cheap):
    python dashboard/scripts/refresh_daily_leaderboard.py

    # Baselines + all LLM models:
    python dashboard/scripts/refresh_daily_leaderboard.py --models

Or hit ``GET /api/v1/leaderboard?period=daily&refresh=true`` for baselines only.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

DASHBOARD_DIR = Path(__file__).resolve().parent.parent

from _bootstrap import ensure_repo_root

ensure_repo_root()

load_dotenv(DASHBOARD_DIR / ".env")
load_dotenv(DASHBOARD_DIR.parent / ".env")

from dashboard.backend.domain.leaderboard.service import (  # noqa: E402
    LeaderboardFallbackError,
    deploy_model_run,
    ensure_leaderboard_runs,
    resolve_leaderboard_config,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh the Daily Leaderboard window")
    parser.add_argument(
        "--models",
        action="store_true",
        help="Also redeploy every llm_agent entry for the daily window (expensive)",
    )
    parser.add_argument(
        "--allow-fallback",
        action="store_true",
        help="Allow publishing LLM entries that fell back to rule-based trading",
    )
    args = parser.parse_args()

    config = resolve_leaderboard_config("daily")
    start = config["start_date"]
    end = config["end_date"]
    print(f"Daily leaderboard window: {start} → {end}")
    print(f"Session: {config['session_id']}")

    print("Recomputing baselines…")
    try:
        meta = ensure_leaderboard_runs(force_refresh=True, period="daily", config=config)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Baselines created: {meta.get('created', 0)} (skipped {meta.get('skipped', 0)})")

    if not args.models:
        print("Done (baselines only). Pass --models to redeploy LLM entries.")
        print("View: GET /api/v1/leaderboard?period=daily")
        return 0

    llm_entries = [
        s for s in config.get("strategies", [])
        if s.get("strategy") == "llm_agent" or s.get("auto_compute") is False
    ]
    print(f"Deploying {len(llm_entries)} model entr(y/ies)…")
    failures = 0
    for entry in llm_entries:
        entry_id = entry["id"]
        print(f"\n--- {entry_id} ({entry.get('model')}) ---")
        try:
            result = deploy_model_run(
                entry_id,
                force_refresh=True,
                period="daily",
                allow_fallback=args.allow_fallback,
            )
            ret = result.get("total_return")
            ret_s = f"{ret * 100:+.2f}%" if ret is not None else "—"
            print(f"  ok  run={result.get('run_id')}  return={ret_s}")
        except (LeaderboardFallbackError, ValueError, RuntimeError) as exc:
            failures += 1
            print(f"  FAIL: {exc}", file=sys.stderr)

    print(f"\nDone. Failures: {failures}")
    print("View: GET /api/v1/leaderboard?period=daily")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
