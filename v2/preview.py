"""Telegram market summary, compact ACTION cards and WATCH guidance."""
from __future__ import annotations

from collections.abc import Iterable

from .candidates import Candidate
from .freshness import FreshnessStatus
from .portfolio_risk import Allocation


HORIZON_LABELS = {"1M": "1 month", "3M": "3 months", "6M": "6 months", "12M": "12 months"}
ACTION_SECTION_LABELS = {
    "1M": "1M SWING — 2 to 6 weeks",
    "3M": "3M POSITIONAL — 1 to 3 months",
    "6M": "6M TREND — 3 to 6 months",
    "12M": "12M COMPOUNDER — 6 to 12 months",
}
TRIGGER_LABELS = {
    "QUALIFIED_PULLBACK": "QUALIFIED PULLBACK", "BREAKOUT": "BREAKOUT",
    "COMPRESSION_RELEASE": "COMPRESSION RELEASE", "HULL_CROSSOVER": "HYBRID HULL CROSSOVER",
    "KAMA_ALIGNMENT": "KAMA ALIGNMENT", "RS_ACCELERATION": "RELATIVE-STRENGTH ACCELERATION",
    "TREND_CONTINUATION": "TREND CONTINUATION", "REACCUMULATION": "RE-ACCUMULATION",
    "NO_TRIGGER": "NO CURRENT TRIGGER",
}


def _price(value: float) -> str:
    return f"₹{value:,.2f}"


def _status(freshness: FreshnessStatus | None) -> str:
    if freshness is None:
        return "Fresh"
    return "Warning — latest data needs review" if freshness.degraded else "Fresh"


def _score_line(candidate: Candidate) -> str:
    values = []
    for horizon in ("1M", "3M", "6M", "12M"):
        row = candidate.horizon_scores.get(horizon, {})
        score, state = row.get("score"), row.get("state", "")
        if score is not None:
            marker = "Q" if state == "QUALIFIED" else ("W" if state == "WATCH" else "-")
            values.append(f"{horizon} {float(score):.0f}{marker}")
    return " | ".join(values)


def _reason_lines(candidate: Candidate) -> list[str]:
    readable = []
    for reason in candidate.reasons_for:
        text = reason.replace("_", " ").strip().capitalize()
        if text and text not in readable:
            readable.append(text)
    return readable[:5]


def _chunk_cards(cards: list[str], header: str, limit: int = 3800) -> list[str]:
    if not cards:
        return []
    messages, current = [], header
    for card in cards:
        candidate = f"{current}\n\n{card}" if current else card
        if len(candidate) <= limit:
            current = candidate
        else:
            if current:
                messages.append(current)
            current = f"{header}\n\n{card}"
    if current:
        messages.append(current)
    total = len(messages)
    if total == 1:
        return messages
    return [message.replace(header, f"{header} — {index}/{total}", 1) for index, message in enumerate(messages, 1)]


def _rank_badge(rank: int) -> str:
    return {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, f"#{rank}")


def _action_card(candidate: Candidate, rank: int, allocations: dict[tuple[str, str], Allocation] | None) -> str:
    """Render the frozen mobile-first ACTION card.

    Detailed entry/stop construction and component-score diagnostics remain in
    persisted/admin data; the user message is intentionally decision-oriented.
    """
    del allocations  # allocation details stay out of the compact user card
    trigger = TRIGGER_LABELS.get(candidate.entry_trigger, candidate.entry_trigger.replace("_", " ").upper())
    lines = [
        "━━━━━━━━━━━━━━━━━━",
        f"{_rank_badge(rank)} {candidate.symbol}",
        f"{candidate.primary_horizon} • {trigger}",
        f"Score: {candidate.score:.0f}/100",
        "",
        f"Entry       {_price(candidate.entry)}",
        f"SL          {_price(candidate.stop)}",
        f"T1          {_price(candidate.target1)}",
        f"T2          {_price(candidate.target2)}",
        "",
        f"Risk        {candidate.risk_percent:.2f}%",
        f"RR          {candidate.reward_risk_t1:.2f}R / {candidate.reward_risk_t2:.2f}R",
        f"Validity    {candidate.valid_for_sessions} sessions",
    ]
    reasons = _reason_lines(candidate)
    if reasons:
        lines.append("")
        lines.extend(f"✓ {reason}" for reason in reasons)
    return "\n".join(lines)


def _action_messages(
    action_rows: list[Candidate],
    allocations: dict[tuple[str, str], Allocation] | None,
) -> list[str]:
    """Render every ACTION candidate in one ranked stream, safely chunked."""
    if not action_rows:
        return []
    cards = [_action_card(candidate, rank, allocations) for rank, candidate in enumerate(action_rows, 1)]
    header = f"🚀 ACTION CANDIDATES\n{len(action_rows)} Fresh Actionable Stocks"
    return _chunk_cards(cards, header)


def _watch_reason(candidate: Candidate) -> str:
    if candidate.trade_plan_state in {"WAIT", "RISKY"}:
        return f"Trade plan {candidate.trade_plan_state.lower()}"
    if candidate.entry_trigger == "NO_TRIGGER":
        return "No actionable trigger"
    if candidate.metrics.get("stretched"):
        return "Extended"
    if candidate.pullback_state == "DEEP_PULLBACK":
        return "Deep pullback — confirmation pending"
    return "Qualified quality — waiting for entry"


