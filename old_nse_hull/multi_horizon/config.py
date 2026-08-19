"""Configuration for the isolated Old NSE + Hull multi-horizon shadow run."""
from __future__ import annotations

import os


def shadow_enabled() -> bool:
    """Return whether the experimental engine is explicitly enabled.

    The default is deliberately off, so a normal Old NSE + Hull run remains
    byte-for-byte on its established baseline path.
    """
    return os.getenv("OLD_NSE_HULL_MULTI_HORIZON_MODE", "off").strip().lower() == "shadow"


MIN_HISTORY = 320
MIN_PRICE = 50.0
MIN_AVG_VOLUME = 50_000.0
QUALIFIED_SCORE = 65.0
CONFIRMING_SCORE = 55.0
