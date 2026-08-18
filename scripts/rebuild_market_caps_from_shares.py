"""Locally rebuild point-in-time market-cap snapshots from validated shares."""
from __future__ import annotations

import argparse
import sqlite3

from nse_corporate_collector import rebuild_caps_from_shares, refresh_current_market_cap
from v2.database import V2Database


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="nse_scanner.db")
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    args = parser.parse_args()
    V2Database(args.db).ensure_v3_schema()
    with sqlite3.connect(args.db) as conn:
        rows = rebuild_caps_from_shares(conn, args.start_date, args.end_date)
        latest = args.end_date
        if not latest:
            table = "daily_prices_v2" if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='daily_prices_v2'").fetchone() else "daily_prices"
            column = "trade_date" if table == "daily_prices_v2" else "date"
            latest = conn.execute(f"SELECT MAX({column}) FROM {table}").fetchone()[0]
        refreshed = refresh_current_market_cap(conn, latest) if latest else 0
    print({"market_cap_snapshots": rows, "current_symbol_master_rows": refreshed, "as_of": latest})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
