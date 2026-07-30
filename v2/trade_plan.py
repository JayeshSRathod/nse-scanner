"""Resistance-aware entry, stop and target construction for Sprint 3."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .indicators import atr


@dataclass(frozen=True)
class TradePlan:
    valid: bool
    entry: float
    stop: float
    target1: float
    target2: float
    risk_per_share: float
    reward_risk_t1: float
    reward_risk_t2: float
    resistance: float | None
    reasons: tuple[str, ...]


def _nearest_resistance(data: pd.DataFrame, entry: float, lookback: int = 120) -> float | None:
    history = data.iloc[:-1].tail(lookback)
    if history.empty:
        return None
    candidates = history.loc[history["high"] > entry, "high"]
    if candidates.empty:
        return None
    return float(candidates.min())


def build_long_trade_plan(
    frame: pd.DataFrame,
    entry_buffer_atr: float = 0.10,
    stop_buffer_atr: float = 0.25,
    target1_r: float = 1.5,
    target2_r: float = 3.0,
    max_entry_extension_atr: float = 1.5,
    minimum_rr_t1: float = 1.25,
) -> TradePlan:
    data = frame.sort_values("trade_date").copy()
    if len(data) < 60:
        return TradePlan(False, 0, 0, 0, 0, 0, 0, 0, None, ("insufficient_history",))

    current_atr = float(atr(data, 14).iloc[-1])
    if not pd.notna(current_atr) or current_atr <= 0:
        return TradePlan(False, 0, 0, 0, 0, 0, 0, 0, None, ("invalid_atr",))

    last = data.iloc[-1]
    recent_swing_low = float(data["low"].iloc[-10:].min())
    entry = float(last["high"] + entry_buffer_atr * current_atr)
    stop = float(recent_swing_low - stop_buffer_atr * current_atr)
    risk = entry - stop
    if risk <= 0:
        return TradePlan(False, entry, stop, 0, 0, risk, 0, 0, None, ("non_positive_risk",))

    resistance = _nearest_resistance(data, entry)
    raw_t1 = entry + target1_r * risk
    raw_t2 = entry + target2_r * risk
    target1 = min(raw_t1, resistance) if resistance is not None else raw_t1
    target2 = raw_t2
    rr1 = (target1 - entry) / risk
    rr2 = (target2 - entry) / risk

    close_extension = (entry - float(last["close"])) / current_atr
    extension_ok = close_extension <= max_entry_extension_atr
    rr_ok = rr1 >= minimum_rr_t1
    resistance_ok = resistance is None or resistance > entry
    reasons = (
        "entry_extension_ok" if extension_ok else "entry_too_extended",
        "t1_reward_risk_ok" if rr_ok else "near_resistance_limits_reward",
        "resistance_clear" if resistance_ok else "entry_above_resistance_invalid",
    )
    return TradePlan(
        valid=extension_ok and rr_ok and resistance_ok,
        entry=round(entry, 2),
        stop=round(stop, 2),
        target1=round(target1, 2),
        target2=round(target2, 2),
        risk_per_share=round(risk, 2),
        reward_risk_t1=round(rr1, 2),
        reward_risk_t2=round(rr2, 2),
        resistance=round(resistance, 2) if resistance is not None else None,
        reasons=reasons,
    )
