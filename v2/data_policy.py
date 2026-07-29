"""V2 data-retention and freshness policy.

V1 loader behavior is intentionally unchanged. V2 reads the existing seed
history and manages its own retention/freshness controls.
"""
from __future__ import annotations

import os

SEED_HISTORY_SESSIONS = int(os.getenv("V2_SEED_HISTORY_SESSIONS", "420"))
MIN_INDICATOR_SESSIONS = int(os.getenv("V2_MIN_INDICATOR_SESSIONS", "260"))
MIN_FULL_RANKING_SESSIONS = int(os.getenv("V2_MIN_FULL_RANKING_SESSIONS", "400"))
RECENT_REPAIR_SESSIONS = int(os.getenv("V2_RECENT_REPAIR_SESSIONS", "5"))


def validate_policy() -> None:
    if SEED_HISTORY_SESSIONS < MIN_FULL_RANKING_SESSIONS:
        raise ValueError("V2 seed history must cover full-ranking lookback")
    if MIN_FULL_RANKING_SESSIONS < MIN_INDICATOR_SESSIONS:
        raise ValueError("full-ranking history must exceed indicator minimum")
    if RECENT_REPAIR_SESSIONS < 1:
        raise ValueError("recent repair window must be positive")
