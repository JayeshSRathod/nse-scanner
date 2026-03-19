"""
nse_telegram_handler.py — Telegram Bot Handler (CLOUD READY)
============================================================
Now uses GitHub JSON as primary data source.
Falls back to local JSON if needed.
"""

import os
import json
import argparse
from datetime import date, datetime

from github_fetch import fetch_json  # ✅ NEW

OWNER_NAME = "Jayesh Rathod"

# ── Local fallback path ─────────────────────────────────────
_HERE        = os.path.dirname(os.path.abspath(__file__))
RESULTS_FILE = os.path.join(_HERE, "telegram_last_scan.json")
PARSE_MODE   = "HTML"


# ── HTML helpers ─────────────────────────────────────────────

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


# ── DATA LOADING (FIXED) ─────────────────────────────────────

def load_scan_results():
    """
    Load scan results:
    1. Try GitHub (primary)
    2. Fallback to local file
    """
    data = fetch_json()
    if data:
        return data

    print("[WARN] GitHub fetch failed, using local fallback")

    if os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE, 'r') as f:
            return json.load(f)

    print("[ERROR] No data available")
    return None


# ── SAVE RESULTS (UNCHANGED - USED BY PIPELINE) ───────────────

def save_scan_results(results_df, scan_date: date):
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
            'rank': idx + 1,
            'symbol': str(row['symbol']),
            'score': round(float(row.get('score', 0)), 2),
            'return_1m_pct': round(float(row.get('return_1m_pct', 0)), 1),
            'return_2m_pct': round(float(row.get('return_2m_pct', 0)), 1),
            'return_3m_pct': round(float(row.get('return_3m_pct', 0)), 1),
            'close': entry,
            'volume': int(row.get('volume', 0)),
            'delivery_pct': round(float(row.get('delivery_pct', 0)), 1),
            'sl': sl,
            'target1': t1,
            'target2': t2,
        })

    stocks_list.sort(key=lambda x: x['return_3m_pct'], reverse=True)

    for i, s in enumerate(stocks_list):
        s['rank'] = i + 1

    data = {
        'scan_date': str(scan_date),
        'total_stocks': len(stocks_list),
        'page_size': 5,
        'stocks': stocks_list,
    }

    with open(RESULTS_FILE, 'w') as f:
        json.dump(data, f, indent=2)

    print(f"✅ Scan results saved: {RESULTS_FILE}")


# ── SORTING ─────────────────────────────────────────────────

def sort_stocks(stocks, mode='3m'):
    if mode == 'score':
        return sorted(stocks, key=lambda x: x.get('score', 0), reverse=True)
    elif mode == 'top10':
        return sorted(stocks, key=lambda x: x.get('return_3m_pct', 0), reverse=True)[:10]
    return sorted(stocks, key=lambda x: x.get('return_3m_pct', 0), reverse=True)


# ── MESSAGE FORMATTING ──────────────────────────────────────

def format_stock_list(stocks, start_idx=0, count=5, scan_date=None):
    end_idx = min(start_idx + count, len(stocks))
    selected = stocks[start_idx:end_idx]

    total = len(stocks)
    cur_page = (start_idx // count) + 1
    tot_pages = max(1, (total + count - 1) // count)

    try:
        dt = datetime.strptime(scan_date or '', '%Y-%m-%d')
        date_str = dt.strftime('%d-%b-%Y')
    except:
        date_str = scan_date or 'Today'

    msg = f"📊 {_b('WATCHLIST SIGNALS — ' + date_str)}\n"
    msg += f"{_i('Sorted by 3M Return | Monitor for entry')}\n"
    msg += "─" * 34 + "\n\n"

    for i, stock in enumerate(selected, start=start_idx + 1):
        entry = float(stock.get('close', 0))
        sl = float(stock.get('sl', entry * 0.93))
        t1 = float(stock.get('target1', entry + (entry - sl)))
        t2 = float(stock.get('target2', entry + 2 * (entry - sl)))

        msg += (
            f"{_b(str(i) + '.')} {_code(stock['symbol'])} {int(stock.get('score', 0))}/10\n"
            f"   Entry {_fmt_price(entry)} | SL {_fmt_price(sl)} | "
            f"T1 {_fmt_price(t1)} | T2 {_fmt_price(t2)} | "
            f"3M {_fmt_return(stock.get('return_3m_pct', 0))}\n\n"
        )

    msg += f"📄 Page {cur_page}/{tot_pages}"
    msg += f"\nDeveloped by: {OWNER_NAME}"

    return msg


# ── CLI TEST ───────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--page", type=int, default=1)
    args = parser.parse_args()

    results = load_scan_results()

    if not results:
        print("❌ No data available")
        return

    stocks = sort_stocks(results['stocks'])
    page_size = results['page_size']
    start_idx = (args.page - 1) * page_size

    print(format_stock_list(stocks, start_idx, page_size, results['scan_date']))


if __name__ == "__main__":
    main()