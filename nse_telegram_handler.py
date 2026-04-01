"""
nse_telegram_handler.py — Telegram Bot Handler (v4 — Probabilities + Frozen Entry)
====================================================================================
Parse mode: HTML

Changes from v3:
  + Probability bars (T1/T2/SL) in stock cards
  + Frozen entry P/L in Strong view
  + Category tags on all stock cards
  + Updated help with new commands (Buckets, Guide)
  + Caution view shows SL risk probability
  + Exit view shows frozen entry P/L and days in list
"""

import os
import json
import argparse
from datetime import date, datetime

_HERE        = os.path.dirname(os.path.abspath(__file__))
RESULTS_FILE = os.path.join(_HERE, "telegram_last_scan.json")
HISTORY_FILE = os.path.join(_HERE, "scan_history.json")
PARSE_MODE   = "HTML"
HISTORY_DAYS = 30

try:
    import config
except ImportError:
    pass

# ── Optional: signal tracker for probabilities ────────────────
_TRACKER_OK = False
try:
    from nse_signal_tracker import (
        get_signal, calculate_probability, get_tracker_summary,
        STATE_ACTIVE, STATE_T1_HIT, STATE_T2_HIT, STATE_WEAKENING, STATE_EXITED,
    )
    _TRACKER_OK = True
except ImportError:
    def get_signal(s): return None
    def calculate_probability(**kw): return {"t1_pct": 0, "t2_pct": 0, "sl_pct": 0}
    def get_tracker_summary(): return {}

CATEGORY_META = {
    "rising":     {"icon": "\U0001F4C8", "label": "Consistently Rising",
                   "desc": "Steady upward momentum over 1-3 months"},
    "uptrend":    {"icon": "\U0001F680", "label": "Clear Uptrend Confirmed",
                   "desc": "Technical breakout confirmed with volume"},
    "peak":       {"icon": "\U0001F51D", "label": "Close to Their Peak",
                   "desc": "Near 52-week highs \u2014 strong demand"},
    "recovering": {"icon": "\U0001F4C9", "label": "Recovering from a Fall",
                   "desc": "Bouncing back \u2014 early recovery signal"},
    "safer":      {"icon": "\U0001F6E1\ufe0f", "label": "Safer Bets with Good Reward",
                   "desc": "Lower risk, consistent returns"},
}

CATEGORY_ORDER = ["uptrend", "rising", "peak", "safer", "recovering"]


# ══════════════════════════════════════════════════════════════
# HTML HELPERS
# ══════════════════════════════════════════════════════════════

def _h(v):
    return str(v).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

def _b(v):    return f"<b>{_h(v)}</b>"
def _i(v):    return f"<i>{_h(v)}</i>"
def _code(v): return f"<code>{_h(v)}</code>"

def _fmt_price(p):
    return f"\u20b9{int(round(float(p))):,}"

def _fmt_return(pct):
    pct = float(pct)
    sign = '+' if pct >= 0 else ''
    return f"{sign}{pct:.1f}%"

def _fmt_pl(entry, current):
    entry   = float(entry)
    current = float(current)
    if entry <= 0:
        return "N/A"
    diff = current - entry
    pct  = diff / entry * 100
    sign = "+" if diff >= 0 else ""
    return f"{sign}{int(round(diff)):,} ({sign}{pct:.1f}%)"

def _date_str(scan_date):
    try:
        return datetime.strptime(scan_date or '', '%Y-%m-%d').strftime('%d-%b-%Y')
    except Exception:
        return scan_date or 'Today'


# ══════════════════════════════════════════════════════════════
# DATA: SAVE / LOAD (unchanged from v3)
# ══════════════════════════════════════════════════════════════

