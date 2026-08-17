"""Strict, auditable NSE-universe eligibility for the progressive scanner."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Mapping

import pandas as pd


@dataclass(frozen=True)
class EligibilityResult:
    symbol: str
    eligible: bool
    reason_code: str
    stage: str
    actual_value: float | str | None = None
    required_value: float | str | None = None
    metrics: dict[str, float | str | bool] | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def evaluate_eligibility(
    symbol: str,
    frame: pd.DataFrame,
    *,
    metadata: Mapping[str, object] | None = None,
    restricted_reason: str | None = None,
    min_sessions: int = 260,
    min_price: float = 50.0,
    min_median_volume_20: float = 100_000.0,
    min_median_turnover_cr_20: float = 5.0,
    min_delivery_5: float = 35.0,
    min_delivery_20: float = 30.0,
    min_market_cap_cr: float = 1_000.0,
) -> EligibilityResult:
    ordered = frame.sort_values("trade_date").copy()
    metadata = metadata or {}

    def reject(stage: str, code: str, actual: object = None, required: object = None) -> EligibilityResult:
        return EligibilityResult(symbol, False, code, stage, actual, required)

    if ordered["trade_date"].duplicated().any():
        return reject("DATA_QUALITY", "DUPLICATE_DATES")
    data = ordered
    if len(data) < min_sessions:
        return reject("DATA_QUALITY", "INSUFFICIENT_HISTORY", len(data), min_sessions)
    prices = data[["open", "high", "low", "close"]].apply(pd.to_numeric, errors="coerce")
    if prices.isna().any().any() or (prices <= 0).any().any():
        return reject("DATA_QUALITY", "INVALID_PRICE")
    if (prices["high"] < prices[["open", "low", "close"]].max(axis=1)).any() or (
        prices["low"] > prices[["open", "high", "close"]].min(axis=1)
    ).any():
        return reject("DATA_QUALITY", "INVALID_OHLC")
    if "quality_status" in data and data["quality_status"].iloc[-1] not in {"VALID", "VALIDATED", "OK"}:
        return reject("DATA_QUALITY", "UNVALIDATED_LATEST_ROW", data["quality_status"].iloc[-1], "VALIDATED")

    series = str(metadata.get("series", "EQ") or "EQ").upper()
    if series != "EQ":
        return reject("TRADEABILITY", "NON_EQ_SERIES", series, "EQ")
    if metadata.get("active") is not None and not bool(metadata.get("active")):
        return reject("TRADEABILITY", "INACTIVE_SECURITY")
    if restricted_reason:
        return reject("REGULATORY", "RESTRICTED_SECURITY", restricted_reason, "NOT_RESTRICTED")

    close = float(prices["close"].iloc[-1])
    if close < min_price:
        return reject("LIQUIDITY", "LOW_PRICE", close, min_price)
    volume = pd.to_numeric(data["volume"], errors="coerce")
    median_volume = float(volume.tail(20).median())
    if pd.isna(median_volume) or median_volume < min_median_volume_20:
        return reject("LIQUIDITY", "LOW_MEDIAN_VOLUME", median_volume, min_median_volume_20)

    if "turnover_lacs" not in data:
        return reject("LIQUIDITY", "TURNOVER_DATA_MISSING", None, min_median_turnover_cr_20)
    turnover_cr = pd.to_numeric(data["turnover_lacs"], errors="coerce") / 100.0
    median_turnover = float(turnover_cr.tail(20).median())
    if pd.isna(median_turnover) or median_turnover < min_median_turnover_cr_20:
        return reject("LIQUIDITY", "LOW_MEDIAN_TURNOVER", median_turnover, min_median_turnover_cr_20)

    if "delivery_pct" not in data:
        return reject("PARTICIPATION", "DELIVERY_DATA_MISSING", None, min_delivery_20)
    delivery = pd.to_numeric(data["delivery_pct"], errors="coerce")
    delivery_5, delivery_20 = float(delivery.tail(5).mean()), float(delivery.tail(20).mean())
    if pd.isna(delivery_5) or delivery_5 < min_delivery_5:
        return reject("PARTICIPATION", "LOW_DELIVERY_5D", delivery_5, min_delivery_5)
    if pd.isna(delivery_20) or delivery_20 < min_delivery_20:
        return reject("PARTICIPATION", "LOW_DELIVERY_20D", delivery_20, min_delivery_20)

    market_cap = metadata.get("market_cap_cr")
    if market_cap is not None and pd.notna(market_cap) and float(market_cap) < min_market_cap_cr:
        return reject("SIZE", "LOW_MARKET_CAP", float(market_cap), min_market_cap_cr)

    return EligibilityResult(symbol, True, "ELIGIBLE", "COMPLETE", metrics={
        "close": close,
        "median_volume_20": median_volume,
        "median_turnover_cr_20": median_turnover,
        "delivery_5": delivery_5,
        "delivery_20": delivery_20,
        "market_cap_verified": market_cap is not None and pd.notna(market_cap),
    })
