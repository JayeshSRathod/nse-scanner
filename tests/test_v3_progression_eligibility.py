import pandas as pd

from v2.eligibility import evaluate_eligibility
from v2.progression import (
    ProgressionStage,
    classify_opportunity,
    next_holding_stage,
    weekly_discovery,
)


def _history(rows=300):
    close = pd.Series([100.0 + i * 0.2 for i in range(rows)])
    return pd.DataFrame({
        "symbol": "ABC",
        "trade_date": pd.bdate_range("2025-01-01", periods=rows),
        "open": close - 0.5,
        "high": close + 1.0,
        "low": close - 1.0,
        "close": close,
        "volume": 250_000,
        "turnover_lacs": 800.0,
        "delivery_pct": 42.0,
        "quality_status": "VALIDATED",
    })


def test_strict_eligibility_passes_liquid_valid_eq_stock():
    result = evaluate_eligibility(
        "ABC", _history(), as_of_date="2026-02-28",
        metadata={"series": "EQ", "active": 1, "market_cap_cr": 5000, "market_cap_as_of": "2026-02-15"},
    )
    assert result.eligible
    assert result.reason_code == "ELIGIBLE"


def test_missing_delivery_fails_closed():
    result = evaluate_eligibility("ABC", _history().drop(columns=["delivery_pct"]), metadata={"series": "EQ"})
    assert not result.eligible
    assert result.reason_code == "DELIVERY_DATA_MISSING"


def test_weekly_discovery_then_fresh_entry():
    discovery = weekly_discovery({
        "weekly_bullish": True, "weekly_rising": True, "daily_bullish": True, "rs63": 0.08,
    })
    assert discovery.stage == ProgressionStage.WEEKLY_CONFIRMED
    label, stage = classify_opportunity(
        None, weekly_stage=discovery.stage, actionable_trigger=True, trade_plan_ready=True,
    )
    assert label == "FRESH_SIGNAL"
    assert stage == ProgressionStage.ENTRY_PENDING


def test_promotions_require_time_and_positive_requalification():
    still_1m = next_holding_stage(
        "ACTIVE_1M", {"3M": "QUALIFIED"}, 19, trend_intact=True,
    )
    assert still_1m.stage == ProgressionStage.ACTIVE_1M
    promoted = next_holding_stage(
        "ACTIVE_1M", {"3M": "QUALIFIED"}, 20, trend_intact=True,
    )
    assert promoted.stage == ProgressionStage.QUALIFIED_3M
    held_6m = next_holding_stage(
        "QUALIFIED_6M", {"12M": "QUALIFIED"}, 130,
        trend_intact=True, fundamentals_passed=None,
    )
    assert held_6m.stage == ProgressionStage.QUALIFIED_6M
    assert held_6m.reason == "twelve_month_fundamental_confirmation_required"
