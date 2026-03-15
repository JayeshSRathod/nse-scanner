"""
nse_telegram_handler.py — Telegram Bot Handler
================================================
Parse mode : HTML  (avoids MarkdownV2 escape failures with live market data)

Key fixes:
  - RESULTS_FILE now uses absolute path (same folder as this script)
    so it works regardless of which directory Python is launched from.
  - Stocks always sorted descending by 3M return.
  - News fetching per stock via NSE / fallback RSS.
"""

import os
import json
import argparse
from datetime import date, datetime

OWNER_NAME = "Jayesh Rathod"

# ── Absolute path for JSON so it works from any working directory ─────────────
_HERE        = os.path.dirname(os.path.abspath(__file__))
RESULTS_FILE = os.path.join(_HERE, "telegram_last_scan.json")
PARSE_MODE   = "HTML"

try:
    import config
except ImportError:
    print("WARNING: config.py not found.")


# ── HTML helpers ──────────────────────────────────────────────────────────────

def _h(v) -> str:
    """Escape value for Telegram HTML: & < >"""
    return str(v).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

def _b(v)    -> str: return f"<b>{_h(v)}</b>"
def _i(v)    -> str: return f"<i>{_h(v)}</i>"
def _code(v) -> str: return f"<code>{_h(v)}</code>"


def _fmt_price(p: float) -> str:
    return f"{int(round(p)):,}"

def _fmt_return(pct: float) -> str:
    sign = '+' if pct >= 0 else ''
    return f"{sign}{pct:.1f}%"


# ── Persistence ───────────────────────────────────────────────────────────────

def save_scan_results(results_df, scan_date: date):
    """
    Save scanned results to JSON for Telegram pagination.
    Stocks are saved sorted descending by 3M return.
    Derives SL / Target1 / Target2 from columns if present, else auto-calculates.
    """
    if results_df.empty:
        print("No results to save")
        return

    stocks_list = []
    for idx, row in results_df.iterrows():
        entry = round(float(row['close']),   2) if 'close'   in row else 0.0
        sl    = round(float(row['sl']),      2) if 'sl'      in row else round(entry * 0.93, 2)
        t1    = round(float(row['target1']), 2) if 'target1' in row else round(entry + (entry - sl), 2)
        t2    = round(float(row['target2']), 2) if 'target2' in row else round(entry + 2*(entry - sl), 2)

        stocks_list.append({
            'rank':          idx + 1,
            'symbol':        str(row['symbol']),
            'score':         round(float(row['score']),         2) if 'score'         in row else 0,
            'return_1m_pct': round(float(row['return_1m_pct']), 1) if 'return_1m_pct' in row else 0,
            'return_2m_pct': round(float(row['return_2m_pct']), 1) if 'return_2m_pct' in row else 0,
            'return_3m_pct': round(float(row['return_3m_pct']), 1) if 'return_3m_pct' in row else 0,
            'close':         entry,
            'volume':        int(row['volume'])                     if 'volume'        in row else 0,
            'delivery_pct':  round(float(row['delivery_pct']),  1) if 'delivery_pct'  in row else 0,
            'sl':            sl,
            'target1':       t1,
            'target2':       t2,
        })

    # Always sort descending by 3M return before saving
    stocks_list.sort(key=lambda x: x['return_3m_pct'], reverse=True)
    # Re-assign ranks after sort
    for i, s in enumerate(stocks_list):
        s['rank'] = i + 1

    data = {
        'scan_date':    str(scan_date),
        'total_stocks': len(stocks_list),
        'page_size':    5,
        'stocks':       stocks_list,
    }

    with open(RESULTS_FILE, 'w') as f:
        json.dump(data, f, indent=2)

    print(f"✅ Scan results saved: {RESULTS_FILE}  ({len(stocks_list)} stocks)")


def load_scan_results():
    """Load previously saved scan results. Returns None if file missing."""
    if not os.path.exists(RESULTS_FILE):
        print(f"[WARN] Results file not found: {RESULTS_FILE}")
        return None
    with open(RESULTS_FILE, 'r') as f:
        return json.load(f)


# ── Sorting ───────────────────────────────────────────────────────────────────

def sort_stocks(stocks: list, mode: str = '3m') -> list:
    """
    '3m'    → descending 3-month return  (default)
    'score' → descending scanner score
    'top10' → top 10 by 3-month return
    """
    if mode == 'score':
        return sorted(stocks, key=lambda x: float(x.get('score', 0)), reverse=True)
    elif mode == 'top10':
        return sorted(stocks, key=lambda x: float(x.get('return_3m_pct', 0)), reverse=True)[:10]
    else:
        return sorted(stocks, key=lambda x: float(x.get('return_3m_pct', 0)), reverse=True)


# ── News fetching ─────────────────────────────────────────────────────────────

def fetch_news_for_symbol(symbol: str, max_items: int = 3) -> list:
    """
    Fetch recent news headlines for an NSE symbol.
    Returns list of dicts: [{'title': str, 'date': str, 'source': str}]
    Falls back to empty list on any error.
    """
    try:
        import requests
        from xml.etree import ElementTree as ET

        # Google News RSS — reliable, no auth needed
        query = f"{symbol} NSE stock India"
        url   = f"https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
        r     = requests.get(url, timeout=6,
                             headers={'User-Agent': 'Mozilla/5.0'})
        if r.status_code != 200:
            return []

        root  = ET.fromstring(r.content)
        items = root.findall('.//item')
        news  = []
        for item in items[:max_items]:
            title   = item.findtext('title', '').split(' - ')[0].strip()
            pub     = item.findtext('pubDate', '')
            source  = item.findtext('source', 'News')
            # Parse pub date to short format
            try:
                dt      = datetime.strptime(pub[:16], '%a, %d %b %Y')
                pub_fmt = dt.strftime('%d-%b')
            except Exception:
                pub_fmt = pub[:10] if pub else ''
            news.append({'title': title, 'date': pub_fmt, 'source': source})

        return news

    except Exception as e:
        print(f"[NEWS] fetch failed for {symbol}: {e}")
        return []


