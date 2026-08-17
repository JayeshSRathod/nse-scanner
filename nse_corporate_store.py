"""Git-backed normalized corporate snapshots for disposable CI runners."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path("corporate_data/normalized")
TABLES = {
    "symbol_master_v2": "symbol_master.csv",
    "shares_outstanding_v3": "shares_outstanding.csv",
    "market_cap_snapshots_v3": "market_cap_snapshots.csv",
    "promoter_pledge_v3": "promoter_pledge.csv",
    "governance_events_v3": "governance_events.csv",
}


def export_snapshots(db_path: str) -> dict[str, int]:
    ROOT.mkdir(parents=True, exist_ok=True)
    counts = {}
    with sqlite3.connect(db_path) as conn:
        existing = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table, filename in TABLES.items():
            if table not in existing:
                continue
            frame = pd.read_sql_query(f"SELECT * FROM {table}", conn)
            frame.to_csv(ROOT / filename, index=False, lineterminator="\n")
            counts[table] = len(frame)
    return counts


def restore_snapshots(db_path: str) -> dict[str, int]:
    counts = {}
    with sqlite3.connect(db_path) as conn:
        for table, filename in TABLES.items():
            path = ROOT / filename
            if not path.exists():
                continue
            frame = pd.read_csv(path)
            if frame.empty:
                counts[table] = 0
                continue
            columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            usable = [column for column in frame.columns if column in columns]
            placeholders = ",".join("?" for _ in usable)
            conn.executemany(
                f"INSERT OR REPLACE INTO {table} ({','.join(usable)}) VALUES ({placeholders})",
                [tuple(row[column] for column in usable) for _, row in frame.iterrows()],
            )
            counts[table] = len(frame)
    return counts
