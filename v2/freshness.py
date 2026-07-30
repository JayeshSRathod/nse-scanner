"""Freshness and degraded-mode controls for NSE Scanner V2."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd


@dataclass(frozen=True)
class FreshnessStatus:
    as_of: str
    price_date: str | None
    index_date: str | None
    price_age_days: int | None
    index_age_days: int | None
    prices_stale: bool
    indices_stale: bool
    degraded: bool
    reasons: tuple[str, ...]


def _age(as_of: date, value: object) -> int | None:
    if value is None or pd.isna(value):
        return None
    return (as_of - pd.Timestamp(value).date()).days


def assess_freshness(
    prices: pd.DataFrame,
    indices: pd.DataFrame,
    as_of: date | str,
    max_price_age_days: int = 4,
    max_index_age_days: int = 4,
) -> FreshnessStatus:
    day = pd.Timestamp(as_of).date()
    price_value = prices["trade_date"].max() if not prices.empty else None
    index_value = indices["trade_date"].max() if not indices.empty else None
    price_age = _age(day, price_value)
    index_age = _age(day, index_value)
    prices_stale = price_age is None or price_age > max_price_age_days
    indices_stale = index_age is None or index_age > max_index_age_days
    reasons: list[str] = []
    if price_age is None:
        reasons.append("price_history_missing")
    elif prices_stale:
        reasons.append(f"price_history_{price_age}_days_old")
    if index_age is None:
        reasons.append("index_history_missing")
    elif indices_stale:
        reasons.append(f"index_history_{index_age}_days_old")
    return FreshnessStatus(
        as_of=day.isoformat(),
        price_date=pd.Timestamp(price_value).date().isoformat() if price_value is not None else None,
        index_date=pd.Timestamp(index_value).date().isoformat() if index_value is not None else None,
        price_age_days=price_age,
        index_age_days=index_age,
        prices_stale=prices_stale,
        indices_stale=indices_stale,
        degraded=prices_stale or indices_stale,
        reasons=tuple(reasons),
    )
