"""Point-in-time 20-session replay using the existing shared EOD database."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from old_nse_hull.discovery import discover

from .comparison import summarize
from .engine import run_shadow


def run(prices: pd.DataFrame, db_path: str | Path, state_path: str | Path, sessions: int = 20) -> dict:
    """Replay prior completed sessions without fetching or mutating market data."""
    dates = sorted(pd.to_datetime(prices["trade_date"]).dropna().unique())[-sessions:]
    completed: list[str] = []
    for date in dates:
        history = prices[pd.to_datetime(prices["trade_date"]) <= date]
        baseline = discover(history).shortlist
        shadow = run_shadow(history, db_path, baseline["symbol"].astype(str).tolist(), state_path)
        completed.append(shadow["as_of_date"])
    return {"mode": "HISTORICAL_REPLAY", "sessions_requested": sessions,
            "sessions_completed": len(completed), "as_of_dates": completed,
            "comparison_summary": summarize(state_path)}
