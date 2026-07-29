"""Run the complete NSE Scanner V2 daily pipeline."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from nse_loader import init_database
from nse_market_store import restore_prices
from v2.orchestrator import run_daily


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="nse_scanner.db")
    parser.add_argument("--date", default=None)
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--minimum-score", type=float, default=70.0)
    parser.add_argument("--restore-snapshots", action="store_true")
    parser.add_argument("--send-telegram", action="store_true")
    parser.add_argument("--output", default="output/v2_daily")
    args = parser.parse_args()

    db_path = Path(args.db)
    if args.restore_snapshots:
        init_database(str(db_path))
        restore_prices(db_path, min_days=1)

    result = run_daily(
        db_path,
        as_of=args.date,
        top_n=args.top_n,
        minimum_score=args.minimum_score,
        send_telegram=args.send_telegram,
    )
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "daily_run.json").write_text(
        json.dumps(result.to_dict(), indent=2, default=str), encoding="utf-8"
    )
    (output / "message_1_candidates.txt").write_text(result.candidate_message, encoding="utf-8")
    (output / "message_2_positions.txt").write_text(result.portfolio_message, encoding="utf-8")
    print(json.dumps(result.to_dict(), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
