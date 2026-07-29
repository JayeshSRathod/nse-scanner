"""Pure, reusable technical indicators for NSE Scanner V2.

These functions contain no database, Telegram or workflow side effects so the
same implementation can be reused by live scanning and future backtests.
"""
from __future__ import annotations

import math
from typing import Iterable

import numpy as np
import pandas as pd


def _series(values: Iterable[float] | pd.Series) -> pd.Series:
    return pd.to_numeric(pd.Series(values, copy=False), errors="coerce").astype(float)


def wma(values: Iterable[float] | pd.Series, length: int) -> pd.Series:
    """Weighted moving average with linearly increasing weights."""
    if length < 1:
        raise ValueError("length must be >= 1")
    s = _series(values)
    weights = np.arange(1, length + 1, dtype=float)
    denominator = weights.sum()
    return s.rolling(length, min_periods=length).apply(
        lambda window: float(np.dot(window, weights) / denominator), raw=True
    )


def hma(values: Iterable[float] | pd.Series, length: int) -> pd.Series:
    """Hull moving average: WMA(2*WMA(n/2)-WMA(n), sqrt(n))."""
    if length < 2:
        raise ValueError("length must be >= 2")
    half = max(1, length // 2)
    root = max(1, int(math.sqrt(length)))
    raw = 2.0 * wma(values, half) - wma(values, length)
    return wma(raw, root)


def true_range(frame: pd.DataFrame) -> pd.Series:
    required = {"high", "low", "close"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"missing columns: {sorted(missing)}")
    high = pd.to_numeric(frame["high"], errors="coerce")
    low = pd.to_numeric(frame["low"], errors="coerce")
    close = pd.to_numeric(frame["close"], errors="coerce")
    previous_close = close.shift(1)
    return pd.concat(
        [(high - low).abs(), (high - previous_close).abs(), (low - previous_close).abs()],
        axis=1,
    ).max(axis=1)


def atr(frame: pd.DataFrame, length: int = 14) -> pd.Series:
    """Wilder ATR using an exponentially smoothed true range."""
    if length < 1:
        raise ValueError("length must be >= 1")
    return true_range(frame).ewm(alpha=1.0 / length, adjust=False, min_periods=length).mean()


def atr_percent(frame: pd.DataFrame, length: int = 14) -> pd.Series:
    close = pd.to_numeric(frame["close"], errors="coerce")
    return 100.0 * atr(frame, length) / close.replace(0, np.nan)


def extension_from_hma(frame: pd.DataFrame, hma_length: int = 55, atr_length: int = 14) -> pd.Series:
    """Distance of close above/below HMA expressed in ATR units."""
    close = pd.to_numeric(frame["close"], errors="coerce")
    baseline = hma(close, hma_length)
    volatility = atr(frame, atr_length).replace(0, np.nan)
    return (close - baseline) / volatility


def hybrid_hull(frame: pd.DataFrame, fast: int = 21, slow: int = 55) -> pd.DataFrame:
    """Return fast/slow HMA and a deterministic direction state.

    State is 1 when fast HMA is above slow HMA and rising, -1 when below and
    falling, otherwise 0. This is a trend-permission component, not an entry.
    """
    close = pd.to_numeric(frame["close"], errors="coerce")
    fast_hma = hma(close, fast)
    slow_hma = hma(close, slow)
    rising = fast_hma.diff() > 0
    falling = fast_hma.diff() < 0
    state = pd.Series(0, index=frame.index, dtype="int64")
    state[(fast_hma > slow_hma) & rising] = 1
    state[(fast_hma < slow_hma) & falling] = -1
    return pd.DataFrame(
        {"hma_fast": fast_hma, "hma_slow": slow_hma, "hybrid_hull_state": state},
        index=frame.index,
    )


def relative_strength_ratio(stock_close: pd.Series, benchmark_close: pd.Series) -> pd.Series:
    """Price-relative series normalized to 100 at the first common valid point."""
    stock, benchmark = pd.to_numeric(stock_close, errors="coerce").align(
        pd.to_numeric(benchmark_close, errors="coerce"), join="inner"
    )
    ratio = stock / benchmark.replace(0, np.nan)
    valid = ratio.dropna()
    if valid.empty:
        return ratio
    return 100.0 * ratio / valid.iloc[0]


def relative_strength_return(
    stock_close: pd.Series, benchmark_close: pd.Series, lookback: int = 63
) -> pd.Series:
    """Stock return minus benchmark return over a fixed trading-session lookback."""
    if lookback < 1:
        raise ValueError("lookback must be >= 1")
    stock, benchmark = pd.to_numeric(stock_close, errors="coerce").align(
        pd.to_numeric(benchmark_close, errors="coerce"), join="inner"
    )
    return stock.pct_change(lookback) - benchmark.pct_change(lookback)
