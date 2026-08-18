"""Read-only shared-market adapter and Old NSE discovery ranking."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class DiscoveryResult:
    as_of_date: str
    eligible: int
    shortlist: pd.DataFrame
    rejected: dict[str, int]


def load_market_data(db_path: str | Path, as_of: str | None = None) -> pd.DataFrame:
    """Read common price snapshots only; do not import V2/V3 code or state."""
    with sqlite3.connect(db_path) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        table = "daily_prices_v2" if "daily_prices_v2" in tables else "daily_prices"
        date_col = "trade_date" if table == "daily_prices_v2" else "date"
        query = f"SELECT * FROM {table}" + (f" WHERE {date_col}<=?" if as_of else "")
        frame = pd.read_sql_query(query, conn, params=[as_of] if as_of else None)
    frame = frame.rename(columns={date_col: "trade_date"})
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    return frame.sort_values(["symbol", "trade_date"])


def discover(prices: pd.DataFrame, top_n: int = 25) -> DiscoveryResult:
    """Rank 22/44/66-session momentum; Hull receives this shortlist only."""
    rows, rejected = [], {"insufficient_history": 0, "low_price": 0, "low_volume": 0}
    for symbol, frame in prices.groupby("symbol"):
        data = frame.sort_values("trade_date")
        if len(data) < 67:
            rejected["insufficient_history"] += 1; continue
        close = pd.to_numeric(data["close"], errors="coerce")
        volume = pd.to_numeric(data["volume"], errors="coerce")
        if close.iloc[-1] < 50:
            rejected["low_price"] += 1; continue
        if volume.tail(20).mean() < 50_000:
            rejected["low_volume"] += 1; continue
        returns = [close.iloc[-1] / close.iloc[-1 - window] - 1 for window in (22, 44, 66)]
        rows.append({"symbol": str(symbol), "as_of_date": data["trade_date"].iloc[-1].date().isoformat(),
                     "momentum_1m": returns[0], "momentum_2m": returns[1], "momentum_3m": returns[2],
                     "volume_20d": float(volume.tail(20).mean())})
    result = pd.DataFrame(rows)
    if result.empty:
        return DiscoveryResult("", 0, result, rejected)
    result["discovery_score"] = (result["momentum_1m"].rank(pct=True) * 20 + result["momentum_2m"].rank(pct=True) * 30 + result["momentum_3m"].rank(pct=True) * 50)
    result = result.sort_values(["discovery_score", "symbol"], ascending=[False, True]).reset_index(drop=True)
    result["discovery_rank"] = result.index + 1
    return DiscoveryResult(str(result["as_of_date"].iloc[0]), len(result), result.head(top_n), rejected)
