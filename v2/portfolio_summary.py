"""On-demand V2 portfolio P&L and risk report rendering."""
from __future__ import annotations

from .portfolio_performance import PortfolioSnapshot


def _money(value: float) -> str:
    sign = "+" if value > 0 else ""
    return f"{sign}₹{value:,.2f}"


def render_portfolio_summary(snapshot: PortfolioSnapshot) -> str:
    """Return a concise report suitable for the future /portfolio command."""
    return "\n".join([
        "💰 KJ V2 PORTFOLIO SUMMARY",
        f"Date: {snapshot.portfolio_date}",
        "━━━━━━━━━━━━━━━━━━",
        f"Capital Base: ₹{snapshot.capital_base:,.2f}",
        f"Committed Capital: ₹{snapshot.committed_capital:,.2f}",
        f"Current Equity: ₹{snapshot.capital_base + snapshot.total_pnl:,.2f}",
        f"Realised P&L: {_money(snapshot.realised_pnl)}",
        f"Unrealised P&L: {_money(snapshot.unrealised_pnl)}",
        f"Total P&L: {_money(snapshot.total_pnl)} ({snapshot.portfolio_return_pct:+.2f}%)",
        "",
        f"Open Positions: {snapshot.open_positions} | Pending Setups: {snapshot.pending_setups}",
        f"Initial Risk Committed: ₹{snapshot.initial_risk:,.2f}",
        f"Remaining Loss Risk to Stops: ₹{snapshot.open_risk_to_stops:,.2f}",
        "",
        "P&L is based on recorded V2 entries, partial exits and closing prices.",
    ])
