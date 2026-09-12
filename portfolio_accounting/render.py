"""Identical portfolio vocabulary with bounded Telegram-compatible pages."""
from __future__ import annotations

from html import escape


def render_messages(snapshot: dict, limit: int = 3400) -> list[str]:
    def money(value):
        return f"₹{value:,.2f}"
    s = snapshot
    header = f"<b>{escape(s['scanner'])} — PAPER PORTFOLIO</b>\nData: {escape(s['as_of_date'])} EOD\n"
    blocks = ["\n".join([
        f"Starting capital: {money(s['starting_capital'])}",
        f"Available cash: {money(s['available_cash'])}",
        f"Invested capital: {money(s['invested_capital'])}",
        f"Pending reservations: {money(s['reserved_capital'])} (not invested)",
        f"Holdings value: {money(s['market_value'])}",
        f"Booked P&L: {money(s['realised_pnl'])}",
        f"Open P&L: {money(s['unrealised_pnl'])}",
        f"Recorded fees: {money(s['fees'])}",
        f"Total P&L: {money(s['total_pnl'])} ({s['return_pct']:+.2f}%)",
        f"Total equity: {money(s['equity'])}",
        f"Open: {s['open_positions']} | Closed: {s['closed_positions']} | Pending: {s['pending_setups']}",
        escape(s['cost_basis']), f"Evidence: {escape(s['provenance'])}",
    ])]
    if not s["positions"]:
        blocks.append("No recorded simulated fills in this accounting ledger.")
    for p in s["positions"]:
        value = lambda key: money(p[key]) if p.get(key) is not None else "Not recorded"
        action = "Review holding and valuation" if p['status'] == 'REVIEW' else "Position closed" if not p['remaining_quantity'] else "Follow the scanner's current stop and exit rules"
        blocks.append("\n".join([
            f"<b>{escape(p['symbol'])}</b> — {escape(p['status'])}",
            f"Entry: {value('entry')} | Date: {escape(str(p.get('entry_date') or 'Not recorded'))}",
            f"Quantity: {p['quantity']:g} | Remaining: {p['remaining_quantity']:g}",
            f"Current price: {value('last_price')} | Mark: {escape(str(p.get('mark_date') or 'Not recorded'))}",
            f"Initial SL: {value('initial_stop')} | Current SL: {value('stop')}",
            f"T1: {value('target1')} | T2: {value('target2')}",
            f"Booked: {value('realised_pnl')} | Open: {value('unrealised_pnl')}",
            f"Total: {value('total_pnl')} ({p['return_pct']:+.2f}%)",
            f"Next: {action}",
        ]))
    if s['pending_setups']:
        blocks.append("Pending entries are tracked separately and contribute no P&L.")
    blocks.extend(escape(w) for w in s['warnings'])
    pages, page = [], header
    for block in blocks:
        if len(header + block) > limit:
            raise ValueError("Portfolio block exceeds message limit")
        if len(page + '\n\n' + block) > limit:
            pages.append(page)
            page = header
        page += '\n\n' + block
    pages.append(page)
    return pages
