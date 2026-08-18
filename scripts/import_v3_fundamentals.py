"""Import point-in-time fundamental snapshots for long-horizon promotion."""
from __future__ import annotations

import argparse
import sqlite3

import pandas as pd


REQUIRED = {
    "symbol", "as_of_date", "revenue_growth_pct", "profit_growth_pct", "roe_pct",
    "debt_to_equity", "operating_cash_flow_positive", "promoter_pledge_pct", "governance_flag",
}


def _flag(value: object) -> int:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "y", "1"}:
            return 1
        if normalized in {"false", "no", "n", "0"}:
            return 0
        raise ValueError(f"invalid boolean value: {value}")
    return int(bool(value))


def import_fundamentals(db_path: str, csv_path: str) -> int:
    frame = pd.read_csv(csv_path)
    missing = REQUIRED.difference(frame.columns)
    if missing:
        raise ValueError(f"fundamental CSV missing columns: {sorted(missing)}")
    frame["symbol"] = frame["symbol"].astype(str).str.strip().str.upper()
    with sqlite3.connect(db_path) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS fundamental_snapshots_v3 (
            symbol TEXT NOT NULL, as_of_date TEXT NOT NULL,
            revenue_growth_pct REAL NOT NULL, profit_growth_pct REAL NOT NULL,
            roe_pct REAL NOT NULL, debt_to_equity REAL NOT NULL,
            operating_cash_flow_positive INTEGER NOT NULL,
            promoter_pledge_pct REAL NOT NULL, governance_flag INTEGER NOT NULL,
            source TEXT NOT NULL DEFAULT 'CONTROLLED_IMPORT',
            loaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(symbol, as_of_date))""")
        conn.executemany("""INSERT INTO fundamental_snapshots_v3
            (symbol,as_of_date,revenue_growth_pct,profit_growth_pct,roe_pct,debt_to_equity,
             operating_cash_flow_positive,promoter_pledge_pct,governance_flag)
            VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(symbol,as_of_date) DO UPDATE SET
             revenue_growth_pct=excluded.revenue_growth_pct,profit_growth_pct=excluded.profit_growth_pct,
             roe_pct=excluded.roe_pct,debt_to_equity=excluded.debt_to_equity,
             operating_cash_flow_positive=excluded.operating_cash_flow_positive,
             promoter_pledge_pct=excluded.promoter_pledge_pct,governance_flag=excluded.governance_flag""", [
            (str(row.symbol), str(row.as_of_date), float(row.revenue_growth_pct), float(row.profit_growth_pct),
             float(row.roe_pct), float(row.debt_to_equity), _flag(row.operating_cash_flow_positive),
             float(row.promoter_pledge_pct), _flag(row.governance_flag))
            for row in frame.itertuples(index=False)
        ])
    return len(frame)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path")
    parser.add_argument("--db", default="nse_scanner.db")
    args = parser.parse_args()
    print(f"Imported {import_fundamentals(args.db, args.csv_path)} fundamental snapshots")


if __name__ == "__main__":
    main()
