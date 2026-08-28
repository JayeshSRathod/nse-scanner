from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

from pine_hull.engine import PineConfig, load_state, pine_metrics, run_daily
from pine_hull.preview import render_daily_signals


def _frame(rows: int = 330, *, final_low: float | None = None) -> pd.DataFrame:
    dates = pd.bdate_range("2025-01-02", periods=rows)
    close = pd.Series(np.linspace(100.0, 260.0, rows))
    frame = pd.DataFrame({
        "trade_date": dates,
        "open": close - 0.3,
        "high": close + 3.0,
        "low": close - 3.0,
        "close": close,
        "volume": 150_000,
    })
    if final_low is not None:
        frame.loc[frame.index[-1], "low"] = final_low
    return frame


def _database(path: Path, frame: pd.DataFrame) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute("""CREATE TABLE daily_prices_v2 (
            symbol TEXT, trade_date TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL
        )""")
        loaded = frame.assign(symbol="PINE")[["symbol", "trade_date", "open", "high", "low", "close", "volume"]].copy()
        loaded["trade_date"] = loaded["trade_date"].dt.strftime("%Y-%m-%d")
        loaded.to_sql("daily_prices_v2", conn, if_exists="append", index=False)


def test_pine_core_reports_ready_for_clean_uptrend() -> None:
    metrics = pine_metrics(_frame())
    assert metrics["available"] is True
    assert metrics["daily_bullish"] is True
    assert metrics["weekly_bullish"] is True
    assert metrics["state"] == "READY"
    assert metrics["initial_stop"] < metrics["close"]


def test_pine_daily_state_is_independent_and_freezes_entry_levels(tmp_path: Path) -> None:
    db_path, state_path = tmp_path / "prices.db", tmp_path / "pine_state.json"
    _database(db_path, _frame())
    result = run_daily(db_path, state_path=state_path, config=PineConfig(capital_base=300_000.0))
    assert len(result["created"]) == 1
    position = result["created"][0]
    assert position["entry"] == 260.0
    assert position["target1"] > position["entry"]
    saved = load_state(state_path)
    assert saved["positions"][0]["trade_id"].startswith("PINE-")
    assert saved["positions"][0]["state"] == "OPEN"


def test_pine_signal_message_matches_compact_daily_candidate_style() -> None:
    result = {
        "trade_date": "2026-08-07",
        "created": [{
            "symbol": "RELIANCE", "entry": 1500.0, "initial_stop": 1450.0,
            "target1": 1575.0, "target2": 1650.0,
            "htf_weekly_bullish": True,
        }],
        "watch": [{"symbol": "TCS", "score": 82.0, "overextended": False, "chop": False, "rotational": False}],
    }
    message = render_daily_signals(result)
    assert "📐 PINE HULL SIGNALS" in message
    assert "NSE%3ARELIANCE" in message
    assert "New paper entry" in message
    assert "Early watchlist" in message
    assert "Entry: ₹1,500.00–" in message
    assert "SL: ₹1,450.00" in message
    assert "T1: ₹1,575.00 • T2: ₹1,650.00" in message
    assert "✅ Daily Hull bullish" in message
    assert "HULL PINE WATCHLIST" in message
    assert "NSE%3ATCS" in message
