"""End-to-end daily orchestration for NSE Scanner V2."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from .candidates import Candidate, evaluate_candidate, rank_candidates
from .daily_portfolio import process_portfolio_day
from .database import V2Database
from .freshness import FreshnessStatus, assess_freshness
from .lifecycle import new_position
from .portfolio_message import render_portfolio_message
from .portfolio_store import PortfolioStore
from .preview import render_candidate_preview
from .snapshots import build_market_snapshot
from .telegram_delivery import DeliveryResult, send_messages


@dataclass(frozen=True)
class DailyRunResult:
    trade_date: str
    regime: str
    benchmark_source: str
    freshness: FreshnessStatus
    evaluated: int
    selected: int
    created_positions: int
    portfolio_positions: int
    candidate_message: str
    portfolio_message: str
    delivery: DeliveryResult

    def to_dict(self) -> dict:
        return asdict(self)


def _equal_weight_benchmark(prices: pd.DataFrame) -> pd.DataFrame:
    frame = prices[["symbol", "trade_date", "close"]].copy()
    frame["return"] = frame.groupby("symbol")["close"].pct_change()
    daily = frame.groupby("trade_date", as_index=False)["return"].mean().fillna(0.0)
    daily["close"] = (1.0 + daily["return"]).cumprod() * 1000.0
    return daily[["trade_date", "close"]]


def _existing_keys(store: PortfolioStore) -> set[tuple[str, str]]:
    return {(position.symbol, position.horizon) for position in store.open_positions()}


def _warning_header(freshness: FreshnessStatus, benchmark_source: str) -> str:
    warnings = list(freshness.reasons)
    if benchmark_source != "OFFICIAL_INDEX_HISTORY":
        warnings.append("official_index_history_unavailable_equal_weight_fallback")
    return "" if not warnings else "DATA WARNING: " + "; ".join(warnings) + "\n\n"


def run_daily(
    db_path: str | Path,
    as_of: date | str | None = None,
    top_n: int = 10,
    minimum_score: float = 70.0,
    send_telegram: bool = False,
) -> DailyRunResult:
    run_date = pd.Timestamp(as_of or date.today()).date()
    database = V2Database(db_path)
    prices = database.load_prices(end_date=run_date.isoformat(), min_sessions=60)
    if prices.empty:
        raise RuntimeError("No usable V2 price history")
    indices = database.load_indices(end_date=run_date.isoformat())
    freshness = assess_freshness(prices, indices, run_date)

    benchmark_source = "OFFICIAL_INDEX_HISTORY"
    benchmark = pd.DataFrame()
    if not indices.empty:
        normalized = indices["index_name"].astype(str).str.upper()
        preferred = indices[normalized.isin(["NIFTY 500", "NIFTY 50"])]
        if not preferred.empty:
            preferred_names = preferred["index_name"].astype(str).str.upper()
            chosen = "NIFTY 500" if (preferred_names == "NIFTY 500").any() else "NIFTY 50"
            benchmark = preferred[preferred_names == chosen].copy()
    if benchmark.empty:
        benchmark = _equal_weight_benchmark(prices)
        benchmark_source = "EQUAL_WEIGHT_UNIVERSE_FALLBACK"

    snapshot = build_market_snapshot(prices, benchmark)
    regime = snapshot["regime"]
    candidates = [
        evaluate_candidate(
            str(symbol), frame, regime,
            stale_data=freshness.prices_stale,
            minimum_score=minimum_score,
        )
        for symbol, frame in prices.groupby("symbol")
    ]
    ranked = rank_candidates(candidates, top_n=top_n)
    selected = [candidate for rows in ranked.values() for candidate in rows]

    store = PortfolioStore(db_path)
    store.initialize()
    existing = _existing_keys(store)
    created = 0
    for candidate in selected:
        store.remember_candidate(candidate.symbol, candidate.horizon, candidate.trade_date, candidate.score)
        key = (candidate.symbol, candidate.horizon)
        if key in existing:
            continue
        position = new_position(
            candidate.symbol, candidate.horizon, candidate.trade_date,
            candidate.entry, candidate.stop, candidate.target1, candidate.target2,
        )
        store.save_position(position, "CREATE")
        existing.add(key)
        created += 1

    latest_bars = {
        str(symbol): frame.sort_values("trade_date").iloc[-1].to_dict()
        for symbol, frame in prices.groupby("symbol")
    }
    process_portfolio_day(store, run_date.isoformat(), latest_bars)
    portfolio_positions = store.open_positions()
    warning = _warning_header(freshness, benchmark_source)
    candidate_message = warning + render_candidate_preview(ranked, regime, run_date.isoformat())
    portfolio_message = warning + render_portfolio_message(portfolio_positions, run_date.isoformat())
    delivery = send_messages([candidate_message, portfolio_message], enabled=send_telegram)
    return DailyRunResult(
        trade_date=run_date.isoformat(), regime=regime,
        benchmark_source=benchmark_source, freshness=freshness,
        evaluated=len(candidates), selected=len(selected), created_positions=created,
        portfolio_positions=len(portfolio_positions), candidate_message=candidate_message,
        portfolio_message=portfolio_message, delivery=delivery,
    )