def format_news_block(news: list) -> str:
    """Format news list as HTML block for Telegram."""
    if not news:
        return "   <i>No recent news</i>\n"
    out = ""
    for n in news:
        title_safe = _h(n['title'][:80] + ('…' if len(n['title']) > 80 else ''))
        out += f"   📰 {title_safe} <i>({_h(n['date'])})</i>\n"
    return out


# ── Message formatting (HTML) ─────────────────────────────────────────────────

def format_stock_list(stocks: list, start_idx: int = 0, count: int = 5,
                      scan_date: str = None, include_news: bool = False) -> str:
    """
    Format a page of stocks as WATCHLIST SIGNALS (Telegram HTML).

    stocks       : already-sorted list (pass result of sort_stocks here)
    start_idx    : 0-based index of first stock on this page
    count        : stocks per page (default 5)
    scan_date    : ISO date string e.g. '2026-03-12'
    include_news : if True, fetches and appends news per stock (slower)
    """
    end_idx   = min(start_idx + count, len(stocks))
    selected  = stocks[start_idx:end_idx]
    total     = len(stocks)
    cur_page  = (start_idx // count) + 1
    tot_pages = max(1, (total + count - 1) // count)

    try:
        dt       = datetime.strptime(scan_date or '', '%Y-%m-%d')
        date_str = dt.strftime('%d-%b-%Y')
    except Exception:
        date_str = scan_date or 'Today'

    msg  = f"📊 {_b('WATCHLIST SIGNALS — ' + date_str)}\n"
    msg += f"{_i('Sorted by 3M Return | Monitor for entry')}\n"
    msg += "─" * 34 + "\n\n"

    for i, stock in enumerate(selected, start=start_idx + 1):
        entry = float(stock.get('close',   0))
        sl    = float(stock.get('sl',      round(entry * 0.93, 2)))
        t1    = float(stock.get('target1', round(entry + (entry - sl), 2)))
        t2    = float(stock.get('target2', round(entry + 2 * (entry - sl), 2)))
        r3m   = float(stock.get('return_3m_pct', 0))
        score = int(round(float(stock.get('score', 0))))
        sym   = stock['symbol']

        msg += (
            f"{_b(str(i) + '.')}  {_code(sym)}  {score}/10\n"
            f"   Entry {_fmt_price(entry)} | SL {_fmt_price(sl)} | "
            f"T1 {_fmt_price(t1)} | T2 {_fmt_price(t2)} | "
            f"3M {_fmt_return(r3m)}\n"
        )

        if include_news:
            news = fetch_news_for_symbol(sym)
            msg += format_news_block(news)

        msg += "\n"

    msg += f"📄 Page {cur_page}/{tot_pages}"
    
    msg += f"\nDeveloped by: {OWNER_NAME}"
    return msg


def format_help() -> str:
    return (
        f"🤖 {_b('NSE Momentum Scanner Bot')}\n\n"
        f"{_b('Commands:')}\n"
        "• /start — Top stocks sorted by 3M return\n"
        "• /next — Next 5 stocks\n"
        "• /prev — Previous 5 stocks\n"
        "• /page N — Jump to page N  (e.g. /page 2)\n"
        "• /news — Same page with news headlines\n"
        "• /list — Summary of all stocks\n"
        "• /help — Show this message\n\n"
        f"{_b('Sort buttons:')}\n"
        "• 📈 3M Return — Sort by 3-month performance\n"
        "• ⭐ Score — Sort by scanner score\n"
        "• 🔝 Top 10 — Show top 10 by 3M return only\n"
        "• 📰 With News — Current page + news headlines\n\n"
        "💡 Tap the inline buttons below each message to navigate!"
	    "Developed by: {OWNER_NAME}"
    )


# ── CLI demo ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Telegram Bot Handler — local test")
    parser.add_argument("--test",  action="store_true", help="Generate test data")
    parser.add_argument("--page",  type=int, default=1, help="Page to display (1-based)")
    parser.add_argument("--news",  action="store_true", help="Include news in output")
    args = parser.parse_args()

    if args.test:
        import pandas as pd
        test_data = {
            'symbol':        [f'STOCK{i:02d}' for i in range(1, 26)],
            'score':         [7 - i * 0.1   for i in range(25)],
            'return_1m_pct': [15 - i * 0.3  for i in range(25)],
            'return_2m_pct': [25 - i * 0.4  for i in range(25)],
            'return_3m_pct': [133 - i * 5   for i in range(25)],
            'close':         [1000 + i * 50 for i in range(25)],
            'volume':        [1000000 + i * 100000 for i in range(25)],
            'delivery_pct':  [40 + i * 1.5  for i in range(25)],
        }
        df = pd.DataFrame(test_data)
        save_scan_results(df, date.today())
        print("✅ Test data saved\n")

        results = load_scan_results()
        if results:
            stocks    = sort_stocks(results['stocks'], '3m')
            page_size = results['page_size']
            start_idx = (args.page - 1) * page_size
            if start_idx >= len(stocks):
                print(f"❌ Page {args.page} not found")
            else:
                print(format_stock_list(stocks, start_idx, page_size,
                                        results['scan_date'], include_news=args.news))


if __name__ == "__main__":
    main()