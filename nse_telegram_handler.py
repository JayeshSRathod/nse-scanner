"""
nse_telegram_handler.py — Telegram Bot Handler
================================================
Parse mode : HTML

History tracking (Phase 1):
  - HISTORY_FILE stores last 30 days of top 25 symbols
  - save_history()   → appends today's symbols
  - load_history()   → loads all history
  - get_new_stocks() → stocks NEW today vs yesterday
  - get_exit_stocks()→ stocks that LEFT today vs yesterday
  - get_strong_stocks() → stocks in list 5+ consecutive days
"""

import os
import json
import argparse
from datetime import date, datetime

# ── Absolute paths ────────────────────────────────────────────
_HERE        = os.path.dirname(os.path.abspath(__file__))
RESULTS_FILE = os.path.join(_HERE, "telegram_last_scan.json")
HISTORY_FILE = os.path.join(_HERE, "scan_history.json")
PARSE_MODE   = "HTML"

# How many days of history to keep
HISTORY_DAYS = 30

try:
    import config
except ImportError:
    print("WARNING: config.py not found.")


# ── HTML helpers ──────────────────────────────────────────────

def _h(v) -> str:
    return str(v).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

def _b(v)    -> str: return f"<b>{_h(v)}</b>"
def _i(v)    -> str: return f"<i>{_h(v)}</i>"
def _code(v) -> str: return f"<code>{_h(v)}</code>"

def _fmt_price(p: float) -> str:
    return f"{int(round(p)):,}"

def _fmt_return(pct: float) -> str:
    sign = '+' if pct >= 0 else ''
    return f"{sign}{pct:.1f}%"


# ══════════════════════════════════════════════════════════════
# SCAN RESULTS — today's data
# ══════════════════════════════════════════════════════════════

def save_scan_results(results_df, scan_date: date):
    """Save scanned results to JSON. Sorted descending by 3M return."""
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

    # Sort descending by 3M return
    stocks_list.sort(key=lambda x: x['return_3m_pct'], reverse=True)
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

    # ── Auto-save to history ──────────────────────────────────
    save_history(stocks_list, scan_date)


def load_scan_results():
    """Load today's scan results."""
    if not os.path.exists(RESULTS_FILE):
        print(f"[WARN] Results file not found: {RESULTS_FILE}")
        return None
    with open(RESULTS_FILE, 'r') as f:
        return json.load(f)


# ══════════════════════════════════════════════════════════════
# SCAN HISTORY — 30 days rolling
# ══════════════════════════════════════════════════════════════

def save_history(stocks_list: list, scan_date: date):
    """
    Append today's scan to history file.
    Keeps last HISTORY_DAYS days only.
    Only stores symbol + score + return for compactness.
    """
    today_str = str(scan_date)

    # Load existing history
    history = load_history()

    # Remove today if already exists (re-run scenario)
    history = [h for h in history if h['date'] != today_str]

    # Add today
    history.append({
        'date':    today_str,
        'symbols': [s['symbol'] for s in stocks_list],
        'stocks':  [
            {
                'symbol':        s['symbol'],
                'score':         s['score'],
                'return_3m_pct': s['return_3m_pct'],
                'return_1m_pct': s['return_1m_pct'],
                'close':         s['close'],
                'sl':            s['sl'],
                'target1':       s['target1'],
                'target2':       s['target2'],
            }
            for s in stocks_list
        ]
    })

    # Sort by date descending — latest first
    history.sort(key=lambda x: x['date'], reverse=True)

    # Keep only last HISTORY_DAYS
    history = history[:HISTORY_DAYS]

    data = {
        'last_updated': today_str,
        'days_stored':  len(history),
        'history':      history,
    }

    with open(HISTORY_FILE, 'w') as f:
        json.dump(data, f, indent=2)

    print(f"✅ History saved: {HISTORY_FILE}  ({len(history)} days)")


def load_history() -> list:
    """Load scan history. Returns list of daily entries, latest first."""
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, 'r') as f:
            data = json.load(f)
        return data.get('history', [])
    except Exception as e:
        print(f"[WARN] Could not load history: {e}")
        return []


# ══════════════════════════════════════════════════════════════
# HISTORY ANALYSIS — comparisons
# ══════════════════════════════════════════════════════════════

def get_new_stocks(history: list) -> list:
    """
    Stocks that are NEW today — in today's list but NOT in yesterday's.
    Returns list of stock dicts from today's scan.
    """
    if len(history) < 2:
        return []

    today_symbols     = set(history[0]['symbols'])
    yesterday_symbols = set(history[1]['symbols'])
    new_symbols       = today_symbols - yesterday_symbols

    # Return full stock data for new stocks
    return [s for s in history[0]['stocks'] if s['symbol'] in new_symbols]


def get_exit_stocks(history: list) -> list:
    """
    Stocks that EXITED today — in yesterday's list but NOT in today's.
    Returns list of stock dicts from yesterday's scan.
    """
    if len(history) < 2:
        return []

    today_symbols     = set(history[0]['symbols'])
    yesterday_symbols = set(history[1]['symbols'])
    exit_symbols      = yesterday_symbols - today_symbols

    # Return full stock data from yesterday
    return [s for s in history[1]['stocks'] if s['symbol'] in exit_symbols]


