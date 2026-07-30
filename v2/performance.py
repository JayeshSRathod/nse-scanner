"""Performance, expectancy and drawdown analytics for V2 backtests."""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from .backtest import BacktestTrade


@dataclass(frozen=True)
class PerformanceReport:
    trades: int
    entered_trades: int
    wins: int
    losses: int
    breakeven: int
    win_rate: float
    expectancy_r: float
    median_r: float
    profit_factor: float
    cumulative_r: float
    max_drawdown_r: float
    average_holding_sessions: float
    t1_or_better_rate: float

    def to_dict(self) -> dict:
        return asdict(self)


def summarize_performance(trades: list[BacktestTrade]) -> PerformanceReport:
    entered = [trade for trade in trades if trade.entry_date is not None]
    r = np.array([trade.realised_r for trade in entered], dtype=float)
    wins = int((r > 0).sum()) if len(r) else 0
    losses = int((r < 0).sum()) if len(r) else 0
    breakeven = int((r == 0).sum()) if len(r) else 0
    gains = float(r[r > 0].sum()) if len(r) else 0.0
    losses_abs = abs(float(r[r < 0].sum())) if len(r) else 0.0
    profit_factor = gains / losses_abs if losses_abs > 0 else (float("inf") if gains > 0 else 0.0)
    equity = np.cumsum(r) if len(r) else np.array([], dtype=float)
    if len(equity):
        peaks = np.maximum.accumulate(np.concatenate(([0.0], equity)))[:-1]
        drawdowns = equity - peaks
        max_drawdown = float(drawdowns.min())
    else:
        max_drawdown = 0.0
    t1_rate = float(np.mean(r >= 1.0)) if len(r) else 0.0
    return PerformanceReport(
        trades=len(trades), entered_trades=len(entered), wins=wins, losses=losses,
        breakeven=breakeven, win_rate=round(wins / len(entered), 4) if entered else 0.0,
        expectancy_r=round(float(r.mean()), 4) if len(r) else 0.0,
        median_r=round(float(np.median(r)), 4) if len(r) else 0.0,
        profit_factor=round(profit_factor, 4) if np.isfinite(profit_factor) else profit_factor,
        cumulative_r=round(float(r.sum()), 4) if len(r) else 0.0,
        max_drawdown_r=round(max_drawdown, 4),
        average_holding_sessions=round(float(np.mean([t.holding_sessions for t in entered])), 2) if entered else 0.0,
        t1_or_better_rate=round(t1_rate, 4),
    )


def trades_frame(trades: list[BacktestTrade]) -> pd.DataFrame:
    return pd.DataFrame([trade.to_dict() for trade in trades])
