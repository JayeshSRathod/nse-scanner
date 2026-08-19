"""Read-only data-health gate for the isolated shadow engine."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd


def evaluate(db_path: str | Path, features: pd.DataFrame) -> dict:
    if features.empty:
        return {"status": "BLOCKED", "reasons": ["no_price_features"], "blocked_symbols": []}
    as_of = str(features["as_of_date"].iloc[0])
    reasons: list[str] = []
    blocked: list[str] = []
    if features["as_of_date"].nunique() != 1:
        reasons.append("mixed_as_of_dates")
    if features["close"].isna().any() or (features["close"] <= 0).any():
        reasons.append("invalid_close")
    try:
        with sqlite3.connect(str(db_path)) as conn:
            table = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='blacklist'").fetchone()
            if table:
                rows = conn.execute("SELECT DISTINCT symbol FROM blacklist WHERE date <= ?", (as_of,)).fetchall()
                blocked = sorted(str(row[0]) for row in rows)
    except sqlite3.Error:
        reasons.append("blacklist_unavailable")
    return {"status": "CURRENT" if not reasons else "DEGRADED", "as_of_date": as_of,
            "reasons": reasons, "blocked_symbols": blocked, "history_eligible": int((features["history_sessions"] >= 320).sum())}
