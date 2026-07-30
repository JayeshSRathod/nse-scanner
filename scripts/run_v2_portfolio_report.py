"""Render the latest V2 portfolio report for a future Telegram /portfolio command."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from v2.portfolio_performance import PortfolioSnapshot
from v2.portfolio_store import PortfolioStore
from v2.portfolio_summary import render_portfolio_summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="nse_scanner.db")
    parser.add_argument("--output", default="output/v2_portfolio/portfolio_summary.txt")
    args = parser.parse_args()
    row = PortfolioStore(args.db).latest_portfolio_snapshot()
    if row is None:
        raise SystemExit("No V2 portfolio snapshot exists yet. Run the V2 daily pipeline first.")
    snapshot = PortfolioSnapshot(**json.loads(row["snapshot_json"]))
    message = render_portfolio_summary(snapshot)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(message, encoding="utf-8")
    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
