"""Point-in-time NSE corporate-data policies and calculations.

Submission/broadcast dates are deliberately separate from period end dates so
backtests cannot see a filing before it was available to the market.
"""
from __future__ import annotations

from dataclasses import dataclass


MARKET_CAP_MAX_AGE_DAYS = {
    "NSE_DIRECT_MARKET_CAP": 45,
    "DIRECT_SNAPSHOT": 45,
    "CALCULATED_QUARTERLY_SHARES": 120,
}


def market_cap_max_age_days(source: str) -> int:
    normalized = str(source or "DIRECT_SNAPSHOT").strip().upper()
    # Annual reports are classification/backfill evidence, never a live cap.
    if normalized == "NSE_ANNUAL_ALL_COMPANIES":
        return 0
    return MARKET_CAP_MAX_AGE_DAYS.get(normalized, 45)


def calculated_market_cap_cr(close: float, shares_outstanding: float) -> float:
    if close <= 0 or shares_outstanding <= 0:
        raise ValueError("close and shares_outstanding must be positive")
    return close * shares_outstanding / 10_000_000.0


@dataclass(frozen=True)
class GovernanceEvent:
    event_type: str
    severity: str

    @property
    def hard_block(self) -> bool:
        return self.severity.upper() == "SEVERE"

