"""Git-backed normalized EOD market-data store for stateless runners.

GitHub Actions runners are disposable, so the local SQLite database cannot be
the source of truth. This module persists one compact CSV per trading day in
the repository and rebuilds a temporary SQLite database when a runner starts.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path

import pandas as pd


STORE_ROOT = Path("market_data")
DAILY_DIR = STORE_ROOT / "daily"
MANIFEST_PATH = STORE_ROOT / "manifest.json"
KEEP_DAYS = 450

PRICE_COLUMNS = [
    "symbol", "date", "prev_close", "open", "high", "low", "last_price",
    "close", "avg_price", "volume", "turnover_lacs", "trades",
    "delivery_qty", "delivery_pct",
]


def _snapshot_paths() -> list[Path]:
    return sorted(DAILY_DIR.glob("????-??-??.csv"))


def snapshot_dates() -> list[str]:
    return [path.stem for path in _snapshot_paths()]


def restore_prices(db_path: str | Path, min_days: int = 1) -> int:
    """Restore saved daily snapshots into an empty SQLite database."""
    paths = _snapshot_paths()
    if len(paths) < min_days:
        return 0

    conn = sqlite3.connect(str(db_path))
    restored = 0
    try:
        for path in paths[-KEEP_DAYS:]:
            day = path.stem
            existing = conn.execute(
                "SELECT 1 FROM load_log WHERE date = ? AND status = 'ok'", (day,)
            ).fetchone()
            if existing:
                continue

            frame = pd.read_csv(path)
            if frame.empty:
                continue
            missing = [column for column in PRICE_COLUMNS if column not in frame.columns]
            if missing:
                raise ValueError(f"Invalid market snapshot {path}: missing {missing}")

            frame[PRICE_COLUMNS].to_sql("daily_prices", conn, if_exists="append", index=False)
            conn.execute(
                """INSERT OR REPLACE INTO load_log
                   (date, loaded_at, prices_rows, status, notes)
                   VALUES (?, ?, ?, 'ok', ?)""",
                (day, datetime.utcnow().isoformat(), len(frame), "Restored from market_data snapshot"),
            )
            restored += 1
        conn.commit()
    finally:
        conn.close()
    return restored


def export_price_snapshot(db_path: str | Path, trade_date: date | str) -> Path:
    """Write one normalized, version-control-friendly price snapshot."""
    day = trade_date.isoformat() if isinstance(trade_date, date) else str(trade_date)
    DAILY_DIR.mkdir(parents=True, exist_ok=True)
    snapshot_path = DAILY_DIR / f"{day}.csv"

    conn = sqlite3.connect(str(db_path))
    try:
        frame = pd.read_sql_query(
            f"SELECT {', '.join(PRICE_COLUMNS)} FROM daily_prices WHERE date = ? ORDER BY symbol",
            conn,
            params=(day,),
        )
    finally:
        conn.close()

    if frame.empty:
        raise ValueError(f"Cannot create snapshot for {day}: no daily_prices rows")
    frame.to_csv(snapshot_path, index=False, lineterminator="\n")
    return snapshot_path


def export_all_price_snapshots(db_path: str | Path, keep_days: int = KEEP_DAYS) -> int:
    """Create missing snapshots for database history and prune old files."""
    conn = sqlite3.connect(str(db_path))
    try:
        dates = [row[0] for row in conn.execute(
            "SELECT DISTINCT date FROM daily_prices ORDER BY date DESC LIMIT ?", (keep_days,)
        )]
    finally:
        conn.close()

    written = 0
    for day in dates:
        path = DAILY_DIR / f"{day}.csv"
        if not path.exists():
            export_price_snapshot(db_path, day)
            written += 1

    paths = _snapshot_paths()
    for path in paths[:-keep_days]:
        path.unlink()
    write_manifest()
    return written


def write_manifest() -> None:
    STORE_ROOT.mkdir(parents=True, exist_ok=True)
    dates = snapshot_dates()
    payload = {
        "schema_version": 1,
        "updated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "snapshot_count": len(dates),
        "oldest_date": dates[0] if dates else None,
        "newest_date": dates[-1] if dates else None,
        "columns": PRICE_COLUMNS,
    }
    pd.Series(payload).to_json(MANIFEST_PATH, indent=2)
