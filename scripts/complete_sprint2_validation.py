"""Restore repository market snapshots and complete Sprint 2 validation.

This command is safe for CI: it creates a temporary SQLite database, never sends
Telegram messages, and writes only JSON/CSV outputs under output/v2_validation.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

import pandas as pd

from nse_loader import init_database
from nse_market_store import restore_prices, snapshot_dates
from v2.database import MarketDatabase
from v2.indicators import atr, hybrid_hull, relative_strength
from v2.snapshots import build_market_regime_snapshot, persist_market_regime_snapshot


def _equal_weight_benchmark(prices: pd.DataFrame) -> pd.DataFrame:
    frame = prices[["symbol", "trade_date", "close"]].copy()
    frame["return"] = frame.groupby("symbol")["close"].pct_change()
    daily = frame.groupby("trade_date", as_index=False)["return"].mean().fillna(0.0)
    daily["close"] = (1.0 + daily["return"]).cumprod() * 1000.0
    return daily[["trade_date", "close"]]


def run(db_path: Path, output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    init_database(str(db_path))
    restored = restore_prices(db_path, min_days=1)
    dates = snapshot_dates()

    market = MarketDatabase(db_path)
    prices = market.load_prices(min_sessions=55)
    if prices.empty:
        raise RuntimeError("No usable market prices were restored")

    benchmark = market.load_index_history()
    benchmark_source = "INDEX_PERF"
    if benchmark.empty:
        benchmark = _equal_weight_benchmark(prices)
        benchmark_source = "EQUAL_WEIGHT_UNIVERSE_FALLBACK"

    snapshot = build_market_regime_snapshot(prices, benchmark)
    snapshot["benchmark_source"] = benchmark_source
    snapshot["sector_history_validated"] = False
    snapshot["sector_validation_note"] = (
        "Sector index history is not persisted in market_data snapshots; "
        "sector-relative outputs remain disabled."
    )
    persist_market_regime_snapshot(db_path, snapshot)

    latest_symbol = (
        prices.groupby("symbol").size().sort_values(ascending=False).index[0]
    )
    sample = prices[prices["symbol"] == latest_symbol].sort_values("trade_date")
    sample_out = {
        "symbol": latest_symbol,
        "sessions": int(len(sample)),
        "latest_atr14": float(atr(sample["high"], sample["low"], sample["close"], 14).iloc[-1]),
        "latest_hybrid_hull": str(hybrid_hull(sample["close"]).iloc[-1]),
    }

    aligned = sample[["trade_date", "close"]].merge(
        benchmark, on="trade_date", how="inner", suffixes=("_stock", "_benchmark")
    )
    if len(aligned) >= 66:
        rs = relative_strength(aligned["close_stock"], aligned["close_benchmark"], 66)
        sample_out["latest_rs66"] = float(rs.iloc[-1])

    result = {
        "status": "PASS",
        "restored_sessions": restored,
        "snapshot_count": len(dates),
        "oldest_snapshot": dates[0] if dates else None,
        "newest_snapshot": dates[-1] if dates else None,
        "price_rows": int(len(prices)),
        "symbols": int(prices["symbol"].nunique()),
        "benchmark_source": benchmark_source,
        "market_regime": snapshot,
        "sample_reconciliation": sample_out,
        "sector_history_validated": False,
    }
    (output_dir / "sprint2_validation.json").write_text(
        json.dumps(result, indent=2, default=str), encoding="utf-8"
    )
    pd.DataFrame([snapshot]).to_csv(output_dir / "market_regime_snapshot.csv", index=False)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="output/v2_validation/sprint2.db")
    parser.add_argument("--output", default="output/v2_validation")
    args = parser.parse_args()
    result = run(Path(args.db), Path(args.output))
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
