import pandas as pd

from v2.corporate_data import calculated_market_cap_cr, market_cap_max_age_days
from v2.eligibility import evaluate_eligibility


def _prices(rows=260):
    return pd.DataFrame({
        "trade_date": pd.date_range("2025-01-01", periods=rows),
        "open": 100.0, "high": 105.0, "low": 95.0, "close": 100.0,
        "volume": 200_000, "turnover_lacs": 600.0, "delivery_pct": 40.0,
    })


def test_source_aware_market_cap_freshness():
    frame = _prices()
    as_of = str(frame.trade_date.max().date())
    cap_date = str((frame.trade_date.max() - pd.Timedelta(days=100)).date())
    quarterly = evaluate_eligibility("ABC", frame, metadata={
        "series": "EQ", "active": True, "market_cap_cr": 2000,
        "market_cap_as_of": cap_date, "market_cap_source": "CALCULATED_QUARTERLY_SHARES",
    }, as_of_date=as_of)
    direct = evaluate_eligibility("ABC", frame, metadata={
        "series": "EQ", "active": True, "market_cap_cr": 2000,
        "market_cap_as_of": cap_date, "market_cap_source": "NSE_DIRECT_MARKET_CAP",
    }, as_of_date=as_of)
    assert quarterly.eligible
    assert direct.reason_code == "STALE_MARKET_CAP"
    assert market_cap_max_age_days("NSE_ANNUAL_ALL_COMPANIES") == 0


def test_market_cap_calculation_in_crore():
    assert calculated_market_cap_cr(100, 100_000_000) == 1000
