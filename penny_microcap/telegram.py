"""Dedicated Telegram formatting and transport for the penny shadow system."""
from __future__ import annotations

import html
import os
from dataclasses import dataclass

import requests


ICONS = {"READY": "🟢", "CONFIRMING": "🟡", "EARLY_RADAR": "🔵", "CIRCUIT_LOCKED": "🔴", "EXTENDED": "🟠"}


@dataclass(frozen=True)
class DeliveryResult:
    sent: bool
    reason: str


def _link(symbol: str) -> str:
    safe = html.escape(symbol)
    return f'<a href="https://www.tradingview.com/chart/?symbol=NSE%3A{safe}">{safe}</a>'


def _card(row: dict) -> str:
    state, metrics = row["state"], row.get("metrics", {})
    lines = ["━━━━━━━━━━━━━━", f'{ICONS.get(state, "⚪")} <b>{_link(row["symbol"])} • {state} • {row["score"]:.0f}/100</b>',
             f'CMP ₹{row["close"]:.2f}', f'5D {metrics.get("return_5d_pct", 0):+.1f}% • Turnover {metrics.get("turnover_ratio", 0):.1f}× normal']
    if row.get("entry_low") is not None:
        lines.append(f'Probable entry ₹{row["entry_low"]:.2f}–₹{row["entry_high"]:.2f}')
    if state == "CIRCUIT_LOCKED":
        lines.extend(["Current entry: <b>NOT EXECUTABLE</b>", "Next: Wait for normal two-way trading"])
    elif state == "EXTENDED":
        lines.extend([f'Distance {metrics.get("distance_atr", 0):.1f} ATR', "Next: Do not chase; wait for reset"])
    elif state == "READY":
        lines.extend([f'SL ₹{row["stop"]:.2f} • T1 ₹{row["target1"]:.2f} • T2 ₹{row["target2"]:.2f}', "Next: PAPER entry only after next-session fill rules"])
    elif state == "CONFIRMING":
        lines.append("Next: Await executable closed-bar confirmation")
    else:
        lines.append("Next: Confirm sustained participation")
    return "\n".join(lines)


def render_messages(report: dict, *, risk_only: bool = False, limit: int = 3400, cards_per_page: int = 7) -> list[str]:
    risk_states = {"CIRCUIT_LOCKED", "EXTENDED"}
    rows = [r for r in report.get("candidates", []) if (r["state"] in risk_states) == risk_only]
    title = "🚧 <b>PENNY CIRCUIT & RISK</b>" if risk_only else "🪙 <b>PENNY & MICROCAP RADAR</b>"
    counts = report.get("counts", {})
    header = "\n".join([title, f'<b>{report.get("as_of_date", "N/A")} EOD • PAPER ONLY</b>',
        f'Universe {report.get("universe_symbols", 0)} • Selected {report.get("selected", 0)}',
        f'Ready {counts.get("READY",0)} • Confirming {counts.get("CONFIRMING",0)} • Early {counts.get("EARLY_RADAR",0)}', ""])
    footer = "\n\n⚠️ HIGH-RISK MICROCAP RESEARCH — NOT ADVICE"
    pages, current, cards = [], header, 0
    if not rows:
        return [header + ("No new circuit or extension risks." if risk_only else "No qualifying candidates today.") + footer]
    for row in rows:
        card = _card(row)
        if cards and (cards >= cards_per_page or len(current) + len(card) + len(footer) + 2 > limit):
            pages.append(current + footer); current, cards = header, 0
        current += card + "\n"; cards += 1
    pages.append(current.rstrip() + footer)
    return pages


def send_messages(messages: list[str], kind: str, *, enabled: bool, timeout: int = 20) -> DeliveryResult:
    if not enabled: return DeliveryResult(False, "disabled")
    token, chat_id = os.getenv("PENNY_TELEGRAM_BOT_TOKEN", "").strip(), os.getenv("PENNY_TELEGRAM_CHAT_ID", "").strip()
    topic_names = {"daily": "PENNY_DAILY_TOPIC_ID", "risk": "PENNY_RISK_TOPIC_ID", "portfolio": "PENNY_PORTFOLIO_TOPIC_ID",
                   "validation": "PENNY_VALIDATION_TOPIC_ID", "review": "PENNY_REVIEW_TOPIC_ID", "system": "PENNY_SYSTEM_TOPIC_ID"}
    topic = os.getenv(topic_names[kind], "").strip()
    if not token or not chat_id or not topic: return DeliveryResult(False, "telegram_not_configured")
    for message in messages:
        payload = {"chat_id": chat_id, "message_thread_id": int(topic), "text": message, "parse_mode": "HTML", "disable_web_page_preview": True}
        try:
            response = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json=payload, timeout=timeout)
            response.raise_for_status()
        except (requests.RequestException, ValueError) as exc:
            return DeliveryResult(False, f"telegram_failed:{type(exc).__name__}")
    return DeliveryResult(True, "sent")
