"""Independent Pine Hull opportunity lifecycle helpers."""
from __future__ import annotations

import pandas as pd


def weekly_transition(weekly21: pd.Series, weekly51: pd.Series) -> tuple[str, dict[str, float]]:
    if len(weekly21) < 2 or len(weekly51) < 2:
        return "NEUTRAL", {}
    values = [weekly21.iloc[-1], weekly21.iloc[-2], weekly51.iloc[-1], weekly51.iloc[-2]]
    if any(pd.isna(value) for value in values):
        return "NEUTRAL", {}
    gap = float(weekly21.iloc[-1] - weekly51.iloc[-1])
    prior_gap = float(weekly21.iloc[-2] - weekly51.iloc[-2])
    fast_slope = float(weekly21.iloc[-1] - weekly21.iloc[-2])
    slow_slope = float(weekly51.iloc[-1] - weekly51.iloc[-2])
    if gap > 0 and fast_slope >= 0:
        state = "BULLISH"
    elif gap < 0 and gap > prior_gap and fast_slope > 0:
        state = "IMPROVING"
    elif gap >= 0 and fast_slope > 0:
        state = "IMPROVING"
    elif fast_slope < 0 and slow_slope < 0 and gap <= prior_gap:
        state = "BEARISH"
    elif fast_slope < 0 or gap < prior_gap:
        state = "DETERIORATING"
    else:
        state = "NEUTRAL"
    return state, {
        "weekly_hma_gap": round(gap, 4), "weekly_hma_gap_prior": round(prior_gap, 4),
        "weekly_fast_slope": round(fast_slope, 4), "weekly_slow_slope": round(slow_slope, 4),
    }


def timing_state(*, daily_bullish: bool, hma_aligned: bool, kama_rising: bool,
                 trend_commitment: bool, chop: bool, rotational: bool,
                 overextended: bool, score: float, htf_state: str) -> str:
    if overextended:
        return "EXTENDED"
    if chop or rotational or not daily_bullish:
        return "WEAK"
    daily_ready = daily_bullish and hma_aligned and kama_rising and trend_commitment and score >= 70
    if daily_ready and htf_state == "BULLISH":
        return "READY"
    if daily_ready and htf_state in {"IMPROVING", "NEUTRAL"}:
        return "EARLY"
    if daily_bullish and kama_rising and htf_state in {"BULLISH", "IMPROVING", "NEUTRAL"} and score >= 60:
        return "EARLY"
    if htf_state in {"BEARISH", "DETERIORATING"}:
        return "WEAK"
    return "WEAK"
