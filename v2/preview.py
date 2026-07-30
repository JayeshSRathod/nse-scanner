"""Telegram Message 1: a compact, actionable V2 candidate shortlist."""
from __future__ import annotations

from .candidates import Candidate
from .freshness import FreshnessStatus
from .portfolio_risk import Allocation


HORIZON_LABELS = {
    "SWING_1_3M": "Swing (1–3 months)",
    "POSITIONAL_3_6M": "Positional (3–6 months)",
    "POSITIONAL_6_12M": "Long-term (6–12 months)",
}
SETUP_LABELS = {
    "BREAKOUT": "Trend continuation",
    "PULLBACK": "Pullback continuation",
    "COMPRESSION": "Breakout preparation",
}


def _price(value: float) -> str:
    return f"₹{value:,.2f}"


def _status(freshness: FreshnessStatus | None) -> str:
    if freshness is None:
        return "Fresh"
    if freshness.degraded:
        return "Warning — latest data needs review"
    return "Fresh"


def _reason_lines(candidate: Candidate) -> list[str]:
    setup = SETUP_LABELS.get(candidate.setup, candidate.setup.replace("_", " ").title())
    reasons = [f"{setup} pattern passed the V2 quality score."]
    if candidate.metrics.get("daily_bullish"):
        reasons.append("Daily Hybrid Hull is up: price above Hull55 and HMA21 above HMA51.")
    if candidate.metrics.get("weekly_bullish"):
        reasons.append("Weekly HMA21/HMA51 trend is aligned upward.")
    if candidate.metrics.get("kama_rising"):
        reasons.append("KAMA30 is rising, confirming daily momentum.")
    return reasons[:3]


def render_candidate_preview(
    grouped: dict[str, list[Candidate]],
    regime: str,
    trade_date: str,
    *,
    freshness: FreshnessStatus | None = None,
    evaluated: int | None = None,
    max_candidates: int = 5,
    allocations: dict[tuple[str, str], Allocation] | None = None,
) -> str:
    """Render only the best actionable candidates; keep below Telegram's size limit."""
    rows = [candidate for candidates in grouped.values() for candidate in candidates]
    rows = sorted(rows, key=lambda candidate: candidate.score, reverse=True)
    shown = rows[:max_candidates]
    lines = [
        "📊 KJ NSE SCANNER V2",
        f"Trade Date: {trade_date}",
        f"Market Regime: {regime.upper()}",
        f"Data Status: {_status(freshness)}",
    ]
    if evaluated is not None:
        lines.append(f"Universe Scanned: {evaluated} stocks")
    lines.extend([f"Qualified Candidates: {len(rows)}", "", "━━━━━━━━━━━━━━━━━━"])
    if not rows:
        return "\n".join(lines + ["No new candidates met the Hybrid Hull, quality and risk criteria today.",
                                    "Existing positions are monitored in the separate lifecycle report."])

    for rank, candidate in enumerate(shown, start=1):
        metric = candidate.metrics
        allocation = (allocations or {}).get((candidate.symbol, candidate.horizon))
        daily = "Bullish" if metric.get("daily_bullish") else "Not aligned"
        weekly = "Bullish" if metric.get("weekly_bullish") else "Not aligned"
        lines.extend([
            f"{rank}️⃣ {candidate.symbol}",
            f"Horizon: {HORIZON_LABELS.get(candidate.horizon, candidate.horizon)}",
            f"Setup: {SETUP_LABELS.get(candidate.setup, candidate.setup.title())}",
            f"Score: {candidate.score:.0f}/100 | State: READY",
            "",
            f"Entry Trigger: {_price(candidate.entry)}",
            f"Stop Loss: {_price(candidate.stop)}",
            f"Target 1: {_price(candidate.target1)} | Target 2: {_price(candidate.target2)}",
            f"Risk: {_price(candidate.entry - candidate.stop)}/share",
            f"Reward to T1: {candidate.reward_risk_t1:.2f}R | Reward to T2: {candidate.reward_risk_t2:.2f}R",
            (f"Proposed Quantity: {allocation.quantity} | Capital: {_price(allocation.entry_notional)} | "
             f"Initial Risk: {_price(allocation.initial_risk)}"
             if allocation else "Allocation: portfolio capacity is currently unavailable."),
            "",
            "Hybrid Hull (fixed):",
            f"Daily: {daily} — Hull55 / HMA21 / HMA51",
            f"Weekly: {weekly} — HMA21 / HMA51 | KAMA30: {'Rising' if metric.get('kama_rising') else 'Not rising'}",
            f"ATR14 × 3.5 trail: {_price(float(metric.get('trail_stop', candidate.stop)))}",
            "Reason:",
            *[f"• {reason}" for reason in _reason_lines(candidate)],
            "━━━━━━━━━━━━━━━━━━",
        ])
    if len(rows) > len(shown):
        lines.append(f"Showing the strongest {len(shown)} of {len(rows)} qualified candidates.")
    lines.extend([
        "Scanner rule: no entry unless the stated trigger is reached.",
        "Quantity follows the configured ₹3,00,000 risk limits; entry remains manual.",
    ])
    return "\n".join(lines)
