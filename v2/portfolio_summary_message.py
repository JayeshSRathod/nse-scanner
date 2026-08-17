"""Telegram Message 3: consolidated portfolio P&L and risk."""
from __future__ import annotations

from .portfolio_performance import PortfolioSnapshot


def render_portfolio_summary(snapshot: PortfolioSnapshot, previous_total_pnl: float | None = None) -> str:
    daily_change = snapshot.total_pnl - previous_total_pnl if previous_total_pnl is not None else 0.0
    return "\n".join([
        "💰 KJ PORTFOLIO P&L",
        f"Trade Date: {snapshot.portfolio_date}",
        "",
        f"Capital Base: ₹{snapshot.capital_base:,.2f}",
        f"Committed Capital: ₹{snapshot.committed_capital:,.2f}",
        f"Current Market Value: ₹{snapshot.market_value:,.2f}",
        f"Realised P&L: ₹{snapshot.realised_pnl:,.2f}",
        f"Unrealised P&L: ₹{snapshot.unrealised_pnl:,.2f}",
        f"Total P&L: ₹{snapshot.total_pnl:,.2f}",
        f"Daily Change: ₹{daily_change:,.2f}",
        f"Portfolio Return: {snapshot.portfolio_return_pct:+.2f}%",
        "",
        f"Open Positions: {snapshot.open_positions}",
        f"Pending Setups: {snapshot.pending_setups}",
        f"Initial Risk: ₹{snapshot.initial_risk:,.2f}",
        f"Open Risk to Stops: ₹{snapshot.open_risk_to_stops:,.2f}",
    ])