def save_scan_results(results_df, scan_date):
    if results_df.empty:
        print("No results to save")
        return
    stocks_list = []
    for idx, row in results_df.iterrows():
        entry = round(float(row.get('close', 0)), 2)
        sl    = round(float(row.get('sl', entry * 0.93)), 2)
        t1    = round(float(row.get('target1', entry + (entry - sl))), 2)
        t2    = round(float(row.get('target2', entry + 2 * (entry - sl))), 2)
        stocks_list.append({
            'rank':          idx + 1,
            'symbol':        str(row['symbol']),
            'score':         round(float(row.get('score', 0)), 2),
            'return_1m_pct': round(float(row.get('return_1m_pct', 0)), 1),
            'return_2m_pct': round(float(row.get('return_2m_pct', 0)), 1),
            'return_3m_pct': round(float(row.get('return_3m_pct', 0)), 1),
            'close':         entry,
            'volume':        int(row.get('volume', 0)),
            'delivery_pct':  round(float(row.get('delivery_pct', 0)), 1),
            'sl':            sl,
            'target1':       t1,
            'target2':       t2,
            'category':      str(row.get('category', 'rising')),
            'streak':        int(row.get('streak', 0)),
        })
    stocks_list.sort(key=lambda x: x['return_3m_pct'], reverse=True)
    for i, s in enumerate(stocks_list):
        s['rank'] = i + 1
    data = {
        'scan_date':    str(scan_date),
        'total_stocks': len(stocks_list),
        'page_size':    5,
        'stocks':       stocks_list,
    }
    with open(RESULTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    print(f"Scan results saved: {RESULTS_FILE}  ({len(stocks_list)} stocks)")
    save_history(stocks_list, scan_date)


def load_scan_results():
    if not os.path.exists(RESULTS_FILE):
        return None
    with open(RESULTS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_history(stocks_list, scan_date):
    today_str = str(scan_date)
    history = load_history()
    history = [h for h in history if h['date'] != today_str]
    history.append({
        'date':    today_str,
        'symbols': [s['symbol'] for s in stocks_list],
        'stocks':  [{
            'symbol': s['symbol'], 'score': s['score'],
            'return_3m_pct': s['return_3m_pct'],
            'return_1m_pct': s['return_1m_pct'],
            'close': s['close'], 'sl': s['sl'],
            'target1': s['target1'], 'target2': s['target2'],
            'category': s.get('category', 'rising'),
        } for s in stocks_list]
    })
    history.sort(key=lambda x: x['date'], reverse=True)
    history = history[:HISTORY_DAYS]
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump({'last_updated': today_str, 'days_stored': len(history),
                    'history': history}, f, indent=2)
    print(f"History saved: {HISTORY_FILE}  ({len(history)} days)")


def load_history():
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f).get('history', [])
    except Exception:
        return []


# ══════════════════════════════════════════════════════════════
# DATA: ANALYSIS (unchanged from v3)
# ══════════════════════════════════════════════════════════════

def get_new_stocks(history):
    if len(history) < 2:
        return []
    new = set(history[0]['symbols']) - set(history[1]['symbols'])
    return [s for s in history[0]['stocks'] if s['symbol'] in new]

def get_exit_stocks(history):
    if len(history) < 2:
        return []
    exits = set(history[1]['symbols']) - set(history[0]['symbols'])
    return [s for s in history[1]['stocks'] if s['symbol'] in exits]

def get_strong_stocks(history, min_days=5):
    if not history:
        return []
    strong = []
    for symbol in set(history[0]['symbols']):
        n = 0
        for day in history:
            if symbol in day['symbols']:
                n += 1
            else:
                break
        if n >= min_days:
            sd = next((s for s in history[0]['stocks'] if s['symbol'] == symbol), None)
            if sd:
                strong.append({**sd, 'consecutive_days': n})
    strong.sort(key=lambda x: x['consecutive_days'], reverse=True)
    return strong

def get_caution_stocks(stocks):
    return [s for s in stocks
            if s.get('score', 10) <= 5 or s.get('delivery_pct', 100) < 40]

def get_stock_streak(symbol, history):
    n = 0
    for day in history:
        if symbol in day['symbols']:
            n += 1
        else:
            break
    return n


def sort_stocks(stocks, mode='3m'):
    if mode == 'score':
        return sorted(stocks, key=lambda x: float(x.get('score', 0)), reverse=True)
    elif mode == 'top10':
        return sorted(stocks, key=lambda x: float(x.get('return_3m_pct', 0)), reverse=True)[:10]
    return sorted(stocks, key=lambda x: float(x.get('return_3m_pct', 0)), reverse=True)


# ══════════════════════════════════════════════════════════════
# PROBABILITY HELPER
# ══════════════════════════════════════════════════════════════

def _get_prob(stock):
    """Get T1/T2/SL probability for a stock from tracker or calculate fresh."""
    sym = stock.get('symbol', '')
    sig = get_signal(sym) if _TRACKER_OK else None
    if sig and sig.get('t1_prob', 0) > 0:
        return {
            "t1": sig.get("t1_prob", 0),
            "t2": sig.get("t2_prob", 0),
            "sl": sig.get("sl_prob", 0),
            "signal": sig,
        }
    score  = float(stock.get('score', 0))
    streak = int(stock.get('streak', 0))
    cat    = stock.get('category', '')
    cat_label = CATEGORY_META.get(cat, {}).get('label', '')
    prob = calculate_probability(score=score, streak=streak, category=cat_label)
    return {"t1": prob["t1_pct"], "t2": prob["t2_pct"], "sl": prob["sl_pct"], "signal": sig}


# ══════════════════════════════════════════════════════════════
# STOCK CARD (updated — with probability)
# ══════════════════════════════════════════════════════════════

def _stock_card(stock, rank=0, show_cat=False, show_prob=True, show_frozen=False):
    """
    Format one stock card. Now includes:
    - T1/T2 probability line
    - Optional frozen entry P/L (for Strong view)
    - Category tag
    """
    e  = float(stock.get('close', 0))
    sl = float(stock.get('sl', e * 0.93))
    t1 = float(stock.get('target1', e + (e - sl)))
    t2 = float(stock.get('target2', e + 2 * (e - sl)))
    r3 = float(stock.get('return_3m_pct', 0))
    sc = int(round(float(stock.get('score', 0))))
    st = int(stock.get('streak', 0))

    prefix = f"{_b(str(rank) + '.')} " if rank else ""
    stag = f" {st}d" if st >= 5 else ""

    msg = f"{prefix}{_code(stock['symbol'])}  {sc}/10{stag}\n"

    # Frozen entry P/L (if tracker has data and show_frozen requested)
    if show_frozen and _TRACKER_OK:
        sig = get_signal(stock['symbol'])
        if sig and sig.get('entry_price', 0) > 0:
            frozen_entry = sig['entry_price']
            msg += f"   Entry(frozen) {_fmt_price(frozen_entry)} | Now {_fmt_price(e)} | P/L {_fmt_pl(frozen_entry, e)}\n"

    msg += (f"   Entry {_fmt_price(e)} | SL {_fmt_price(sl)}\n"
            f"   T1 {_fmt_price(t1)} | T2 {_fmt_price(t2)} | "
            f"3M {_fmt_return(r3)}\n")

    # Probability line
    if show_prob:
        p = _get_prob(stock)
        if p["t1"] > 0:
            msg += f"   T1 {p['t1']}% | T2 {p['t2']}%\n"

    # Category tag
    if show_cat:
        cat = stock.get('category', 'rising')
        m = CATEGORY_META.get(cat, CATEGORY_META['rising'])
        msg += f"   {m['icon']} {_i(m['label'])}\n"

    return msg


# ══════════════════════════════════════════════════════════════
# NEWS (unchanged)
# ══════════════════════════════════════════════════════════════

def fetch_news_for_symbol(symbol, max_items=3):
    try:
        import requests
        from xml.etree import ElementTree as ET
        url = f"https://news.google.com/rss/search?q={symbol}+NSE+stock+India&hl=en-IN&gl=IN&ceid=IN:en"
        r = requests.get(url, timeout=6, headers={'User-Agent': 'Mozilla/5.0'})
        if r.status_code != 200:
            return []
        root = ET.fromstring(r.content)
        news = []
        for item in root.findall('.//item')[:max_items]:
            title = item.findtext('title', '').split(' - ')[0].strip()
            pub = item.findtext('pubDate', '')
            try:
                pub_fmt = datetime.strptime(pub[:16], '%a, %d %b %Y').strftime('%d-%b')
            except Exception:
                pub_fmt = pub[:10]
            news.append({'title': title, 'date': pub_fmt})
        return news
    except Exception:
        return []

def format_news_block(news):
    if not news:
        return f"   {_i('No recent news')}\n"
    return "".join(f"   \U0001F4F0 {_h(n['title'][:80])} {_i('(' + _h(n['date']) + ')')}\n" for n in news)


# ══════════════════════════════════════════════════════════════
# MESSAGE FORMATTERS (updated with probabilities)
# ══════════════════════════════════════════════════════════════

def format_today_scan(stocks, scan_date=None):
    ds = _date_str(scan_date)
    msg = f"\U0001F4CA {_b('NSE Daily Scan ' + chr(8212) + ' ' + ds)}\n"
    msg += f"{_i('Top ' + str(len(stocks)) + ' stocks, grouped by signal type')}\n\n"

    cats = {}
    for s in stocks:
        c = s.get('category', 'rising')
        cats.setdefault(c, []).append(s)

    parts = []
    for k in CATEGORY_ORDER:
        if k in cats:
            m = CATEGORY_META[k]
            parts.append(f"{m['icon']} {len(cats[k])} {m['label'].split()[0].lower()}")
    msg += " | ".join(parts) + "\n" + "\u2500" * 30 + "\n\n"

    rank = 1
    for k in CATEGORY_ORDER:
        if k not in cats:
            continue
        m = CATEGORY_META[k]
        msg += f"{m['icon']} {_b(m['label'])} ({len(cats[k])})\n"
        msg += f"   {_i(m['desc'])}\n\n"
        for s in cats[k]:
            msg += _stock_card(s, rank=rank, show_prob=True) + "\n"
            rank += 1

    # Tracker summary if available
    if _TRACKER_OK:
        ts = get_tracker_summary()
        if ts.get('avg_t1_prob', 0) > 0:
            msg += "\u2500" * 30 + "\n"
            msg += (f"Avg T1 prob: {ts['avg_t1_prob']}% | "
                    f"Avg T2 prob: {ts['avg_t2_prob']}% | "
                    f"T1 >70%: {ts.get('high_prob_count', 0)} stocks\n")

    msg += "\u2500" * 30 + "\n"
    msg += "Tap a view below to explore"
    return msg


def format_stock_list(stocks, start_idx=0, count=5, scan_date=None, include_news=False):
    end = min(start_idx + count, len(stocks))
    sel = stocks[start_idx:end]
    cp  = (start_idx // count) + 1
    tp  = max(1, (len(stocks) + count - 1) // count)
    ds  = _date_str(scan_date)

    msg = f"\U0001F4CA {_b('WATCHLIST ' + chr(8212) + ' ' + ds)}\n"
    msg += f"{_i('Sorted by 3M Return | Page ' + str(cp) + '/' + str(tp))}\n"
    msg += "\u2500" * 30 + "\n\n"

    for i, s in enumerate(sel, start=start_idx + 1):
        msg += _stock_card(s, rank=i, show_cat=True, show_prob=True)
        if include_news:
            msg += format_news_block(fetch_news_for_symbol(s['symbol']))
        msg += "\n"

    msg += f"Page {cp}/{tp}"
    return msg


def format_new_stocks(new_stocks, scan_date=None):
    ds = _date_str(scan_date)
    if not new_stocks:
        return (f"\U0001F195 {_b('NEW ENTRIES ' + chr(8212) + ' ' + ds)}\n\n"
                f"{_i('No new stocks entered today')}\n\n"
                "All 25 carried over from yesterday \u2014 consistency!")

    msg = (f"\U0001F195 {_b('NEW ENTRIES ' + chr(8212) + ' ' + ds)}\n"
           f"{_i(str(len(new_stocks)) + ' stock(s) entered top 25 today')}\n"
           f"{_i('Fresh signals \u2014 consider for new positions')}\n"
           + "\u2500" * 30 + "\n\n")

    for i, s in enumerate(new_stocks, 1):
        msg += _stock_card(s, rank=i, show_cat=True, show_prob=True) + "\n"

    msg += f"{len(new_stocks)} new stock(s) entered today"
    return msg


def format_exit_stocks(exit_stocks, scan_date=None):
    ds = _date_str(scan_date)
    if not exit_stocks:
        return (f"\U0001F4C9 {_b('EXIT WATCH ' + chr(8212) + ' ' + ds)}\n\n"
                f"{_i('No stocks exited today')}\n\n"
                "Yesterday's list intact \u2014 momentum holding!")

    msg = (f"\U0001F4C9 {_b('EXIT WATCH ' + chr(8212) + ' ' + ds)}\n"
           f"{_i('Dropped out \u2014 consider booking profits')}\n"
           + "\u2500" * 30 + "\n\n")

    for i, s in enumerate(exit_stocks, 1):
        r3  = float(s.get('return_3m_pct', 0))
        sc  = int(round(float(s.get('score', 0))))
        e   = float(s.get('close', 0))
        cat = s.get('category', 'rising')
        m   = CATEGORY_META.get(cat, CATEGORY_META['rising'])

        msg += f"{_b(str(i) + '.')}  {_code(s['symbol'])}  {sc}/10  [Exited]\n"

        # Show frozen entry P/L from tracker if available
        if _TRACKER_OK:
            sig = get_signal(s['symbol'])
            if sig and sig.get('entry_price', 0) > 0:
                frozen = sig['entry_price']
                days   = sig.get('days_in_list', sig.get('streak', 0))
                t1_hit = "T1 was hit" if sig.get('t1_hit_date') else "T1 not hit"
                msg += f"   Was in list {days} days\n"
                msg += f"   Entry {_fmt_price(frozen)} \u2192 Exit {_fmt_price(e)}\n"
                msg += f"   Final P/L: {_fmt_pl(frozen, e)} | {t1_hit}\n"
            else:
                msg += f"   Last price {_fmt_price(e)} | 3M {_fmt_return(r3)}\n"
        else:
            msg += f"   Last price {_fmt_price(e)} | 3M {_fmt_return(r3)}\n"

        msg += f"   Was: {m['icon']} {_i(m['label'])}\n"
        msg += f"   {_i('Consider tightening stop loss')}\n\n"

    msg += f"{len(exit_stocks)} stock(s) dropped out today"
    return msg


def format_caution_stocks(stocks, scan_date=None):
    ds = _date_str(scan_date)
    caution = get_caution_stocks(stocks)
    if not caution:
        return (f"\u26A0\ufe0f {_b('CAUTION FLAGS ' + chr(8212) + ' ' + ds)}\n\n"
                f"{_i('No caution flags \u2014 all stocks looking solid!')}")

    msg = (f"\u26A0\ufe0f {_b('CAUTION FLAGS ' + chr(8212) + ' ' + ds)}\n"
           f"{_i('Weaker signals \u2014 trade carefully')}\n"
           + "\u2500" * 30 + "\n\n")

    for i, s in enumerate(caution, 1):
        sc = int(round(float(s.get('score', 0))))
        dl = float(s.get('delivery_pct', 0))
        e  = float(s.get('close', 0))
        r3 = float(s.get('return_3m_pct', 0))

        reasons = []
        if sc <= 5:
            reasons.append("Score at lower end")
        if dl < 40:
            reasons.append(f"Low delivery {dl:.0f}%")
        if r3 > 40:
            reasons.append(f"Overextended ({_fmt_return(r3)})")

        # Get probabilities with SL risk
        p = _get_prob(s)

        msg += f"{_b(str(i) + '.')}  {_code(s['symbol'])}  {sc}/10\n"
        msg += f"   Price {_fmt_price(e)} | 3M {_fmt_return(r3)}\n"

        if p["t1"] > 0:
            msg += f"   T1 prob: {p['t1']}% | SL risk: {p['sl']}%\n"

        msg += f"   \u26A0\ufe0f {' | '.join(reasons)}\n"

        # Warning box for high risk
        if p["sl"] >= 35:
            msg += f"   {_i('High SL risk \u2014 tighten stop or book profits')}\n"
        elif r3 > 40:
            msg += f"   {_i('Overextended \u2014 high correction risk')}\n"

        msg += "\n"

    msg += f"{len(caution)} stock(s) need extra caution"
    return msg


def format_strong_stocks(strong_stocks, scan_date=None):
    ds = _date_str(scan_date)
    if not strong_stocks:
        return (f"\U0001F525 {_b('STRONG PICKS ' + chr(8212) + ' ' + ds)}\n\n"
                f"{_i('No stocks in top 25 for 5+ days yet')}\n\n"
                "Building history \u2014 check back soon.")

    msg = (f"\U0001F525 {_b('STRONG PICKS ' + chr(8212) + ' ' + ds)}\n"
           f"{_i('In top 25 for 5+ consecutive days')}\n"
           f"{_i('Sustained momentum = strongest conviction')}\n"
           + "\u2500" * 30 + "\n\n")

    for i, s in enumerate(strong_stocks, 1):
        e  = float(s.get('close', 0))
        sl = float(s.get('sl', e * 0.93))
        t1 = float(s.get('target1', e + (e - sl)))
        t2 = float(s.get('target2', e + 2 * (e - sl)))
        r3 = float(s.get('return_3m_pct', 0))
        sc = int(round(float(s.get('score', 0))))
        dy = s.get('consecutive_days', 0)
        cat = s.get('category', 'rising')
        m = CATEGORY_META.get(cat, CATEGORY_META['rising'])

        msg += f"{_b(str(i) + '.')}  {_code(s['symbol'])}  {sc}/10  {dy}d streak\n"
        msg += f"   {m['icon']} {_i(m['label'])}\n"

        # Frozen entry P/L from tracker
        if _TRACKER_OK:
            sig = get_signal(s['symbol'])
            if sig and sig.get('entry_price', 0) > 0:
                frozen = sig['entry_price']
                msg += (f"   Entry(frozen {sig.get('entry_date', '?')[:10]}) "
                        f"{_fmt_price(frozen)} | Now {_fmt_price(e)} | "
                        f"P/L {_fmt_pl(frozen, e)}\n")

        msg += (f"   Entry {_fmt_price(e)} | SL {_fmt_price(sl)}\n"
                f"   T1 {_fmt_price(t1)} | T2 {_fmt_price(t2)} | "
                f"3M {_fmt_return(r3)}\n")

        # Probability
        p = _get_prob(s)
        if p["t1"] > 0:
            msg += f"   T1 {p['t1']}% | T2 {p['t2']}%\n"

        msg += "\n"

    msg += f"{len(strong_stocks)} stock(s) with sustained momentum"
    return msg


def format_welcome(user_name=None):
    name = f" {user_name}" if user_name else ""
    return (
        f"\U0001F44B {_b('Hello' + name + '! Welcome to NSE Scanner Daily.')}\n\n"
        "Here is what I can show you:\n\n"
        f"\U0001F4CA {_b('Today')} \u2014 Top 25 bucketed by signal\n"
        f"\U0001F195 {_b('New')} \u2014 Stocks added today\n"
        f"\U0001F4C9 {_b('Exit')} \u2014 Stocks removed today\n"
        f"\u26A0\ufe0f {_b('Caution')} \u2014 Weaker signals with SL risk\n"
        f"\U0001F525 {_b('Strong')} \u2014 5+ day streak with frozen P/L\n"
        f"\U0001F5C2 {_b('Buckets')} \u2014 Stocks by category\n"
        f"\U0001F4D6 {_b('Guide')} \u2014 How to read the scanner\n\n"
        "Tap a button below!"
    )


def format_help():
    return (
        f"\U0001F916 {_b('NSE Momentum Scanner Bot')}\n\n"
        f"{_b('Views:')}\n"
        "\U0001F4CA /today \u2014 Bucketed daily scan\n"
        "\U0001F195 /new \u2014 New entries today\n"
        "\U0001F4C9 /exit \u2014 Exit signals\n"
        "\u26A0\ufe0f /caution \u2014 Caution flags + SL risk\n"
        "\U0001F525 /strong \u2014 Strong picks with frozen P/L\n"
        "\U0001F5C2 /buckets \u2014 Category breakdown\n"
        "\U0001F4D6 /guide \u2014 How to read the scanner\n\n"
        f"{_b('Navigation:')}\n"
        "/start \u2014 Welcome menu\n"
        "/list \u2014 Flat ranked list\n"
        "/next /prev \u2014 Paginate\n"
        "/news \u2014 Page with headlines\n"
        "/help \u2014 This message\n\n"
        f"{_b('Sorting:')}\n"
        "3M \u2014 Sort by 3-month return\n"
        "Score \u2014 Sort by scanner score\n"
        "Top10 \u2014 Show top 10 only\n\n"
        f"{_b('Admin (owner only):')}\n"
        "/admin \u2014 Health check dashboard\n"
        "/users \u2014 Bot user list\n\n"
        f"{_b('Categories:')}\n"
        "\U0001F4C8 Rising \u2014 all returns positive\n"
        "\U0001F680 Uptrend \u2014 breakout confirmed\n"
        "\U0001F51D Near Peak \u2014 close to 52W high\n"
        "\U0001F6E1\ufe0f Safer \u2014 high delivery, good RR\n"
        "\U0001F4C9 Recovering \u2014 bouncing back\n\n"
        "\u25c0 Back \u2014 go up one level\n"
        "\u25c0\u25c0 Main \u2014 jump to home\n\n"
        "Tap buttons to navigate!"
    )


# ══════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test",    action="store_true")
    parser.add_argument("--history", action="store_true")
    parser.add_argument("--demo",    action="store_true")
    args = parser.parse_args()

    if args.test:
        import pandas as pd
        cats = (["rising"] * 5 + ["uptrend"] * 3 + ["peak"] * 5 +
                ["safer"] * 5 + ["recovering"] * 4 + ["rising"] * 3)
        df = pd.DataFrame({
            'symbol':        [f'STOCK{i:02d}' for i in range(1, 26)],
            'score':         [9 - i * 0.15 for i in range(25)],
            'return_1m_pct': [15 - i * 0.3 for i in range(25)],
            'return_2m_pct': [25 - i * 0.4 for i in range(25)],
            'return_3m_pct': [30 - i * 1.0 for i in range(25)],
            'close':         [1000 + i * 50 for i in range(25)],
            'volume':        [1000000 for _ in range(25)],
            'delivery_pct':  [40 + i * 1.5 for i in range(25)],
            'sl':            [950 + i * 47 for i in range(25)],
            'target1':       [1050 + i * 53 for i in range(25)],
            'target2':       [1100 + i * 56 for i in range(25)],
            'category':      cats[:25],
            'streak':        [12 - i // 2 for i in range(25)],
        })
        save_scan_results(df, date.today())
        print("Test data saved\n")

    if args.demo:
        res = load_scan_results()
        if res:
            stocks = res['stocks']
            import re
            strip = lambda t: re.sub(r'<[^>]+>', '', t)
            print("\n" + "=" * 50)
            print(strip(format_welcome("Jayesh")))
            print("\n" + "=" * 50)
            print(strip(format_today_scan(stocks, res['scan_date'])))
            print("\n" + "=" * 50)
            print(strip(format_help()))

    if args.history:
        h = load_history()
        print(f"History: {len(h)} days")
        print(f"New:    {[s['symbol'] for s in get_new_stocks(h)]}")
        print(f"Exit:   {[s['symbol'] for s in get_exit_stocks(h)]}")
        print(f"Strong: {[s['symbol'] for s in get_strong_stocks(h)]}")


if __name__ == "__main__":
    main()
