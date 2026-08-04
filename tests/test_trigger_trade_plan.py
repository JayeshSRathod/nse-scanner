from __future__ import annotations

import numpy as np
import pandas as pd

from v2.entry_triggers import EntryTrigger
from v2.trade_plan import build_trigger_trade_plan


def _frame(rows: int = 140) -> pd.DataFrame:
    close = pd.Series(np.linspace(100.0, 145.0, rows))
    return pd.DataFrame({
        "trade_date": pd.date_range("2026-01-01", periods=rows, freq="B"),
        "open": close - 0.5,
        "high": close + 1.0,
        "low": close - 1.5,
        "close": close,
        "volume": np.linspace(100_000, 150_000, rows),
    })


def _trigger(name: str, actionable: bool = True) -> EntryTrigger:
    return EntryTrigger(name, actionable, 80.0, ("test",), {})


def test_no_trigger_returns_wait() -> None:
    plan = build_trigger_trade_plan(_frame(), _trigger("NO_TRIGGER", False), "1M")
    assert plan.state == "WAIT"
    assert plan.valid is False
    assert plan.valid_for_sessions == 3


def test_horizon_controls_expiry() -> None:
    frame = _frame()
    assert build_trigger_trade_plan(frame, _trigger("BREAKOUT"), "1M").valid_for_sessions == 3
    assert build_trigger_trade_plan(frame, _trigger("BREAKOUT"), "3M").valid_for_sessions == 5
    assert build_trigger_trade_plan(frame, _trigger("BREAKOUT"), "6M").valid_for_sessions == 10
    assert build_trigger_trade_plan(frame, _trigger("BREAKOUT"), "12M").valid_for_sessions == 15


def test_trigger_specific_basis_is_recorded() -> None:
    plan = build_trigger_trade_plan(_frame(), _trigger("HULL_CROSSOVER"), "3M")
    assert plan.trigger == "HULL_CROSSOVER"
    assert "crossover_high" in plan.entry_basis
    assert "hull_support" in plan.stop_basis
    assert 0 <= plan.score <= 100


def test_breakout_and_pullback_use_different_stop_logic() -> None:
    frame = _frame()
    breakout = build_trigger_trade_plan(frame, _trigger("BREAKOUT"), "3M")
    pullback = build_trigger_trade_plan(frame, _trigger("QUALIFIED_PULLBACK"), "3M")
    assert breakout.stop_basis != pullback.stop_basis
    assert breakout.entry_basis != pullback.entry_basis


def test_plan_exposes_risk_and_targets() -> None:
    plan = build_trigger_trade_plan(_frame(), _trigger("TREND_CONTINUATION"), "6M")
    assert plan.entry > plan.stop
    assert plan.risk_per_share > 0
    assert plan.target2 > plan.entry
    assert plan.reward_risk_t2 == 3.0
    assert plan.state in {"READY", "WAIT", "RISKY", "INVALID"}