def _watch_entry_guidance(candidate: Candidate) -> tuple[float, float, float, str] | None:
    """Return a non-actionable preferred retest/reclaim zone for WATCH stocks.

    WATCH is intentionally different from ACTION. The suggested level is a
    structural area to monitor; a fresh trigger is still required before the
    stock can move to ACTION. Shorter horizons use the faster HMA21/Hull area,
    while 6M/12M use the slower Hull/HMA51 structure and a wider ATR allowance.
    """
    metrics = candidate.metrics or {}
    try:
        hull55 = float(metrics.get("hull55", 0.0) or 0.0)
        hma21 = float(metrics.get("hma21", 0.0) or 0.0)
        hma51 = float(metrics.get("hma51", 0.0) or 0.0)
        atr14 = float(metrics.get("atr14", 0.0) or 0.0)
    except (TypeError, ValueError):
        hull55 = hma21 = hma51 = atr14 = 0.0

    if atr14 > 0:
        if candidate.primary_horizon in {"1M", "3M"}:
            supports = [value for value in (hull55, hma21) if value > 0]
            allowance = {"1M": 0.20, "3M": 0.30}[candidate.primary_horizon]
            basis = "Hull55/HMA21 retest"
        else:
            supports = [value for value in (hull55, hma51) if value > 0]
            allowance = {"6M": 0.40, "12M": 0.50}.get(candidate.primary_horizon, 0.35)
            basis = "Hull55/HMA51 structural retest"
        if supports:
            support = max(supports)
            low = max(0.01, support - allowance * atr14)
            high = support + 0.15 * atr14
            preferred = (low + high) / 2.0
            return round(preferred, 2), round(low, 2), round(high, 2), basis

    if candidate.entry > 0:
        return candidate.entry, candidate.entry, candidate.entry, "existing trigger reference"
    return None


def _watch_card(candidate: Candidate, rank: int) -> str:
    lines = [
        f"{rank}. {candidate.symbol} | {candidate.primary_horizon} | Score {candidate.score:.0f}",
        f"Status: {_watch_reason(candidate)}",
    ]
    guidance = _watch_entry_guidance(candidate)
    if guidance:
        preferred, low, high, basis = guidance
        if low == high:
            lines.append(f"Preferred Entry: {_price(preferred)} — confirmation required")
        else:
            lines.append(f"Preferred Entry: {_price(preferred)} | Zone: {_price(low)}–{_price(high)}")
        lines.append(f"Entry basis: {basis}")
    lines.append("Action: WAIT for a fresh trigger; this is not an active buy signal.")
    return "\n".join(lines)


def render_candidate_messages(
    actions: Iterable[Candidate], watches: Iterable[Candidate], regime: str, trade_date: str, *,
    freshness: FreshnessStatus | None = None, evaluated: int | None = None,
    benchmark_source: str = "", allocations: dict[tuple[str, str], Allocation] | None = None,
    tradable: int | None = None, quality_qualified: int | None = None,
) -> list[str]:
    action_rows = sorted(list(actions), key=lambda row: (-row.score, -row.trade_plan_score, row.symbol))
    watch_rows = sorted(list(watches), key=lambda row: (-row.score, row.symbol))
    benchmark = "Official NIFTY index history" if benchmark_source == "OFFICIAL_INDEX_HISTORY" else "Equal-weight NSE universe (official index history unavailable)"
    summary = [
        "📊 KJ NSE SCANNER V2 — DAILY CANDIDATES", f"Trade Date: {trade_date}",
        f"Market Regime: {regime.upper()}", f"Data Status: {_status(freshness)}",
        f"Benchmark: {benchmark}", "", "Scanner Funnel",
        f"Universe Loaded: {evaluated if evaluated is not None else '-'}",
        f"Tradable/Evaluated: {tradable if tradable is not None else (evaluated if evaluated is not None else '-')}",
        f"Quality Qualified: {quality_qualified if quality_qualified is not None else len(action_rows) + len(watch_rows)}",
        "Focus Scores: 1M/3M 80+ | 6M/12M 82+",
        f"Fresh Actionable: {len(action_rows)}", f"Focus Watchlist: {len(watch_rows)}",
    ]
    if not action_rows:
        summary.extend(["", "No new candidates met the qualified-quality, actionable-trigger and READY trade-plan criteria today."])
    messages = ["\n".join(summary)]
    messages.extend(_action_messages(action_rows, allocations))
    if watch_rows:
        cards: list[str] = []
        rank = 1
        for horizon in ("1M", "3M", "6M", "12M"):
            rows = [candidate for candidate in watch_rows if candidate.primary_horizon == horizon]
            if not rows:
                continue
            cards.append(ACTION_SECTION_LABELS[horizon])
            for candidate in rows:
                cards.append(_watch_card(candidate, rank))
                rank += 1
        messages.extend(_chunk_cards(cards, "🟡 FOCUS WATCHLIST — PREFERRED ENTRY AREAS, NOT ACTIVE BUY SIGNALS"))
    return messages


def render_candidate_preview(
    grouped: dict[str, list[Candidate]], regime: str, trade_date: str, *,
    freshness: FreshnessStatus | None = None, evaluated: int | None = None,
    max_candidates: int = 5, allocations: dict[tuple[str, str], Allocation] | None = None,
) -> str:
    """Backward-compatible single-message preview for legacy tests and inspection."""
    rows = [candidate for candidates in grouped.values() for candidate in candidates]
    messages = render_candidate_messages(rows[:max_candidates], [], regime, trade_date,
        freshness=freshness, evaluated=evaluated, allocations=allocations)
    text = "\n\n".join(messages)
    if rows:
        first = rows[0]
        text = (
            "📊 KJ NSE SCANNER V2\n" + text +
            f"\n\nEntry Trigger: {_price(first.entry)}\n"
            "Hybrid Hull (fixed):\n"
            f"Daily: {'Bullish' if first.metrics.get('daily_bullish') else 'Not aligned'}\n"
            f"Weekly: {'Bullish' if first.metrics.get('weekly_bullish') else 'Not aligned'}"
        )
    return text