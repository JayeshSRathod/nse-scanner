"""
nse_telegram_handler.py — Telegram Bot Handler (v6 — Situation Engine)
========================================================================
WHAT CHANGED FROM v5:
  1. SITUATION ENGINE added
     - assign_situation() maps each stock to prime/watch/hold/book/avoid
     - format_today_scan() now groups by situation (not category)
     - format_prime_stocks() — new dedicated PRIME ENTRY view
     - format_situation_scan() — full situation-grouped message

  2. STOCK CARD updated
     - Shows situation label + action advice
     - Shows signal breakdown (cross age, room, volume)
     - 3M return shown as (ref) not as ranking signal

  3. PROBABILITY updated
     - Now uses freshness + room + situation in calculation
     - Situation AVOID/BOOK reduce probability appropriately

  4. SORT updated
     - Default sort = by forward score (not 3M return)
     - 3M sort still available as option

  5. HELP updated
     - New /prime command documented
     - Situation descriptions added

All other functions (save/load, history, news,
new/exit/strong/caution formats) unchanged.
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
    SITUATION_META  = getattr(config, 'SITUATION_META', {})
    SITUATION_ORDER = getattr(config, 'SITUATION_ORDER',
                              ["prime", "hold", "watch", "book", "avoid"])
    SITUATION_PRIME = getattr(config, 'SITUATION_PRIME', "prime")
    SITUATION_WATCH = getattr(config, 'SITUATION_WATCH', "watch")
    SITUATION_HOLD  = getattr(config, 'SITUATION_HOLD',  "hold")
    SITUATION_BOOK  = getattr(config, 'SITUATION_BOOK',  "book")
    SITUATION_AVOID = getattr(config, 'SITUATION_AVOID', "avoid")
except ImportError:
    config = None
    SITUATION_META = {
        "prime": {"icon": "🎯", "label": "Prime Entry",
                  "action": "Enter today — confirm on TradingView"},
        "watch": {"icon": "👀", "label": "Watch Closely",
                  "action": "Good setup. One condition missing."},
        "hold":  {"icon": "💰", "label": "Hold & Trail",
                  "action": "Already in move — trail your stop loss."},
        "book":  {"icon": "⚠️", "label": "Book Profits",
                  "action": "Move maturing — protect gains."},
        "avoid": {"icon": "🚫", "label": "Avoid Now",
                  "action": "Weak setup — skip today."},
    }
    SITUATION_ORDER = ["prime", "hold", "watch", "book", "avoid"]
    SITUATION_PRIME = "prime"
    SITUATION_WATCH = "watch"
    SITUATION_HOLD  = "hold"
    SITUATION_BOOK  = "book"
    SITUATION_AVOID = "avoid"

_TRACKER_OK = False
try:
    from nse_signal_tracker import (
        get_signal, calculate_probability, get_tracker_summary,
        STATE_ACTIVE, STATE_T1_HIT, STATE_T2_HIT,
        STATE_WEAKENING, STATE_EXITED,
    )
    _TRACKER_OK = True
except ImportError:
    def get_signal(s): return None
    def calculate_probability(**kw): return {"t1_pct": 0, "t2_pct": 0, "sl_pct": 0}
    def get_tracker_summary(): return {}

# ── Category metadata (kept for backwards compatibility) ──────
CATEGORY_META = {
    "rising":     {"icon": "📈", "label": "Consistently Rising",
                   "desc": "Steady momentum, early in the move"},
    "uptrend":    {"icon": "🚀", "label": "Clear Uptrend Confirmed",
                   "desc": "Fresh cross, room to run, volume confirmed"},
    "peak":       {"icon": "🔝", "label": "Close to Their Peak",
                   "desc": "Near 52-week highs — strong institutional demand"},
    "recovering": {"icon": "📉", "label": "Recovering from a Fall",
                   "desc": "Bouncing back — early recovery signal"},
    "safer":      {"icon": "🛡️", "label": "Safer Bets with Good Reward",
                   "desc": "Tight stop, high delivery, lower risk setup"},
}
CATEGORY_ORDER = ["uptrend", "rising", "peak", "safer", "recovering"]

SEP_BOLD = "━" * 17
SEP_THIN = "─" * 18


# ═══════════════════════════════════════════════════════════════
# HTML HELPERS
# ═══════════════════════════════════════════════════════════════

def _h(v):
    return str(v).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

def _b(v):    return f"<b>{_h(v)}</b>"
def _i(v):    return f"<i>{_h(v)}</i>"
def _code(v): return f"<code>{_h(v)}</code>"

def _fmt_price(p):
    return f"₹{int(round(float(p))):,}"

def _fmt_return(pct):
    pct  = float(pct)
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


# ═══════════════════════════════════════════════════════════════
# SITUATION ENGINE — NEW
# ═══════════════════════════════════════════════════════════════

def assign_situation(stock: dict, streak: int = 0) -> str:
    """
    Assign a situation label to a stock based on forward signals.

    Priority order:
      1. AVOID   — score ≤ 3 OR distribution volume OR bearish
      2. BOOK    — cross age > 30d OR >15% stretched
      3. HOLD    — streak ≥ 5 days AND score still OK
      4. PRIME   — score ≥ 7 + fresh cross + not overextended
      5. WATCH   — everything else that passes

    Args:
        stock:  stock dict from scan results
        streak: consecutive days in scanner list

    Returns:
        situation string: prime/watch/hold/book/avoid
    """
    score        = float(stock.get('score', 0))
    cross_age    = int(stock.get('cross_age', 999))
    dist_pct     = float(stock.get('dist_pct', 0))
    overextended = bool(stock.get('overextended', False))
    fresh_cross  = bool(stock.get('fresh_cross', False))
    acc_days     = int(stock.get('acc_days', 0))
    dist_days    = int(stock.get('dist_days', 0))
    obv_dir      = str(stock.get('obv_dir', 'flat'))
    r3m          = float(stock.get('return_3m_pct', 0))

    # ── 1. AVOID — weak, bearish or distribution ──────────────
    if score <= 3:
        return SITUATION_AVOID
    if dist_days >= 4 and obv_dir == 'falling':
        return SITUATION_AVOID
    if cross_age == -1:   # bearish — HMA20 below HMA55
        return SITUATION_AVOID

    # ── 2. BOOK PROFITS — move is mature or stretched ─────────
    if overextended and cross_age > 20:
        return SITUATION_BOOK
    if cross_age > 30 and dist_pct > 10:
        return SITUATION_BOOK
    if r3m > 40 and score < 6:
        return SITUATION_BOOK

    # ── 3. HOLD AND TRAIL — sustained momentum ─────────────────
    if streak >= 5 and score >= 5:
        return SITUATION_HOLD

    # ── 4. PRIME ENTRY — best forward setup ───────────────────
    if (score >= 7 and
            not overextended and
            cross_age <= 20 and
            acc_days >= 3):
        return SITUATION_PRIME

    # ── 5. WATCH CLOSELY — good but not perfect ───────────────
    return SITUATION_WATCH


def get_situation_signal_line(stock: dict) -> str:
    """
    Returns a compact signal summary showing WHY the situation was assigned.
    Example: "🟢 Cross 4d | 3.2% room | Accum vol | Sector ✅"
    """
    parts = []

    cross_age    = int(stock.get('cross_age', 999))
    dist_pct     = float(stock.get('dist_pct', 0))
    fresh_cross  = bool(stock.get('fresh_cross', False))
    overextended = bool(stock.get('overextended', False))
    acc_days     = int(stock.get('acc_days', 0))
    dist_days    = int(stock.get('dist_days', 0))
    obv_dir      = str(stock.get('obv_dir', 'flat'))
    sector_bias  = int(stock.get('sector_bias', 0))

    # HMA cross age
    if cross_age == -1:
        parts.append("Bearish HMA")
    elif fresh_cross:
        parts.append(f"🟢 Cross {cross_age}d")
    elif cross_age <= 20:
        parts.append(f"Cross {cross_age}d")
    elif cross_age < 999:
        parts.append(f"⚠️ Cross {cross_age}d ago")
    else:
        parts.append("No cross")

    # Distance from mean
    if overextended:
        parts.append(f"⚠️ {dist_pct:.0f}% stretched")
    elif dist_pct <= 5.0:
        parts.append(f"🟢 {dist_pct:.1f}% room")
    else:
        parts.append(f"{dist_pct:.1f}% above")

    # Volume quality
    if acc_days >= 4 and obv_dir == 'rising':
        parts.append("🟢 Accum vol")
    elif dist_days >= 4 or obv_dir == 'falling':
        parts.append("🔴 Dist vol")
    else:
        parts.append("Vol OK")

    # Sector
    if sector_bias == 1:
        parts.append("Sector ✅")
    elif sector_bias == -1:
        parts.append("Sector ❌")

    return " | ".join(parts)


# ═══════════════════════════════════════════════════════════════
# PROBABILITY HELPER — Updated with situation awareness
# ═══════════════════════════════════════════════════════════════

def _get_prob(stock: dict) -> dict:
    """Get T1/T2 probability for a stock using situation-aware model."""
    sym = stock.get('symbol', '')
    sig = get_signal(sym) if _TRACKER_OK else None

    if sig and sig.get('t1_prob', 0) > 0:
        return {
            "t1": sig["t1_prob"],
            "t2": sig["t2_prob"],
            "sl": sig["sl_prob"],
            "signal": sig,
        }

    score      = float(stock.get('score', 0))
    streak     = int(stock.get('streak', 0))
    cat        = stock.get('category', '')
    situation  = stock.get('situation', '')
    cross_age  = int(stock.get('cross_age', 999))
    dist_pct   = float(stock.get('dist_pct', 0))
    cat_label  = CATEGORY_META.get(cat, {}).get('label', '')

    prob = calculate_probability(
        score=score,
        streak=streak,
        category=cat_label,
        situation=situation,
        cross_age=cross_age,
        dist_pct=dist_pct,
    )
    return {
        "t1": prob["t1_pct"],
        "t2": prob["t2_pct"],
        "sl": prob["sl_pct"],
        "signal": sig,
    }


# ═══════════════════════════════════════════════════════════════
# DATA: SAVE / LOAD / HISTORY
# ═══════════════════════════════════════════════════════════════

def save_scan_results(results_df, scan_date):
    """Save scan results to JSON. Sorted by forward score."""
    if results_df.empty:
        print("No results to save")
        return

    stocks_list = []
    for idx, row in results_df.iterrows():
        entry = round(float(row.get('close', 0)), 2)
        sl    = round(float(row.get('sl', entry * 0.93)), 2)
        t1    = round(float(row.get('target1', entry + (entry - sl))), 2)
        t2    = round(float(row.get('target2', entry + 2 * (entry - sl))), 2)

        # Determine situation
        streak = int(row.get('streak', 0))
        row_dict = row.to_dict() if hasattr(row, 'to_dict') else dict(row)
        situation = row_dict.get('situation', '') or assign_situation(row_dict, streak)

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
            'situation':     situation,
            # Forward score signals (for display)
            'cross_age':     int(row.get('cross_age', 999)),
            'dist_pct':      round(float(row.get('dist_pct', 0)), 1),
            'fresh_cross':   bool(row.get('fresh_cross', False)),
            'overextended':  bool(row.get('overextended', False)),
            'acc_days':      int(row.get('acc_days', 0)),
            'dist_days':     int(row.get('dist_days', 0)),
            'obv_dir':       str(row.get('obv_dir', 'flat')),
            'sector_bias':   int(row.get('sector_bias', 0)),
        })

    # Sort by forward score (situation priority first, then score)
    sit_priority = {SITUATION_PRIME: 0, SITUATION_HOLD: 1,
                    SITUATION_WATCH: 2, SITUATION_BOOK: 3, SITUATION_AVOID: 4}
    stocks_list.sort(
        key=lambda x: (
            sit_priority.get(x.get('situation', 'watch'), 2),
            -float(x.get('score', 0))
        )
    )
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

    print(f"✅ Scan results saved: {RESULTS_FILE}  ({len(stocks_list)} stocks)")
    save_history(stocks_list, scan_date)


def load_scan_results():
    if not os.path.exists(RESULTS_FILE):
        return None
    with open(RESULTS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_history(stocks_list, scan_date):
    today_str = str(scan_date)
    history   = load_history()
    history   = [h for h in history if h['date'] != today_str]
    history.append({
        'date':    today_str,
        'symbols': [s['symbol'] for s in stocks_list],
        'stocks':  [{
            'symbol':        s['symbol'],
            'score':         s['score'],
            'return_3m_pct': s['return_3m_pct'],
            'return_1m_pct': s['return_1m_pct'],
            'close':         s['close'],
            'sl':            s['sl'],
            'target1':       s['target1'],
            'target2':       s['target2'],
            'category':      s.get('category', 'rising'),
            'situation':     s.get('situation', 'watch'),
        } for s in stocks_list]
    })
    history.sort(key=lambda x: x['date'], reverse=True)
    history = history[:HISTORY_DAYS]
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump({
            'last_updated': today_str,
            'days_stored':  len(history),
            'history':      history,
        }, f, indent=2)


def load_history():
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f).get('history', [])
    except Exception:
        return []


def get_new_stocks(history):
    if len(history) < 2: return []
    new = set(history[0]['symbols']) - set(history[1]['symbols'])
    return [s for s in history[0]['stocks'] if s['symbol'] in new]


def get_exit_stocks(history):
    if len(history) < 2: return []
    exits = set(history[1]['symbols']) - set(history[0]['symbols'])
    return [s for s in history[1]['stocks'] if s['symbol'] in exits]


def get_strong_stocks(history, min_days=5):
    if not history: return []
    strong = []
    for symbol in set(history[0]['symbols']):
        n = 0
        for day in history:
            if symbol in day['symbols']: n += 1
            else: break
        if n >= min_days:
            sd = next((s for s in history[0]['stocks']
                       if s['symbol'] == symbol), None)
            if sd:
                strong.append({**sd, 'consecutive_days': n})
    strong.sort(key=lambda x: x['consecutive_days'], reverse=True)
    return strong


def get_caution_stocks(stocks):
    """Returns stocks that need extra caution."""
    caution = []
    for s in stocks:
        score    = float(s.get('score', 10))
        delivery = float(s.get('delivery_pct', 100))
        r3m      = float(s.get('return_3m_pct', 0))
        dist_pct = float(s.get('dist_pct', 0))
        situation = s.get('situation', 'watch')

        if (score <= 5 or
                delivery < 40 or
                r3m > 40 or
                dist_pct > 15 or
                situation in (SITUATION_AVOID, SITUATION_BOOK)):
            caution.append(s)
    return caution


def get_stock_streak(symbol, history):
    n = 0
    for day in history:
        if symbol in day['symbols']: n += 1
        else: break
    return n


# ═══════════════════════════════════════════════════════════════
# SORTING — Updated default to forward score
# ═══════════════════════════════════════════════════════════════

def sort_stocks(stocks, mode='score'):
    """
    Sort stocks by mode.
    Default changed from '3m' to 'score' (forward score).
    """
    sit_priority = {
        SITUATION_PRIME: 0, SITUATION_HOLD: 1,
        SITUATION_WATCH: 2, SITUATION_BOOK: 3, SITUATION_AVOID: 4,
    }

    if mode == 'score':
        return sorted(
            stocks,
            key=lambda x: (
                sit_priority.get(x.get('situation', 'watch'), 2),
                -float(x.get('score', 0))
            )
        )
    elif mode == '3m':
        return sorted(stocks,
                      key=lambda x: float(x.get('return_3m_pct', 0)),
                      reverse=True)
    elif mode == 'top10':
        return sorted(stocks,
                      key=lambda x: float(x.get('score', 0)),
                      reverse=True)[:10]
    elif mode == 'prime':
        return [s for s in stocks
                if s.get('situation') == SITUATION_PRIME]
    return sorted(stocks,
                  key=lambda x: float(x.get('score', 0)),
                  reverse=True)


# ═══════════════════════════════════════════════════════════════
# NEWS
# ═══════════════════════════════════════════════════════════════

def fetch_news_for_symbol(symbol, max_items=3):
    try:
        import requests
        from xml.etree import ElementTree as ET
        url = (f"https://news.google.com/rss/search"
               f"?q={symbol}+NSE+stock+India&hl=en-IN&gl=IN&ceid=IN:en")
        r = requests.get(url, timeout=6,
                         headers={'User-Agent': 'Mozilla/5.0'})
        if r.status_code != 200:
            return []
        root = ET.fromstring(r.content)
        news = []
        for item in root.findall('.//item')[:max_items]:
            title   = item.findtext('title', '').split(' - ')[0].strip()
            pub     = item.findtext('pubDate', '')
            try:
                pub_fmt = datetime.strptime(pub[:16],
                                            '%a, %d %b %Y').strftime('%d-%b')
            except Exception:
                pub_fmt = pub[:10]
            news.append({'title': title, 'date': pub_fmt})
        return news
    except Exception:
        return []


def format_news_block(news):
    if not news:
        return f"   {_i('No recent news')}\n"
    return "".join(
        f"   📰 {_h(n['title'][:80])} {_i('(' + n['date'] + ')')}\n"
        for n in news
    )


# ═══════════════════════════════════════════════════════════════
# STOCK CARD — Updated with situation + signal line
# ═══════════════════════════════════════════════════════════════

def _stock_card(stock, rank=0, show_prob=True,
                show_frozen=False, show_signal=True):
    """
    Render one stock card with situation context.

    New fields shown:
      - Situation label + action
      - Signal line (cross age, room, volume)
      - 3M return labelled as (ref)
    """
    e   = float(stock.get('close', 0))
    sl  = float(stock.get('sl', e * 0.93))
    t1  = float(stock.get('target1', e + (e - sl)))
    t2  = float(stock.get('target2', e + 2 * (e - sl)))
    r3  = float(stock.get('return_3m_pct', 0))
    sc  = int(round(float(stock.get('score', 0))))
    st  = int(stock.get('streak', 0))
    sit = stock.get('situation', SITUATION_WATCH)

    sm       = SITUATION_META.get(sit, SITUATION_META.get('watch', {}))
    sit_icon = sm.get('icon', '•')
    sit_lbl  = sm.get('label', sit.title())

    prefix   = f"{_b(str(rank) + '.')} " if rank else ""
    stag     = f"  🔥{st}d" if st >= 5 else ""

    msg = f"{prefix}{_code(stock['symbol'])}  {sc}/10{stag}  {sit_icon}\n"

    # Frozen P&L for tracker
    if show_frozen and _TRACKER_OK:
        sig = get_signal(stock['symbol'])
        if sig and sig.get('entry_price', 0) > 0:
            fe = sig['entry_price']
            fd = sig.get('entry_date', '?')[:10]
            msg += f"   Entry(frozen {fd}) {_fmt_price(fe)} | Now {_fmt_price(e)}\n"
            msg += f"   P/L {_fmt_pl(fe, e)}\n"

    # Trade levels
    msg += f"   Entry {_fmt_price(e)} | SL {_fmt_price(sl)}\n"
    msg += f"   T1 {_fmt_price(t1)} | T2 {_fmt_price(t2)}"

    # T1/T2 probabilities
    if show_prob:
        p = _get_prob(stock)
        if p["t1"] > 0:
            msg += f"  ·  T1 {p['t1']}% T2 {p['t2']}%"
    msg += "\n"

    # Signal breakdown line
    if show_signal and any(k in stock for k in
                           ['cross_age', 'dist_pct', 'acc_days']):
        sig_line = get_situation_signal_line(stock)
        if sig_line:
            msg += f"   {_i(sig_line)}\n"

    # 3M return as reference
    msg += f"   3M {_fmt_return(r3)} {_i('(ref)')}\n"

    return msg


# ═══════════════════════════════════════════════════════════════
# FORMAT: WELCOME — Updated with situation summary
# ═══════════════════════════════════════════════════════════════

def format_welcome(user_name=None):
    name = f" {user_name}" if user_name else ""

    sit_line = ""
    try:
        res = load_scan_results()
        if res and res.get('stocks'):
            stocks = res['stocks']
            ds     = _date_str(res.get('scan_date', ''))

            # Count by situation
            sit_counts = {}
            for s in stocks:
                sit = s.get('situation', SITUATION_WATCH)
                sit_counts[sit] = sit_counts.get(sit, 0) + 1

            parts = []
            for sit in SITUATION_ORDER:
                if sit in sit_counts:
                    sm = SITUATION_META.get(sit, {})
                    parts.append(
                        f"{sm.get('icon','·')} {sit_counts[sit]} "
                        f"{sm.get('label','').split()[0].lower()}"
                    )

            prime_count = sit_counts.get(SITUATION_PRIME, 0)
            prime_note  = (f"\n{_b(f'🎯 {prime_count} stock(s) ready to enter today!')}"
                           if prime_count > 0 else "")

            sit_line = (
                f"{_b('NSE Scanner Daily')}\n"
                f"{ds} · {len(stocks)} stocks scanned\n"
                f"{SEP_BOLD}\n"
                f"{_b('Today')}s situation\n"
                + " · ".join(parts)
                + prime_note + "\n"
                f"{SEP_BOLD}\n"
            )
    except Exception:
        pass

    if not sit_line:
        sit_line = f"{_b('NSE Scanner Daily')}\n{SEP_BOLD}\n"

    return (
        f"👋 {_b('Hello' + name + '!')}\n\n"
        + sit_line +
        "\n"
        f"🎯 {_b('Prime')} — Stocks ready to enter today\n"
        f"📊 {_b('Today')} — Full situation scan\n"
        f"🆕 {_b('New')} — Stocks added today\n"
        f"📉 {_b('Exit')} — Stocks removed today\n"
        f"⚠️ {_b('Caution')} — Risk flags + avoid signals\n"
        f"💰 {_b('Strong')} — 5+ day streak with frozen P/L\n"
        f"📅 {_b('Digest')} — Last week performance\n"
        f"📖 {_b('Guide')} — How to read the scanner\n\n"
        f"{_i('Tap a view below to explore')}"
    )


# ═══════════════════════════════════════════════════════════════
# FORMAT: TODAY SCAN — Grouped by situation
# ═══════════════════════════════════════════════════════════════

def format_today_scan(stocks, scan_date=None):
    """
    Main daily scan grouped by situation.
    PRIME ENTRY stocks shown first with full detail.
    Others shown as compact list.
    """
    ds   = _date_str(scan_date)

    # Group by situation
    sit_groups = {}
    for s in stocks:
        streak = int(s.get('streak', 0))
        sit    = s.get('situation') or assign_situation(s, streak)
        sit_groups.setdefault(sit, []).append({**s, 'situation': sit})

    # Summary line
    parts = []
    for sit in SITUATION_ORDER:
        if sit in sit_groups:
            sm = SITUATION_META.get(sit, {})
            parts.append(
                f"{sm.get('icon','·')} {len(sit_groups[sit])} "
                f"{sm.get('label','').split()[0].lower()}"
            )

    msg  = f"📊 {_b('NSE Daily Scan — ' + ds)}\n"
    msg += f"{_i('Ranked by forward probability score')}\n\n"
    msg += " · ".join(parts) + "\n"
    msg += SEP_THIN + "\n\n"

    rank = 1
    for sit in SITUATION_ORDER:
        group = sit_groups.get(sit, [])
        if not group:
            continue
        sm = SITUATION_META.get(sit, {})
        msg += (f"{sm.get('icon','')} {_b(sm.get('label', sit.title()))} "
                f"({len(group)})\n")
        msg += f"   {_i(sm.get('action', ''))}\n\n"

        # PRIME and HOLD get full cards
        if sit in (SITUATION_PRIME, SITUATION_HOLD):
            for s in group:
                msg += _stock_card(s, rank=rank, show_prob=True,
                                   show_frozen=(sit == SITUATION_HOLD),
                                   show_signal=True)
                msg += "\n"
                rank += 1
        else:
            # WATCH / BOOK / AVOID — compact list
            for s in group:
                sc    = int(round(float(s.get('score', 0))))
                e     = float(s.get('close', 0))
                r3    = float(s.get('return_3m_pct', 0))
                cross = int(s.get('cross_age', 999))
                cross_str = (f"cross {cross}d" if 0 < cross < 999 else
                             "no cross" if cross == 999 else "bearish")
                msg += (f"{_b(str(rank) + '.')} {_code(s['symbol'])}  {sc}/10"
                        f"  {_fmt_price(e)}  {_i(cross_str)}\n")
                rank += 1
            msg += "\n"

    # Probability summary
    if _TRACKER_OK:
        ts = get_tracker_summary()
        if ts.get('avg_t1_prob', 0) > 0:
            msg += SEP_THIN + "\n"
            msg += (f"{_b('Probability outlook')}\n"
                    f"Avg T1: {ts['avg_t1_prob']}% · "
                    f"Avg T2: {ts['avg_t2_prob']}% · "
                    f"T1>70%: {_b(str(ts.get('high_prob_count', 0)))} stocks\n")

    msg += SEP_THIN + "\n"
    msg += f"{_i('Tap Prime for entry-ready stocks · TV confirms timing')}"
    return msg


# ═══════════════════════════════════════════════════════════════
# FORMAT: PRIME — New dedicated view
# ═══════════════════════════════════════════════════════════════

def format_prime_stocks(stocks, scan_date=None):
    """
    PRIME ENTRY view — shows only stocks ready to enter today.
    Full detail cards with all signals and probabilities.
    """
    ds = _date_str(scan_date)

    prime = []
    for s in stocks:
        streak = int(s.get('streak', 0))
        sit    = s.get('situation') or assign_situation(s, streak)
        if sit == SITUATION_PRIME:
            prime.append({**s, 'situation': sit})

    if not prime:
        return (
            f"🎯 {_b('Prime Entry — ' + ds)}\n\n"
            f"{_i('No PRIME ENTRY stocks today')}\n\n"
            f"This means:\n"
            f"• No fresh HMA crosses (≤10 days)\n"
            f"• Or all good stocks are overextended\n"
            f"• Or volume not confirming\n\n"
            f"Check {_b('Watch Closely')} for stocks to monitor.\n"
            f"Market may be in consolidation — patience pays."
        )

    msg  = f"🎯 {_b('Prime Entry — ' + ds)}\n"
    msg += f"{_i('Best forward probability setups today')}\n"
    msg += f"{_i('Confirm each on TradingView before entering')}\n"
    msg += SEP_THIN + "\n\n"

    for i, s in enumerate(prime, 1):
        msg += _stock_card(s, rank=i, show_prob=True,
                           show_frozen=False, show_signal=True)

        # Add TV confirmation checklist
        msg += f"   {_b('TV Check:')}\n"
        msg += f"   Regime TREND ✓ · ADX ≥20 ✓ · W.Trend Bull ✓\n\n"

    msg += SEP_THIN + "\n"
    if len(prime) == 1:
        msg += f"1 high-probability setup today · Quality over quantity"
    else:
        msg += (f"{len(prime)} high-probability setups · "
                f"Focus on top 1-2 · Don't overtrade")
    return msg


# ═══════════════════════════════════════════════════════════════
# FORMAT: STOCK LIST (paginated) — Updated sort default
# ═══════════════════════════════════════════════════════════════

def format_stock_list(stocks, start_idx=0, count=5,
                      scan_date=None, include_news=False):
    end  = min(start_idx + count, len(stocks))
    sel  = stocks[start_idx:end]
    cp   = (start_idx // count) + 1
    tp   = max(1, (len(stocks) + count - 1) // count)
    ds   = _date_str(scan_date)

    msg  = f"📊 {_b('Watchlist — ' + ds)}\n"
    msg += f"{_i('Sorted by forward score · Page ' + str(cp) + '/' + str(tp))}\n"
    msg += SEP_THIN + "\n\n"

    for i, s in enumerate(sel, start=start_idx + 1):
        msg += _stock_card(s, rank=i, show_prob=True, show_signal=True)
        if include_news:
            msg += format_news_block(fetch_news_for_symbol(s['symbol']))
        msg += "\n"

    msg += SEP_THIN + "\n"
    msg += f"Page {cp}/{tp}"
    return msg


# ═══════════════════════════════════════════════════════════════
# FORMAT: NEW ENTRIES
# ═══════════════════════════════════════════════════════════════

def format_new_stocks(new_stocks, scan_date=None):
    ds = _date_str(scan_date)

    if not new_stocks:
        return (
            f"🆕 {_b('New entries — ' + ds)}\n\n"
            f"{_i('No new stocks entered today')}\n\n"
            f"All 25 carried over from yesterday — consistency!"
        )

    msg  = f"🆕 {_b('New entries — ' + ds)}\n"
    msg += f"{_i(str(len(new_stocks)) + ' stock(s) entered top 25 today')}\n"
    msg += f"{_i('Fresh signals — check situation before entering')}\n"
    msg += SEP_THIN + "\n\n"

    for i, s in enumerate(new_stocks, 1):
        streak = int(s.get('streak', 0))
        sit    = s.get('situation') or assign_situation(s, streak)
        sm     = SITUATION_META.get(sit, SITUATION_META.get('watch', {}))
        e      = float(s.get('close', 0))
        sl     = float(s.get('sl', e * 0.93))
        t1     = float(s.get('target1', e + (e - sl)))
        t2     = float(s.get('target2', e + 2 * (e - sl)))
        r3     = float(s.get('return_3m_pct', 0))
        sc     = int(round(float(s.get('score', 0))))
        p      = _get_prob(s)

        msg += (f"{_b(str(i) + '.')} {_code(s['symbol'])}  {sc}/10  "
                f"🆕  {sm.get('icon','')} {_i(sm.get('label',''))}\n")
        msg += f"   Entry {_fmt_price(e)} | SL {_fmt_price(sl)}\n"
        msg += f"   T1 {_fmt_price(t1)} | T2 {_fmt_price(t2)} | 3M {_fmt_return(r3)}\n"
        if p["t1"] > 0:
            msg += f"   T1 {p['t1']}% · T2 {p['t2']}%\n"
        sig_line = get_situation_signal_line(s)
        if sig_line:
            msg += f"   {_i(sig_line)}\n"
        msg += "\n"

    msg += SEP_THIN + "\n"
    msg += f"{len(new_stocks)} new stock(s) entered today"
    return msg


# ═══════════════════════════════════════════════════════════════
# FORMAT: EXIT
# ═══════════════════════════════════════════════════════════════

def format_exit_stocks(exit_stocks, scan_date=None):
    ds = _date_str(scan_date)

    if not exit_stocks:
        return (
            f"📉 {_b('Exit watch — ' + ds)}\n\n"
            f"{_i('No stocks exited today')}\n\n"
            f"Yesterday's list intact — momentum holding!"
        )

    msg  = f"📉 {_b('Exit watch — ' + ds)}\n"
    msg += f"{_i('Dropped out — consider booking profits')}\n"
    msg += SEP_THIN + "\n\n"

    for i, s in enumerate(exit_stocks, 1):
        sc  = int(round(float(s.get('score', 0))))
        e   = float(s.get('close', 0))
        r3  = float(s.get('return_3m_pct', 0))

        msg += f"{_b(str(i) + '.')} {_code(s['symbol'])}  was {sc}/10  [Exited]\n"

        if _TRACKER_OK:
            sig = get_signal(s['symbol'])
            if sig and sig.get('entry_price', 0) > 0:
                fe   = sig['entry_price']
                days = sig.get('days_in_list', sig.get('streak', 0))
                t1h  = "T1 was hit ✅" if sig.get('t1_hit_date') else "T1 not hit"
                msg += f"   Was in list {days} days\n"
                msg += f"   Entry {_fmt_price(fe)} → Exit {_fmt_price(e)}\n"
                msg += f"   Final P/L: {_fmt_pl(fe, e)} | {t1h}\n"
            else:
                msg += f"   Last price {_fmt_price(e)} | 3M {_fmt_return(r3)}\n"
        else:
            msg += f"   Last price {_fmt_price(e)} | 3M {_fmt_return(r3)}\n"

        if _TRACKER_OK:
            sig = get_signal(s['symbol'])
            if sig and sig.get('t1_hit_date'):
                msg += f"   {_i('Profit booked — well played')}\n"
            else:
                msg += f"   {_i('Consider tightening stop loss')}\n"
        else:
            msg += f"   {_i('Consider tightening stop loss')}\n"
        msg += "\n"

    msg += SEP_THIN + "\n"
    msg += f"{len(exit_stocks)} stock(s) dropped out today"
    return msg


# ═══════════════════════════════════════════════════════════════
# FORMAT: CAUTION — Updated with situation-aware flags
# ═══════════════════════════════════════════════════════════════

def format_caution_stocks(stocks, scan_date=None):
    ds      = _date_str(scan_date)
    caution = get_caution_stocks(stocks)

    if not caution:
        return (
            f"⚠️ {_b('Caution flags — ' + ds)}\n\n"
            f"{_i('No caution flags — all stocks looking solid!')}"
        )

    msg  = f"⚠️ {_b('Caution & Avoid — ' + ds)}\n"
    msg += f"{_i('These need extra care or should be skipped')}\n"
    msg += SEP_THIN + "\n\n"

    for i, s in enumerate(caution, 1):
        sc       = int(round(float(s.get('score', 0))))
        dl       = float(s.get('delivery_pct', 0))
        e        = float(s.get('close', 0))
        r3       = float(s.get('return_3m_pct', 0))
        sit      = s.get('situation', '')
        dist_pct = float(s.get('dist_pct', 0))
        cross_age = int(s.get('cross_age', 0))
        p        = _get_prob(s)

        # Build reason list
        reasons = []
        if sit == SITUATION_AVOID:
            reasons.append("Avoid — weak signal or distribution")
        elif sit == SITUATION_BOOK:
            reasons.append("Book profits — move is maturing")
        if sc <= 5:
            reasons.append(f"Low score {sc}/10")
        if dl < 40:
            reasons.append(f"Low delivery {dl:.0f}%")
        if r3 > 40:
            reasons.append(f"Overextended ({_fmt_return(r3)})")
        if dist_pct > 15:
            reasons.append(f"{dist_pct:.0f}% above HMA55")
        if cross_age > 30:
            reasons.append(f"Cross {cross_age}d ago — mature")

        sit_icon = SITUATION_META.get(sit, {}).get('icon', '⚠️')
        state_tag = "Avoid" if sit == SITUATION_AVOID else (
            "Book" if sit == SITUATION_BOOK else "Risk")

        msg += (f"{_b(str(i) + '.')} {_code(s['symbol'])}  {sc}/10  "
                f"[{state_tag}] {sit_icon}\n")
        msg += f"   Price {_fmt_price(e)} | 3M {_fmt_return(r3)}\n"

        if p["t1"] > 0:
            msg += f"   T1 prob: {p['t1']}% · SL risk: {p['sl']}%\n"

        msg += f"   ⚠️ {' | '.join(reasons)}\n"

        if sit == SITUATION_AVOID:
            msg += f"   {_i('Skip this trade — below quality threshold')}\n"
        elif sit == SITUATION_BOOK:
            msg += f"   {_i('Consider booking 50-100% profits')}\n"
        elif p["sl"] >= 35:
            msg += f"   {_i('High SL risk — tighten stop or book profits')}\n"
        msg += "\n"

    msg += SEP_THIN + "\n"
    msg += f"{len(caution)} stock(s) need extra caution"
    return msg


# ═══════════════════════════════════════════════════════════════
# FORMAT: STRONG / HOLD AND TRAIL
# ═══════════════════════════════════════════════════════════════

def format_strong_stocks(strong_stocks, scan_date=None):
    ds = _date_str(scan_date)

    if not strong_stocks:
        return (
            f"💰 {_b('Hold & Trail — ' + ds)}\n\n"
            f"{_i('No stocks in top 25 for 5+ days yet')}\n\n"
            f"Building history — check back soon."
        )

    msg  = f"💰 {_b('Hold & Trail — ' + ds)}\n"
    msg += f"{_i('In top 25 for 5+ consecutive days')}\n"
    msg += f"{_i('Sustained momentum — trail your stop loss')}\n"
    msg += SEP_THIN + "\n\n"

    for i, s in enumerate(strong_stocks, 1):
        e   = float(s.get('close', 0))
        sl  = float(s.get('sl', e * 0.93))
        t1  = float(s.get('target1', e + (e - sl)))
        t2  = float(s.get('target2', e + 2 * (e - sl)))
        r3  = float(s.get('return_3m_pct', 0))
        sc  = int(round(float(s.get('score', 0))))
        dy  = s.get('consecutive_days', 0)
        sit = s.get('situation', SITUATION_HOLD)
        sm  = SITUATION_META.get(sit, SITUATION_META.get('hold', {}))

        msg += (f"{_b(str(i) + '.')} {_code(s['symbol'])}  {sc}/10  "
                f"{dy}d streak  💰\n")
        msg += f"   {sm.get('icon','')} {_i(sm.get('label', 'Hold & Trail'))}\n"

        if _TRACKER_OK:
            sig = get_signal(s['symbol'])
            if sig and sig.get('entry_price', 0) > 0:
                fe = sig['entry_price']
                fd = sig.get('entry_date', '?')[:10]
                t1h = sig.get('t1_hit_date')
                msg += (f"   Entry(frozen {fd}) {_fmt_price(fe)} | "
                        f"Now {_fmt_price(e)}\n")
                msg += f"   P/L {_fmt_pl(fe, e)}"
                if t1h:
                    msg += f"  · T1 hit ✅ → SL at entry"
                msg += "\n"

        msg += f"   SL {_fmt_price(sl)} | T1 {_fmt_price(t1)} | T2 {_fmt_price(t2)}\n"

        p = _get_prob(s)
        if p["t1"] > 0:
            msg += f"   T1 {p['t1']}% · T2 {p['t2']}%\n"
        msg += "\n"

    msg += SEP_THIN + "\n"
    msg += f"{len(strong_stocks)} stock(s) with sustained momentum"
    return msg


# ═══════════════════════════════════════════════════════════════
# FORMAT: SUMMARY
# ═══════════════════════════════════════════════════════════════

def format_summary(stocks, scan_date=None, history=None):
    ds = _date_str(scan_date)

    # Count by situation
    sit_counts = {}
    for s in stocks:
        sit = s.get('situation', SITUATION_WATCH)
        sit_counts[sit] = sit_counts.get(sit, 0) + 1

    avg_score = (sum(float(s.get('score', 0)) for s in stocks)
                 / max(len(stocks), 1))

    msg  = f"📊 {_b('Daily summary — ' + ds)}\n"
    msg += SEP_BOLD + "\n"
    msg += (f"Total: {_b(str(len(stocks)))} stocks · "
            f"Avg score: {_b(str(round(avg_score, 1)))}\n")

    if history and len(history) >= 2:
        new_count  = len(get_new_stocks(history))
        exit_count = len(get_exit_stocks(history))
        msg += f"New today: {new_count} · Exited: {exit_count}\n"

    msg += SEP_THIN + "\n"
    msg += f"{_b('Situation breakdown')}\n"
    for sit in SITUATION_ORDER:
        if sit in sit_counts:
            sm = SITUATION_META.get(sit, {})
            msg += (f"{sm.get('icon','')} {sm.get('label', sit.title())}: "
                    f"{sit_counts[sit]} stocks\n")

    prime_count = sit_counts.get(SITUATION_PRIME, 0)
    if prime_count > 0:
        prime_stocks = [s['symbol'] for s in stocks
                        if s.get('situation') == SITUATION_PRIME]
        msg += f"\n🎯 {_b('Prime entry today:')} {', '.join(prime_stocks)}\n"

    msg += SEP_THIN + "\n"
    msg += f"{_b('Top 5 by forward score')}\n"
    top5 = sorted(stocks,
                  key=lambda x: float(x.get('score', 0)),
                  reverse=True)[:5]
    for j, s in enumerate(top5, 1):
        sc  = int(round(float(s.get('score', 0))))
        sit = s.get('situation', '')
        sm  = SITUATION_META.get(sit, {})
        msg += (f"{j}. {_code(s['symbol'])} {sc}/10 "
                f"{sm.get('icon','')}\n")

    if _TRACKER_OK:
        ts = get_tracker_summary()
        if ts.get('avg_t1_prob', 0) > 0:
            msg += SEP_THIN + "\n"
            msg += f"{_b('Probability outlook')}\n"
            msg += (f"Avg T1: {ts['avg_t1_prob']}% · "
                    f"Avg T2: {ts['avg_t2_prob']}% · "
                    f"T1>70%: {_b(str(ts.get('high_prob_count', 0)))} "
                    f"of {ts.get('total_active', 0)}\n")

    return msg


# ═══════════════════════════════════════════════════════════════
# FORMAT: HELP — Updated with /prime and situation explanation
# ═══════════════════════════════════════════════════════════════

def format_help():
    return (
        f"🤖 {_b('NSE Momentum Scanner Bot')}\n\n"
        f"{_b('Situation Views:')}\n"
        f"🎯 /prime — Stocks ready to enter today\n"
        f"📊 /today — Full scan grouped by situation\n"
        f"🆕 /new — New stocks entered today\n"
        f"📉 /exit — Stocks removed today\n"
        f"⚠️ /caution — Caution + avoid signals\n"
        f"💰 /strong — 5+ day streak (hold & trail)\n"
        f"📅 /digest — Last week performance\n"
        f"📖 /guide — How to read the scanner\n\n"
        f"{_b('Situations explained:')}\n"
        f"🎯 Prime — Fresh cross, room to run, accum vol\n"
        f"💰 Hold — In move 5+ days, trail your SL\n"
        f"👀 Watch — Good setup, one signal missing\n"
        f"⚠️ Book — Move mature, protect profits\n"
        f"🚫 Avoid — Weak/bearish, skip today\n\n"
        f"{_b('Navigation:')}\n"
        f"/start — Welcome menu\n"
        f"/list — Flat ranked list\n"
        f"/next /prev — Paginate\n"
        f"/news — Page with headlines\n"
        f"/help — This message\n\n"
        f"{_b('Sort options:')}\n"
        f"Score — By forward probability score\n"
        f"3M — By 3-month return (reference)\n"
        f"Top10 — Top 10 by score\n\n"
        f"{_b('Admin (owner only):')}\n"
        f"/admin — Health check dashboard\n"
        f"/users — Bot user list\n\n"
        f"{_i('Tap buttons to navigate!')}"
    )


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test",    action="store_true")
    parser.add_argument("--history", action="store_true")
    parser.add_argument("--demo",    action="store_true")
    args = parser.parse_args()

    if args.test:
        import pandas as pd
        df = pd.DataFrame({
            'symbol':        ['KAYNES', 'DIXON', 'SYRMA', 'EMCURE',
                              'ASTERDM', 'HONASA'],
            'score':         [9, 8, 7, 5, 4, 3],
            'return_1m_pct': [8.5, 7.1, 4.2, 3.8, -1.2, -2.1],
            'return_2m_pct': [12.4, 11.8, 7.6, 6.9, 2.1, 1.5],
            'return_3m_pct': [21.6, 19.3, 11.4, 13.3, 12.6, 9.5],
            'close':  [5840, 8420, 796, 1590, 688, 307],
            'sl':     [5600, 8060, 757, 1477, 637, 280],
            'target1':[6080, 8780, 838, 1703, 739, 335],
            'target2':[6320, 9140, 879, 1816, 790, 362],
            'delivery_pct': [72.4, 61.2, 55.1, 48.3, 42.1, 38.5],
            'cross_age':    [4, 7, 12, 42, -1, 55],
            'fresh_cross':  [True, True, False, False, False, False],
            'dist_pct':     [3.2, 4.1, 5.8, 18.2, 8.1, 12.4],
            'overextended': [False, False, False, True, False, False],
            'acc_days':     [4, 3, 3, 1, 2, 1],
            'dist_days':    [0, 1, 1, 4, 2, 3],
            'obv_dir':      ['rising', 'rising', 'flat', 'falling',
                             'flat', 'falling'],
            'sector_bias':  [1, 0, 1, 1, 0, 0],
            'streak':       [3, 1, 6, 8, 2, 1],
            'category':     ['uptrend', 'rising', 'rising', 'peak',
                             'safer', 'recovering'],
        })
        save_scan_results(df, date.today())
        print("✅ Test data saved\n")

    if args.demo:
        res = load_scan_results()
        if res:
            import re
            strip = lambda t: re.sub(r'<[^>]+>', '', t)
            print(strip(format_welcome("Jayesh")))
            print("\n" + "=" * 50)
            print(strip(format_today_scan(res['stocks'], res['scan_date'])))
            print("\n" + "=" * 50)
            print(strip(format_prime_stocks(res['stocks'], res['scan_date'])))

    if args.history:
        h = load_history()
        print(f"History: {len(h)} days")
        print(f"New:    {[s['symbol'] for s in get_new_stocks(h)]}")
        print(f"Exit:   {[s['symbol'] for s in get_exit_stocks(h)]}")
        print(f"Strong: {[s['symbol'] for s in get_strong_stocks(h)]}")


if __name__ == "__main__":
    main()
