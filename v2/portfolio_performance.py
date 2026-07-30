"""Auditable V2 portfolio P&L and risk snapshots."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

from .lifecycle import Position, TradeState


@dataclass(frozen=True)
class PortfolioSnapshot:
    portfolio_date: str
    capital_base: float
    committed_capital: float
    market_value: float
    realised_pnl: float
    unrealised_pnl: float
    total_pnl: float
    portfolio_return_pct: float
    initial_risk: float
    open_risk_to_stops: float
    open_positions: int
    pending_setups: int

    def to_dict(self) -> dict:
        return asdict(self)


def build_portfolio_snapshot(
    positions: Iterable[Position], portfolio_date: str, capital_base: float,
) -> PortfolioSnapshot:
    rows = list(positions)
    live_states = {TradeState.OPEN, TradeState.PARTIAL, TradeState.TRAILING}
    committed_states = live_states | {TradeState.WATCH, TradeState.READY}
    live = [position for position in rows if position.state in live_states]
    committed = [position for position in rows if position.state in committed_states]
    realised = sum(position.realised_pnl for position in rows)
    unrealised = sum(
        position.remaining_quantity * ((position.last_price or position.entry) - position.entry)
        for position in live
    )
    committed_capital = sum(position.quantity * position.entry for position in committed)
    market_value = sum(position.remaining_quantity * (position.last_price or position.entry) for position in live)
    initial_risk = sum(position.quantity * (position.entry - position.initial_stop) for position in committed)
    open_risk = sum(
        position.remaining_quantity * max(position.entry - position.stop, 0.0) for position in live
    )
    total = realised + unrealised
    return PortfolioSnapshot(
        portfolio_date=portfolio_date, capital_base=round(capital_base, 2),
        committed_capital=round(committed_capital, 2), market_value=round(market_value, 2),
        realised_pnl=round(realised, 2), unrealised_pnl=round(unrealised, 2), total_pnl=round(total, 2),
        portfolio_return_pct=round(total / capital_base * 100, 4) if capital_base else 0.0,
        initial_risk=round(initial_risk, 2), open_risk_to_stops=round(open_risk, 2),
        open_positions=len(live),
        pending_setups=sum(p.state in {TradeState.WATCH, TradeState.READY} for p in committed),
    )
