"""Frozen PAPER defaults for the progressive penny-stock funnel."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PennyConfig:
    strategy_version: str = "penny-shadow-v2-acceleration"
    min_price: float = 1.0
    max_price: float = 49.99
    radar_history: int = 120
    confirming_history: int = 180
    ready_history: int = 260
    radar_turnover_lacs: float = 20.0
    confirming_turnover_lacs: float = 40.0
    confirming_recent_turnover_lacs: float = 60.0
    ready_turnover_lacs: float = 60.0
    ready_recent_turnover_lacs: float = 100.0
    high_liquidity_turnover_lacs: float = 100.0
    high_liquidity_recent_lacs: float = 200.0
    ready_delivery_5: float = 30.0
    ready_delivery_20: float = 25.0
    ready_market_cap_cr: float = 100.0
    max_ready_distance_atr: float = 1.0
    extended_distance_atr: float = 1.5
    max_stop_risk_pct: float = 12.0
    min_reward_risk: float = 2.5
    radar_score: float = 35.0
    confirming_score: float = 50.0
    ready_review_score: float = 65.0
    ready_score: float = 75.0
    max_cards_per_message: int = 7
    telegram_message_limit: int = 3400
