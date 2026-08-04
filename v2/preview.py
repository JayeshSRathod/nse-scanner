"""Telegram market summary, complete ACTION delivery and compact WATCH output."""
from __future__ import annotations

from collections.abc import Iterable

from .candidates import Candidate
from .freshness import FreshnessStatus
from .portfolio_risk import Allocation


HORIZON_LABELS = {"1M": "1 month", "3M": "3 months", "6M": "6 months", "12M": "12 months"}
TRIGGER_LABELS = {
    "QUALIFIED_PULLBACK": "Qualified pullback", "BREAKOUT": "Breakout",
    "COMPRESSION_RELEASE": "Compression release", "HULL_CROSSOVER": "Hybrid Hull crossover",
    "KAMA_ALIGNMENT": "KAMA alignment", "RS_ACCELERATION": "Relative-strength acceleration",
    "TREND_CONTINUATION": "Trend continuation", "REACCUMULATION": "Re-accumulation",
    "NO_TRIGGER": "No current trigger",
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


def _component_lines(candidate: Candidate) -> list[str]:
    components = candidate.horizon_scores.get(candidate.primary_horizon, {}).get("component_scores", {})
    ordered = sorted(components.items(), key=lambda item: (-float(item[1]), item[0]))
    return [f"• {name.replace('_', ' ').title()}: {float(points):.1f}" for name, points in ordered[:5]]


def _reason_lines(candidate: Candidate) -> list[str]:
    readable = []
    for reason in candidate.reasons_for:
        text = reason.replace("_", " ").strip().capitalize()
        if text and text not in readable:
            readable.append(text)
    return readable[:4]


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
    return [message.replace(header, f"{header} — {index}/{total}", 1) for index, message in enumerate(messages, 1)]


def _action_card(candidate: Candidate, rank: int, allocations: dict[tuple[str, str], Allocation] | None) -> str:
    allocation = (allocations or {}).get((candidate.symbol, candidate.horizon))
    lines = [
        f"{rank}. {candidate.symbol}",
        f"State: ACTION | Primary: {candidate.primary_horizon}",
        f"Horizon Scores: {_score_line(candidate)}",
        f"Trigger: {TRIGGER_LABELS.get(candidate.entry_trigger, candidate.entry_trigger)} ({candidate.trigger_score:.0f}/100)",
        f"Trade Plan: {candidate.trade_plan_state} ({candidate.trade_plan_score:.0f}/100)",
        f"Entry: {_price(candidate.entry)} | SL: {_price(candidate.stop)}",
        f"T1: {_price(candidate.target1)} | T2: {_price(candidate.target2)}",
        f"RR: {candidate.reward_risk_t1:.2f}R / {candidate.reward_risk_t2:.2f}R | Risk: {candidate.risk_percent:.2f}%",
        f"Valid: {candidate.valid_for_sessions} trading sessions",
    ]
    if allocation:
        lines.append(
            f"Proposed Quantity: {allocation.quantity} | Capital: {_price(allocation.entry_notional)} | Initial Risk: {_price(allocation.initial_risk)}"
        )
    lines.extend([f"Entry basis: {candidate.entry_basis}", f"Stop basis: {candidate.stop_basis}"])
    reasons = _reason_lines(candidate)
    if reasons:
        lines.append("Why selected:")
        lines.extend(f"• {reason}" for reason in reasons)
    components = _component_lines(candidate)
    if components:
        lines.append(f"{candidate.primary_horizon} score breakdown:")
        lines.extend(components)
    return "\n".join(lines)


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
        f"Fresh Actionable: {len(action_rows)}", f"Watchlist: {len(watch_rows)}",
    ]
    if not action_rows:
        summary.extend(["", "No new candidates met the qualified-quality, actionable-trigger and READY trade-plan criteria today."])
    messages = ["\n".join(summary)]
    cards = [_action_card(candidate, rank, allocations) for rank, candidate in enumerate(action_rows, 1)]
    messages.extend(_chunk_cards(cards, "🟢 ALL ACTIONABLE CANDIDATES"))
    if watch_rows:
        watch_lines = ["🟡 WATCHLIST — QUALIFIED, NO READY ENTRY"]
        for index, candidate in enumerate(watch_rows, 1):
            watch_lines.append(f"{index}. {candidate.symbol} | {candidate.primary_horizon} {candidate.score:.0f} | {_watch_reason(candidate)}")
        watch_text = "\n".join(watch_lines)
        messages.append(watch_text) if len(watch_text) <= 3900 else messages.extend(_chunk_cards(watch_lines[1:], watch_lines[0]))
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
