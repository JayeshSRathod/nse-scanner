"""Render the persistent-position update (Message 2) for NSE Scanner V2."""
from __future__ import annotations

from collections.abc import Iterable

from .lifecycle import Position, TradeState


def _fmt(value: float | None) -> str:
    return "-" if value is None else f"{value:.2f}"


def render_portfolio_message(positions: Iterable[Position], trade_date: str) -> str:
    rows = sorted(positions, key=lambda p: (p.horizon, p.symbol, p.trade_id))
    lines = [f"V2 POSITION UPDATE | {trade_date}"]
    if not rows:
        return "\n".join(lines + ["No active or recently updated positions."])

    current_horizon: str | None = None
    for position in rows:
        if position.horizon != current_horizon:
            current_horizon = position.horizon
            lines.extend(["", f"[{current_horizon}]"])
        quantity_text = f"{position.remaining_quantity:g}/{position.quantity:g}"
        lines.append(
            f"{position.symbol} | {position.state.value} | Last {_fmt(position.last_price)} | "
            f"SL {_fmt(position.stop)} | T1 {_fmt(position.target1)} | "
            f"T2 {_fmt(position.target2)} | Qty {quantity_text}"
        )
        lines.append(f"Reason: {position.reason} | Trade ID: {position.trade_id[:8]}")
    return "\n".join(lines)


def positions_for_message(before: Iterable[Position], after: Iterable[Position]) -> list[Position]:
    """Include every active position plus positions closed/cancelled on this run."""
    previous = {p.trade_id: p for p in before}
    selected: list[Position] = []
    for position in after:
        changed = previous.get(position.trade_id) != position
        if position.state not in {TradeState.CLOSED, TradeState.CANCELLED} or changed:
            selected.append(position)
    return selected