def get_strong_stocks(history: list, min_days: int = 5) -> list:
    """
    Stocks consistently in top 25 for min_days or more consecutive days.
    Returns list of dicts with stock data + consecutive_days count.
    """
    if not history:
        return []

    today_symbols = set(history[0]['symbols'])
    strong        = []

    for symbol in today_symbols:
        # Count consecutive days this symbol appeared
        consecutive = 0
        for day_entry in history:
            if symbol in day_entry['symbols']:
                consecutive += 1
            else:
                break   # consecutive streak broken

        if consecutive >= min_days:
            # Get today's data for this stock
            stock_data = next(
                (s for s in history[0]['stocks'] if s['symbol'] == symbol),
                None
            )
            if stock_data:
                strong.append({
                    **stock_data,
                    'consecutive_days': consecutive,
                    'days_available':   len(history),
                })

    # Sort by consecutive days descending
    strong.sort(key=lambda x: x['consecutive_days'], reverse=True)
    return strong


def get_stock_streak(symbol: str, history: list) -> int:
    """How many consecutive days a symbol has been in the list."""
    count = 0
    for day_entry in history:
        if symbol in day_entry['symbols']:
            count += 1
        else:
            break
    return count


# ══════════════════════════════════════════════════════════════
# SORTING
# ══════════════════════════════════════════════════════════════

def sort_stocks(stocks: list, mode: str = '3m') -> list:
    if mode == 'score':
        return sorted(stocks, key=lambda x: float(x.get('score', 0)), reverse=True)
    elif mode == 'top10':
        return sorted(stocks, key=lambda x: float(x.get('return_3m_pct', 0)), reverse=True)[:10]
    else:
        return sorted(stocks, key=lambda x: float(x.get('return_3m_pct', 0)), reverse=True)


# ══════════════════════════════════════════════════════════════
# NEWS
# ══════════════════════════════════════════════════════════════

def fetch_news_for_symbol(symbol: str, max_items: int = 3) -> list:
    try:
        import requests
        from xml.etree import ElementTree as ET
        query = f"{symbol} NSE stock India"
        url   = f"https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
        r     = requests.get(url, timeout=6, headers={'User-Agent': 'Mozilla/5.0'})
        if r.status_code != 200:
            return []
        root  = ET.fromstring(r.content)
        items = root.findall('.//item')
        news  = []
        for item in items[:max_items]:
            title   = item.findtext('title', '').split(' - ')[0].strip()
            pub     = item.findtext('pubDate', '')
            source  = item.findtext('source', 'News')
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
    if not news:
        return "   <i>No recent news</i>\n"
    out = ""
    for n in news:
        title_safe = _h(n['title'][:80] + ('…' if len(n['title']) > 80 else ''))
        out += f"   📰 {title_safe} <i>({_h(n['date'])})</i>\n"
    return out


# ══════════════════════════════════════════════════════════════
# MESSAGE FORMATTING
# ══════════════════════════════════════════════════════════════

def format_stock_list(stocks: list, start_idx: int = 0, count: int = 5,
                      scan_date: str = None, include_news: bool = False) -> str:
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
        t2    = float(stock.get('target2', round(entry + 2*(entry - sl), 2)))
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
    return msg


def format_new_stocks(new_stocks: list, scan_date: str = None) -> str:
    """Format NEW entries message."""
    try:
        dt       = datetime.strptime(scan_date or '', '%Y-%m-%d')
        date_str = dt.strftime('%d-%b-%Y')
    except Exception:
        date_str = scan_date or 'Today'

    if not new_stocks:
        return (
            f"🆕 {_b('NEW ENTRIES — ' + date_str)}\n\n"
            f"{_i('No new stocks entered the watchlist today')}\n\n"
            f"All 25 stocks carried over from yesterday."
        )

    msg  = f"🆕 {_b('NEW ENTRIES — ' + date_str)}\n"
    msg += f"{_i('Stocks that entered top 25 today')}\n"
    msg += "─" * 34 + "\n\n"

    for i, stock in enumerate(new_stocks, 1):
        entry = float(stock.get('close',   0))
        sl    = float(stock.get('sl',      round(entry * 0.93, 2)))
        t1    = float(stock.get('target1', round(entry + (entry - sl), 2)))
        t2    = float(stock.get('target2', round(entry + 2*(entry - sl), 2)))
        r3m   = float(stock.get('return_3m_pct', 0))
        score = int(round(float(stock.get('score', 0))))

        msg += (
            f"{_b(str(i) + '.')}  {_code(stock['symbol'])}  {score}/10\n"
            f"   Entry {_fmt_price(entry)} | SL {_fmt_price(sl)} | "
            f"T1 {_fmt_price(t1)} | T2 {_fmt_price(t2)} | "
            f"3M {_fmt_return(r3m)}\n\n"
        )

    msg += f"💡 {len(new_stocks)} new stock(s) entered today"
    return msg


