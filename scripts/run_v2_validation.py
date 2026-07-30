"""Run Sprint 7 point-in-time backtest and validation reports."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from v2.backtest import run_point_in_time_backtest
from v2.database import V2Database
from v2.performance import summarize_performance, trades_frame
from v2.walk_forward import anchored_walk_forward, score_sensitivity


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="nse_scanner.db")
    parser.add_argument("--output", default="output/v2_validation")
    parser.add_argument("--minimum-score", type=float, default=70.0)
    parser.add_argument("--warmup", type=int, default=120)
    parser.add_argument("--max-positions", type=int, default=10)
    parser.add_argument("--walk-forward", action="store_true")
    args = parser.parse_args()

    prices = V2Database(args.db).load_prices(min_sessions=args.warmup + 1)
    if prices.empty:
        raise RuntimeError("No usable price history for validation")
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    trades = run_point_in_time_backtest(
        prices, minimum_score=args.minimum_score,
        warmup_sessions=args.warmup, max_positions=args.max_positions,
    )
    report = summarize_performance(trades)
    trades_frame(trades).to_csv(output / "trades.csv", index=False)
    (output / "performance.json").write_text(
        json.dumps(report.to_dict(), indent=2, default=str), encoding="utf-8"
    )

    sensitivity = score_sensitivity(
        prices, warmup_sessions=args.warmup, max_positions=args.max_positions,
    )
    (output / "score_sensitivity.json").write_text(
        json.dumps(sensitivity, indent=2, default=str), encoding="utf-8"
    )

    if args.walk_forward:
        rows = anchored_walk_forward(
            prices, warmup_sessions=args.warmup, max_positions=args.max_positions,
        )
        (output / "walk_forward.json").write_text(
            json.dumps([row.to_dict() for row in rows], indent=2), encoding="utf-8"
        )

    print(json.dumps(report.to_dict(), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
