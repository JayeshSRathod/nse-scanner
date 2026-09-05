"""Mobile-first Telegram rendering for the isolated Pine Hull paper system."""
from __future__ import annotations

from html import escape
from urllib.parse import quote

from telegram_dashboard import status_icon, status_label


def _number(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _price(value: object) -> str:
    return f"₹{_number(value):,.2f}"


def _rank_badge(rank: int) -> str:
    return {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, f"#{rank}")


def _ticker(symbol: object) -> str:
    raw = str(symbol).strip().upper()
    label = escape(raw)
    url = f'https://www.tradingview.com/chart/?symbol={quote("NSE:" + raw, safe="")}'
    return f'<a href="{url}"><b>{label}</b></a>'


def _watch_range(item: dict) -> tuple[float, float]:
    close, atr = _number(item.get("close")), _number(item.get("atr14"))
    supports = [_number(item.get(name)) for name in ("hybrid_hull", "hma21") if _number(item.get(name)) > 0]
    center = max(supports) if item.get("overextended") and supports else max(close, max(supports, default=close))
    return max(0.01, center - 0.15 * atr), center + 0.15 * atr


def render_daily_signals(result: dict) -> str:
    """Render Pine Hull signals in the same decision-first style as V2 ACTION.

    Pine remains an independent paper system and is delivered to the dedicated
    Pine Hull Signals topic; only presentation is aligned with the V2 card UX.
    """
    created = list(result.get("created", []))
    watch = list(result.get("watch", []))
    lines = [
        "📐 PINE HULL SIGNALS",
        f"{len(created)} Fresh Paper Entries • {len(watch)} Watch",
        f"Data: {result.get('trade_date', '-')} close",
        "",
        "Hull55 • HMA21/51 • KAMA30 • ATR14×3.5",
    ]

    if not created:
        lines.extend(["", "✅ Scan completed", "Fresh Signals: 0", "No new qualified Pine Hull entry today."])
    for rank, position in enumerate(created, 1):
        weekly = "Confirmed" if position.get("htf_weekly_bullish") else "Pending / weak"
        entry = _number(position["entry"])
        entry_high = entry + 0.15 * max(0.0, _number(position.get("target1")) - entry) / 1.5
        lines.extend([
            "",
            "━━━━━━━━━━━━━━",
            f"{status_icon('NEW_TRIGGER')} {_ticker(position['symbol'])} • <b>{status_label('NEW_TRIGGER')} • {_number(position.get('score')):.0f}/100</b>",
            f"CMP {_price(position.get('last_price', entry))}",
            "Evidence: Hull pullback continuation • Daily Hull bullish",
            f"Entry: {_price(entry)}–{_price(entry_high)}",
            f"SL {_price(position['initial_stop'])} | T1 {_price(position['target1'])} | T2 {_price(position['target2'])}",
            f"Context: Weekly {weekly} • HMA21 > HMA51 • KAMA30 rising",
            "Next: Act only after trigger confirmation",
            "PAPER ONLY",
        ])

    if watch:
        lines.extend(["", "👀 <b>HULL PINE WATCHLIST</b>", f"{result.get('trade_date', '-')} EOD • {len(watch)} stocks"])
        for item in watch:
            timing = str(item.get("timing_state", "EARLY"))
            state = "EXTENDED" if item.get("overextended") else "EARLY" if timing == "EARLY" else "CONFIRMING"
            reason = "Hull rising • commitment pending"
            if item.get("overextended"):
                reason = "Extended price • wait for reset"
            elif item.get("chop") or item.get("rotational"):
                state, reason = "WAIT", "Sideways movement • confirmation missing"
            low, high = _watch_range(item)
            lines.extend(["", "━━━━━━━━━━━━━━", f"{status_icon(state)} {_ticker(item['symbol'])} • <b>{status_label(state)} • {_number(item.get('score')):.0f}/100</b>",
                          f"CMP {_price(item.get('close'))}", f"Entry: {_price(low)}–{_price(high)}", f"Context: {reason}",
                          "Next: Await executable closed-bar confirmation", "PAPER ONLY"])
        lines.extend(["", "🟢 Watch for entry • 🟡 Wait for confirmation • 🔵 Early watchlist • ⚪ No action yet", "PAPER — enter only after trigger confirmation."])

    return "\n".join(lines)
