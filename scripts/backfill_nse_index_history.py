"""Backfill official NSE index snapshots for the retained market sessions."""
from __future__ import annotations

import argparse
import sqlite3
from datetime import date
from pathlib import Path

from nse_historical_downloader import DIRECT_URLS, apply_fmt, date_vars, day_folder, download
from nse_loader import init_database, load_index
from nse_market_store import export_index_history, snapshot_dates
from nse_parser import parse_ind_close


def backfill(db_path: str, limit: int = 420) -> tuple[int, int]:
    init_database(db_path)
    loaded = failed = 0
    for value in snapshot_dates()[-limit:]:
        trade_date = date.fromisoformat(value)
        fmt = date_vars(trade_date)
        path = Path(day_folder(trade_date)) / f"ind_close_all_{fmt['DDMMYYYY']}.csv"
        url = apply_fmt(DIRECT_URLS["ind_close_all"], fmt)
        if not download(url, str(path)):
            failed += 1
            continue
        frame = parse_ind_close(str(path))
        if frame is None or frame.empty:
            failed += 1
            continue
        with sqlite3.connect(db_path) as conn:
            load_index(conn, frame, trade_date)
        loaded += 1
    export_index_history(db_path)
    return loaded, failed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="nse_scanner.db")
    parser.add_argument("--limit", type=int, default=420)
    args = parser.parse_args()
    loaded, failed = backfill(args.db, args.limit)
    print(f"Official index sessions loaded: {loaded}; failed: {failed}")
    return 0 if loaded else 2


if __name__ == "__main__":
    raise SystemExit(main())
