"""PAPER-only card rendering for the opt-in multi-horizon preview."""
from __future__ import annotations

from html import escape

from telegram_dashboard import status_label


MAX_MESSAGE_CHARS = 3950


def _score(row: dict, horizon: str) -> str:
    value = row.get(f"score_{horizon.lower()}")
    return f"{float(value):.0f}" if value is not None else "—"


def _card(row: dict) -> str:
    symbol = escape(str(row["symbol"]))
    url = f"https://www.tradingview.com/chart/?symbol=NSE%3A{symbol}"
    confirmations = ", ".join(row.get("confirming_horizons") or []) or "none"
    levels = row.get("trade_levels") or {}
    trigger = levels.get("entry_trigger")
    atr = float(row.get("atr", 0) or 0)
    if levels.get("eligible_for_paper") and trigger:
        entry = f"₹{float(trigger):,.2f}–₹{float(trigger) + 0.15 * atr:,.2f}"
        readiness = f"🟢 {status_label('READY')}" if str(row.get("lifecycle_status")) in {"NEW_TRIGGER", "NEWLY_QUALIFIED", "UPGRADED"} else f"🟡 {status_label('CONFIRMING')}"
    else:
        entry = "Awaiting valid structure"
        readiness = f"⚪ {status_label('WAIT')}"
    reason = "Multi-horizon strength • confirmation present" if confirmations != "none" else "Primary horizon qualified • confirmation pending"
    return "\n".join([
        "━━━━━━━━━━━━━━",
        f"{readiness} • <b><a href=\"{url}\">{symbol}</a></b>",
        f"Primary: <b>{escape(str(row.get('primary_horizon', '—')))}</b> | Score: <b>{float(row.get('primary_score', 0)):.0f}/100</b>",
        f"1M {_score(row, '1M')} ✅ • 3M {_score(row, '3M')} {'✅' if '3M' in confirmations else '⚪'}",
        f"6M {_score(row, '6M')} {'✅' if '6M' in confirmations else '⚪'} • 12M {_score(row, '12M')} {'✅' if '12M' in confirmations else '⚪'}",
        f"Entry: {entry}",
        escape(reason),
        f"CMP: ₹{float(row.get('close', 0)):,.2f} | ATR: {float(row.get('atr_pct', 0)):.1f}%",
        "<b>PAPER SHADOW — NOT AN ENTRY</b>",
    ])


def render_messages(report: dict) -> list[str]:
    """Split only between complete cards; never truncate HTML or a candidate."""
    shadow = report.get("multi_horizon_shadow", {})
    summary = shadow.get("comparison_summary", {})
    title = [
        "🪜 <b>LADDER RADAR WATCHLIST</b>",
        "<b>PAPER RESEARCH • BASELINE TELEGRAM UNCHANGED</b>",
        f"Data: {escape(str(shadow.get('as_of_date', 'N/A')))} EOD",
        f"Data health: {escape(str(shadow.get('data_health', {}).get('status', 'N/A')))} | Market context: {escape(str(shadow.get('market_context', {}).get('regime', 'AWAITING_DATA')))}",
        f"Validation: {summary.get('sessions_observed', 0)}/{summary.get('target_sessions', 20)} sessions | "
        f"Baseline avg {summary.get('average_baseline_candidates', 0)} | Shadow avg {summary.get('average_shadow_candidates', 0)} | Overlap avg {summary.get('average_overlap', 0)}",
    ]
    cards = [_card(row) for row in shadow.get("candidates", [])]
    if not cards:
        cards = ["No shadow-qualified candidates today. PAPER observation continues."]
    messages, current = [], "\n".join(title)
    for card in cards:
        if len(current) + len(card) + 2 > MAX_MESSAGE_CHARS:
            messages.append(current)
            current = "\n".join(title[:2]) + "\n" + card
        else:
            current += "\n" + card
    messages.append(current)
    total = len(messages)
    return [f"{message}\n\n🟢 Watch for entry • 🟡 Wait for confirmation • ⚪ No action yet\n<i>Shadow preview {index}/{total}. No live-trading instruction.</i>" for index, message in enumerate(messages, 1)]
