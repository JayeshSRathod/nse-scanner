"""Import dated market-cap and NSE symbol metadata from a controlled CSV."""
from __future__ import annotations

import argparse
import sqlite3

import pandas as pd


REQUIRED = {"symbol", "series", "market_cap_cr", "as_of_date"}


def import_metadata(db_path: str, csv_path: str) -> int:
    frame = pd.read_csv(csv_path)
    missing = REQUIRED.difference(frame.columns)
    if missing:
        raise ValueError(f"metadata CSV missing columns: {sorted(missing)}")
    frame["symbol"] = frame["symbol"].astype(str).str.strip().str.upper()
    frame["series"] = frame["series"].astype(str).str.strip().str.upper()
    frame["market_cap_cr"] = pd.to_numeric(frame["market_cap_cr"], errors="raise")
    if (frame["market_cap_cr"] <= 0).any():
        raise ValueError("market_cap_cr must be positive")
    if frame["symbol"].duplicated().any():
        raise ValueError("metadata CSV contains duplicate symbols")
    rows = [
        (row.symbol, row.series, float(row.market_cap_cr), str(row.as_of_date), 1)
        for row in frame.itertuples(index=False)
    ]
    with sqlite3.connect(db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(symbol_master_v2)")}
        if "market_cap_cr" not in columns:
            conn.execute("ALTER TABLE symbol_master_v2 ADD COLUMN market_cap_cr REAL")
        if "market_cap_as_of" not in columns:
            conn.execute("ALTER TABLE symbol_master_v2 ADD COLUMN market_cap_as_of DATE")
        conn.executemany("""INSERT INTO symbol_master_v2
            (symbol,series,market_cap_cr,market_cap_as_of,active)
            VALUES (?,?,?,?,?)
            ON CONFLICT(symbol) DO UPDATE SET series=excluded.series,
            market_cap_cr=excluded.market_cap_cr,market_cap_as_of=excluded.market_cap_as_of,
            active=excluded.active,updated_at=CURRENT_TIMESTAMP""", rows)
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path")
    parser.add_argument("--db", default="nse_scanner.db")
    args = parser.parse_args()
    print(f"Imported {import_metadata(args.db, args.csv_path)} symbol metadata rows")


if __name__ == "__main__":
    main()