def format_exit_stocks(exit_stocks: list, scan_date: str = None) -> str:
    """Format EXIT signals message."""
    try:
        dt       = datetime.strptime(scan_date or '', '%Y-%m-%d')
        date_str = dt.strftime('%d-%b-%Y')
    except Exception:
        date_str = scan_date or 'Today'

    if not exit_stocks:
        return (
            f"⚠️ {_b('EXIT SIGNALS — ' + date_str)}\n\n"
            f"{_i('No stocks exited the watchlist today')}\n\n"
            f"All yesterday's stocks still in top 25."
        )

    msg  = f"⚠️ {_b('EXIT SIGNALS — ' + date_str)}\n"
    msg += f"{_i('Stocks that left top 25 today — consider booking profits')}\n"
    msg += "─" * 34 + "\n\n"

    for i, stock in enumerate(exit_stocks, 1):
        r3m   = float(stock.get('return_3m_pct', 0))
        score = int(round(float(stock.get('score', 0))))
        entry = float(stock.get('close', 0))

        msg += (
            f"{_b(str(i) + '.')}  {_code(stock['symbol'])}  {score}/10\n"
            f"   Last price {_fmt_price(entry)} | "
            f"3M {_fmt_return(r3m)}\n\n"
        )

    msg += f"⚠️ {len(exit_stocks)} stock(s) exited today"
    return msg


def format_strong_stocks(strong_stocks: list, scan_date: str = None) -> str:
    """Format STRONG / consistent stocks message."""
    try:
        dt       = datetime.strptime(scan_date or '', '%Y-%m-%d')
        date_str = dt.strftime('%d-%b-%Y')
    except Exception:
        date_str = scan_date or 'Today'

    if not strong_stocks:
        return (
            f"🔥 {_b('STRONG SIGNALS — ' + date_str)}\n\n"
            f"{_i('No stocks in top 25 for 5+ consecutive days yet')}\n\n"
            f"Check back after more trading days."
        )

    msg  = f"🔥 {_b('STRONG SIGNALS — ' + date_str)}\n"
    msg += f"{_i('Stocks in top 25 for 5+ consecutive days')}\n"
    msg += "─" * 34 + "\n\n"

    for i, stock in enumerate(strong_stocks, 1):
        entry = float(stock.get('close',   0))
        sl    = float(stock.get('sl',      round(entry * 0.93, 2)))
        t1    = float(stock.get('target1', round(entry + (entry - sl), 2)))
        t2    = float(stock.get('target2', round(entry + 2*(entry - sl), 2)))
        r3m   = float(stock.get('return_3m_pct', 0))
        score = int(round(float(stock.get('score', 0))))
        days  = stock.get('consecutive_days', 0)

        msg += (
            f"{_b(str(i) + '.')}  {_code(stock['symbol'])}  "
            f"{score}/10  🔥{days}d\n"
            f"   Entry {_fmt_price(entry)} | SL {_fmt_price(sl)} | "
            f"T1 {_fmt_price(t1)} | T2 {_fmt_price(t2)} | "
            f"3M {_fmt_return(r3m)}\n\n"
        )

    msg += f"🔥 {len(strong_stocks)} stock(s) showing sustained momentum"
    return msg


def format_help() -> str:
    return (
        f"🤖 {_b('NSE Momentum Scanner Bot')}\n\n"
        f"{_b('Commands:')}\n"
        "• /start — Top stocks sorted by 3M return\n"
        "• /next — Next 5 stocks\n"
        "• /prev — Previous 5 stocks\n"
        "• /page N — Jump to page N\n"
        "• /news — Current page with news\n"
        "• /list — Summary of all stocks\n"
        "• /help — Show this message\n\n"
        f"{_b('View buttons:')}\n"
        "• 📊 Today — Today's watchlist\n"
        "• 🆕 New — Stocks that entered today\n"
        "• ⚠️ Exit — Stocks that left today\n"
        "• 🔥 Strong — 5+ consecutive days\n\n"
        f"{_b('Sort buttons:')}\n"
        "• 📈 3M Return — Sort by 3-month performance\n"
        "• ⭐ Score — Sort by scanner score\n"
        "• 🔝 Top 10 — Show top 10 only\n\n"
        "💡 Tap buttons below to navigate!"
    )


# ── CLI demo ──────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test",    action="store_true")
    parser.add_argument("--history", action="store_true",
                        help="Show history analysis")
    parser.add_argument("--page",    type=int, default=1)
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

    if args.history:
        history = load_history()
        print(f"History entries: {len(history)}")
        new     = get_new_stocks(history)
        exits   = get_exit_stocks(history)
        strong  = get_strong_stocks(history)
        print(f"New today   : {[s['symbol'] for s in new]}")
        print(f"Exit today  : {[s['symbol'] for s in exits]}")
        print(f"Strong (5d+): {[s['symbol'] for s in strong]}")


if __name__ == "__main__":
    main()
