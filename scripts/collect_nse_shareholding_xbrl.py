"""CLI for local bootstrap and incremental daily NSE shareholding collection."""
from __future__ import annotations
import argparse
import json
from datetime import date
from pathlib import Path
from nse_shareholding_collector import collect


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--as-of", default=date.today().isoformat())
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--csv", type=Path, help="manual NSE listing CSV fallback/bootstrap")
    parser.add_argument("--output", type=Path, help="compatibility argument; normalized output is managed atomically")
    parser.add_argument("--db")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    result = collect(db_path=args.db, as_of=date.fromisoformat(args.as_of), days=args.days, csv_fallback=args.csv, limit=args.limit, output_path=args.output)
    print(json.dumps(result.__dict__, indent=2))
    return 0 if result.status in {"FRESH", "NO_NEW_FILINGS", "REUSED_LAST_VALID"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
