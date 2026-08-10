"""Mobile-first Telegram rendering for the isolated Pine Hull paper system."""
from __future__ import annotations


def _number(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _price(value: object) -> str:
    return f"₹{_number(value):,.2f}"


def _rank_badge(rank: int) -> str:
    return {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, f"#{rank}")


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
        lines.extend([
            "",
            "━━━━━━━━━━━━━━━━━━",
            f"{_rank_badge(rank)} {position['symbol']}",
            "PINE HULL • READY LONG",
            f"Score: {_number(position.get('score')):.0f}/100" if position.get("score") is not None else "Paper Signal: READY",
            "",
            f"Entry       {_price(position['entry'])}",
            f"SL          {_price(position['initial_stop'])}",
            f"T1          {_price(position['target1'])}",
            f"T2          {_price(position['target2'])}",
            "",
            f"Weekly HTF  {weekly}",
            "✓ Daily Hull bullish",
            "✓ HMA21 > HMA51",
            "✓ KAMA30 rising",
            "✓ Trend commitment confirmed",
            "",
            "Paper entry frozen at EOD signal close.",
        ])

    if watch:
        lines.extend(["", "🟡 PINE WATCH — TREND PRESENT, ENTRY NOT READY"])
        for item in watch:
            reason = "wait for commitment"
            if item.get("overextended"):
                reason = "extended; wait for reset"
            elif item.get("chop") or item.get("rotational"):
                reason = "chop/rotation; wait for expansion"
            lines.append(f"• {item['symbol']} | Score {_number(item.get('score')):.0f} | {reason}")

    return "\n".join(lines)
