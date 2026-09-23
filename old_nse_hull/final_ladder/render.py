"""User-facing selected-profile daily cards and period summaries."""
from html import escape
from urllib.parse import quote

from telegram_dashboard import dashboard_url

def daily_messages(report):
    header=f"<b>Momentum Ladder | Daily PAPER watchlist</b>\nData: {escape(report['as_of_date'])} EOD\nEMA14/21 | Volume1.8x | RSI50-70 | Score65+\n"
    pages=[];page=header
    for r in report['shortlist'][:25]:
        l=r['trade_levels']
        block=(f"\n<b>{escape(r['symbol'])}</b> | Watch for entry\n"
            f"Score: {r['primary_score']:.2f} | Price: INR {r['close']:.2f}\n"
            f"Planned entry: INR {l['entry_trigger']:.2f} | Hard stop: INR {l['stop']:.2f}\n"
            f"TP1: INR {l['target_1']:.2f}; then follow structural trailing stop\n"
            "Why: Recent EMA14/21 crossover and qualifying technical score.\n"
            "Next: Wait for entry trigger; setup expires after 5 sessions.\n")
        block += f'<a href="https://www.tradingview.com/chart/?symbol=NSE%3A{quote(r["symbol"], safe="")}">📈 Open {escape(r["symbol"])} chart</a>\n'
        if len(page)+len(block)>3400:pages.append(page);page=header
        page+=block
    if not report['shortlist']:page+='\nNo stocks meet the selected entry rules today. Do not force an entry.\n'
    page+=f'\n<a href="{escape(dashboard_url("ladder"), quote=True)}">📊 Open Momentum Ladder dashboard</a>\nWatchlist setups are not filled positions. PAPER tracking only.'
    pages.append(page)
    return pages

def period_message(report,period):
    s=report['uniform_portfolio']
    return (f"<b>Momentum Ladder | {escape(period.title())} PAPER review</b>\n"
        f"Data: {escape(report['as_of_date'])} EOD\n"
        f"Selected profile: {escape(report['strategy_profile'])}\n"
        f"Open positions: {s['open_positions']} | Pending: {s['pending_setups']}\n"
        f"Cumulative net P&amp;L: INR {s['total_pnl']:,.2f}\n"
        "These are cumulative cohort figures, not period-only returns.\n"
        "Follow stored protective stops; TP2 is not a forced exit.")
