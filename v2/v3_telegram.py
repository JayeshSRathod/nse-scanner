"""Safe, presentation-only primitives for V3 Telegram reports."""
from __future__ import annotations

import hashlib
from html import escape
from urllib.parse import quote

MAX_MESSAGE_CHARS = 3400


def text(value: object | None) -> str:
    return "N/A" if value is None or str(value).strip() == "" else escape(str(value))


def currency(value: float | None, decimals: int = 2) -> str:
    return "N/A" if value is None else f"₹{value:,.{decimals}f}"


def percent(value: float | None) -> str:
    return "N/A" if value is None else f"{value:+.2f}%"


def ticker(symbol: object) -> str:
    label = text(symbol).upper()
    raw = str(symbol).strip().upper()
    if not raw or any(char not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789&-" for char in raw):
        return f"<b>{label}</b>"
    return f'<a href="https://www.tradingview.com/chart/?symbol={quote("NSE:" + raw, safe="")}"><b>{label}</b></a>'


def fingerprint(scan_date: str, message_type: str, topic_id: int | None, page: int, body: str) -> str:
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]
    return f"{scan_date}:{message_type}:{topic_id or 'general'}:{page}:{digest}"


def paginate_cards(header: str, cards: list[str], footer: str = "") -> list[str]:
    if not cards:
        return [header + ("\n\n" + footer if footer else "")]
    pages, current = [], header
    for card in cards:
        candidate = f"{current}\n\n{card}"
        if len(candidate) > MAX_MESSAGE_CHARS and current != header:
            pages.append(current)
            current = f"{header}\n\n{card}"
        else:
            current = candidate
    pages.append(current + ("\n\n" + footer if footer else ""))
    if len(pages) == 1:
        return pages
    return [page.replace(header, f"{header} ({index}/{len(pages)})", 1) for index, page in enumerate(pages, 1)]
