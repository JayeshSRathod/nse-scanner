from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from v2.indicators import atr, hma, hybrid_hull, relative_strength_return, wma
from v2.regime import classify_market_regime, rank_relative_strength


def test_wma_matches_manual_calculation():
    values = pd.Series([1.0, 2.0, 3.0, 4.0])
    result = wma(values, 3)
    assert result.iloc[-1] == pytest.approx((2 * 1 + 3 * 2 + 4 * 3) / 6)


def test_hma_tracks_linear_series_after_warmup():
    values = pd.Series(np.arange(1.0, 121.0))
    result = hma(values, 20)
    assert result.notna().sum() > 80
    assert result.iloc[-1] > result.iloc[-2]
    assert abs(result.iloc[-1] - values.iloc[-1]) < 5.0


def test_atr_uses_true_range_gap():
    frame = pd.DataFrame(
        {"high": [11.0, 16.0], "low": [9.0, 14.0], "close": [10.0, 15.0]}
    )
    result = atr(frame, length=1)
    assert result.iloc[0] == pytest.approx(2.0)
    assert result.iloc[1] == pytest.approx(6.0)


def test_hybrid_hull_returns_positive_state_in_strong_uptrend():
    close = pd.Series(np.linspace(100.0, 200.0, 160))
    frame = pd.DataFrame({"close": close})
    result = hybrid_hull(frame, fast=21, slow=55)
    assert result.iloc[-1]["hybrid_hull_state"] == 1


def test_relative_strength_return_is_excess_return():
    stock = pd.Series([100.0, 120.0])
    benchmark = pd.Series([100.0, 110.0])
    result = relative_strength_return(stock, benchmark, lookback=1)
    assert result.iloc[-1] == pytest.approx(0.10)


def _regime_fixture(up: bool = True):
    index = pd.bdate_range("2026-01-01", periods=100)
    close = np.linspace(100.0, 150.0, 100) if up else np.linspace(150.0, 100.0, 100)
    benchmark = pd.DataFrame({"close": close}, index=index)
    breadth = pd.DataFrame(
        {
            "pct_above_50dma": 70.0 if up else 30.0,
            "pct_above_200dma": 60.0 if up else 25.0,
        },
        index=index,
    )
    return benchmark, breadth


def test_market_regime_bull_is_date_explicit():
    benchmark, breadth = _regime_fixture(True)
    result = classify_market_regime(benchmark, breadth, hma_length=20)
    assert result.state == "BULL"
    assert result.as_of_date == benchmark.index[-1].date().isoformat()
    assert result.score == 4


def test_market_regime_bear():
    benchmark, breadth = _regime_fixture(False)
    result = classify_market_regime(benchmark, breadth, hma_length=20)
    assert result.state == "BEAR"


def test_rs_rank_has_no_static_bias():
    ranked = rank_relative_strength({"IT": 0.08, "BANK": 0.12, "AUTO": 0.04})
    assert ranked.iloc[0]["symbol"] == "BANK"
    assert list(ranked["rs_rank"]) == [1, 2, 3]
