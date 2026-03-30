"""
nse_telegram_handler.py — Telegram Bot Handler (v3 Layman)
==========================================================
INSTRUCTION: DELETE your entire existing nse_telegram_handler.py
             Replace with this complete file

Parse mode: HTML
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

# ── Category config ───────────────────────────────────────────

CATEGORY_META = {
    "rising":     {"icon": "📈", "label": "Consistently Rising",
                   "desc": "Steady upward momentum over 1-3 months"},
    "uptrend":    {"icon": "🚀", "label": "Clear Uptrend Confirmed",
                   "desc": "Technical breakout confirmed with volume"},
    "peak":       {"icon": "🔝", "label": "Close to Their Peak",
                   "desc": "Near 52-week highs — strong demand"},
    "recovering": {"icon": "📉", "label": "Recovering from a Fall",
                   "desc": "Bouncing back — early recovery signal"},
    "safer":      {"icon": "🛡️", "label": "Safer Bets with Good Reward",
                   "desc": "Lower risk, consistent returns"},
}

CATEGORY_ORDER = ["uptrend", "rising", "peak", "safer", "recovering"]


# ── HTML helpers ──────────────────────────────────────────────

def _h(v):
    return str(v).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')

def _b(v):    return f"<b>{_h(v)}</b>"
def _i(v):    return f"<i>{_h(v)}</i>"
def _code(v): return f"<code>{_h(v)}</code>"

def _fmt_price(p):
    return f"₹{int(round(float(p))):,}"

def _fmt_return(pct):
    pct = float(pct)
    sign = '+' if pct >= 0 else ''
    return f"{sign}{pct:.1f}%"


# ══════════════════════════════════════════════════════════════
# SAVE / LOAD
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
        t2    = round(float(row.get('target2', entry + 2*(entry - sl))), 2)

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

    print(f"✅ Scan results saved: {RESULTS_FILE}  ({len(stocks_list)} stocks)")
    save_history(stocks_list, scan_date)


def load_scan_results():
    if not os.path.exists(RESULTS_FILE):
        return None
    with open(RESULTS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


# ══════════════════════════════════════════════════════════════
# HISTORY — 30 days rolling
# ══════════════════════════════════════════════════════════════

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
    print(f"✅ History saved: {HISTORY_FILE}  ({len(history)} days)")


def load_history():
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f).get('history', [])
    except Exception:
        return []


# ══════════════════════════════════════════════════════════════
# HISTORY ANALYSIS
# ══════════════════════════════════════════════════════════════

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
        if symbol in day['symbols']: n += 1
        else: break
    return n


# ══════════════════════════════════════════════════════════════
# SORTING
# ══════════════════════════════════════════════════════════════

def sort_stocks(stocks, mode='3m'):
    if mode == 'score':
        return sorted(stocks, key=lambda x: float(x.get('score',0)), reverse=True)
    elif mode == 'top10':
        return sorted(stocks, key=lambda x: float(x.get('return_3m_pct',0)), reverse=True)[:10]
    return sorted(stocks, key=lambda x: float(x.get('return_3m_pct',0)), reverse=True)


# ══════════════════════════════════════════════════════════════
# STOCK CARD
# ══════════════════════════════════════════════════════════════

def _stock_card(stock, rank=0, show_cat=False):
    e  = float(stock.get('close', 0))
    sl = float(stock.get('sl', e*0.93))
    t1 = float(stock.get('target1', e+(e-sl)))
    t2 = float(stock.get('target2', e+2*(e-sl)))
    r3 = float(stock.get('return_3m_pct', 0))
    sc = int(round(float(stock.get('score', 0))))
    st = int(stock.get('streak', 0))
    prefix = f"{_b(str(rank)+'.')} " if rank else ""
    stag = f" 🔥{st}d" if st >= 5 else ""
    msg = (f"{prefix}{_code(stock['symbol'])}  {sc}/10{stag}\n"
           f"   Entry {_fmt_price(e)} | SL {_fmt_price(sl)}\n"
           f"   T1 {_fmt_price(t1)} | T2 {_fmt_price(t2)} | "
           f"3M {_fmt_return(r3)}\n")
    if show_cat:
        cat = stock.get('category', 'rising')
        m = CATEGORY_META.get(cat, CATEGORY_META['rising'])
        msg += f"   {m['icon']} {_i(m['label'])}\n"
    return msg


# ══════════════════════════════════════════════════════════════
# NEWS
# ══════════════════════════════════════════════════════════════

def fetch_news_for_symbol(symbol, max_items=3):
    try:
        import requests
        from xml.etree import ElementTree as ET
        url = f"https://news.google.com/rss/search?q={symbol}+NSE+stock+India&hl=en-IN&gl=IN&ceid=IN:en"
        r = requests.get(url, timeout=6, headers={'User-Agent': 'Mozilla/5.0'})
        if r.status_code != 200: return []
        root = ET.fromstring(r.content)
        news = []
        for item in root.findall('.//item')[:max_items]:
            title = item.findtext('title','').split(' - ')[0].strip()
            pub = item.findtext('pubDate','')
            try:
                pub_fmt = datetime.strptime(pub[:16], '%a, %d %b %Y').strftime('%d-%b')
            except Exception:
                pub_fmt = pub[:10]
            news.append({'title': title, 'date': pub_fmt})
        return news
    except Exception:
        return []

def format_news_block(news):
    if not news: return "   <i>No recent news</i>\n"
    return "".join(f"   📰 {_h(n['title'][:80])} <i>({_h(n['date'])})</i>\n" for n in news)


# ══════════════════════════════════════════════════════════════
# MESSAGE FORMATTERS — ALL VIEWS
# ══════════════════════════════════════════════════════════════

def _date_str(scan_date):
    try:
        return datetime.strptime(scan_date or '', '%Y-%m-%d').strftime('%d-%b-%Y')
    except Exception:
        return scan_date or 'Today'


def format_today_scan(stocks, scan_date=None):
    ds = _date_str(scan_date)
    msg = f"📊 {_b('NSE Daily Scan — ' + ds)}\n"
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
    msg += " | ".join(parts) + "\n" + "─"*34 + "\n\n"

    rank = 1
    for k in CATEGORY_ORDER:
        if k not in cats: continue
        m = CATEGORY_META[k]
        msg += f"{m['icon']} {_b(m['label'])} ({len(cats[k])})\n"
        msg += f"   {_i(m['desc'])}\n\n"
        for s in cats[k]:
            msg += _stock_card(s, rank=rank) + "\n"
            rank += 1

    msg += "─"*34 + "\n💡 Tap a view below to explore"
    return msg


def format_stock_list(stocks, start_idx=0, count=5, scan_date=None, include_news=False):
    end = min(start_idx + count, len(stocks))
    sel = stocks[start_idx:end]
    cp  = (start_idx // count) + 1
    tp  = max(1, (len(stocks) + count - 1) // count)
    ds  = _date_str(scan_date)

    msg = f"📊 {_b('WATCHLIST — ' + ds)}\n{_i('Sorted by 3M Return')}\n" + "─"*34 + "\n\n"
    for i, s in enumerate(sel, start=start_idx+1):
        msg += _stock_card(s, rank=i, show_cat=True)
        if include_news:
            msg += format_news_block(fetch_news_for_symbol(s['symbol']))
        msg += "\n"
    msg += f"📄 Page {cp}/{tp}"
    return msg


def format_new_stocks(new_stocks, scan_date=None):
    ds = _date_str(scan_date)
    if not new_stocks:
        return (f"🆕 {_b('NEW ENTRIES — '+ds)}\n\n"
                f"{_i('No new stocks entered today')}\n\n"
                "All 25 carried over from yesterday — consistency!")
    msg = (f"🆕 {_b('NEW ENTRIES — '+ds)}\n"
           f"{_i(str(len(new_stocks))+' stock(s) entered top 25 today')}\n"
           f"{_i('Fresh signals — consider for new positions')}\n" + "─"*34 + "\n\n")
    for i, s in enumerate(new_stocks, 1):
        msg += _stock_card(s, rank=i, show_cat=True) + "\n"
    msg += f"💡 {len(new_stocks)} new stock(s) entered today"
    return msg


def format_exit_stocks(exit_stocks, scan_date=None):
    ds = _date_str(scan_date)
    if not exit_stocks:
        return (f"📉 {_b('EXIT WATCH — '+ds)}\n\n"
                f"{_i('No stocks exited today')}\n\n"
                "Yesterday's full list intact — momentum holding!")
    msg = (f"📉 {_b('EXIT WATCH — '+ds)}\n"
           f"{_i('Dropped out — consider booking profits')}\n" + "─"*34 + "\n\n")
    for i, s in enumerate(exit_stocks, 1):
        r3 = float(s.get('return_3m_pct', 0))
        sc = int(round(float(s.get('score', 0))))
        e  = float(s.get('close', 0))
        cat = s.get('category', 'rising')
        m = CATEGORY_META.get(cat, CATEGORY_META['rising'])
        msg += (f"{_b(str(i)+'.')}  {_code(s['symbol'])}  {sc}/10\n"
                f"   Last price {_fmt_price(e)} | 3M {_fmt_return(r3)}\n"
                f"   Was: {m['icon']} {_i(m['label'])}\n"
                f"   {_i('Consider tightening stop loss')}\n\n")
    msg += f"⚠️ {len(exit_stocks)} stock(s) dropped out today"
    return msg


def format_caution_stocks(stocks, scan_date=None):
    ds = _date_str(scan_date)
    caution = get_caution_stocks(stocks)
    if not caution:
        return (f"⚠️ {_b('CAUTION FLAGS — '+ds)}\n\n"
                f"{_i('No caution flags — all stocks looking solid!')}")
    msg = (f"⚠️ {_b('CAUTION FLAGS — '+ds)}\n"
           f"{_i('Weaker signals — trade carefully')}\n" + "─"*34 + "\n\n")
    for i, s in enumerate(caution, 1):
        sc = int(round(float(s.get('score', 0))))
        dl = float(s.get('delivery_pct', 0))
        e  = float(s.get('close', 0))
        reasons = []
        if sc <= 5: reasons.append("Score at lower end")
        if dl < 40: reasons.append(f"Low delivery {dl:.0f}%")
        msg += (f"{_b(str(i)+'.')}  {_code(s['symbol'])}  {sc}/10\n"
                f"   Price {_fmt_price(e)}\n"
                f"   ⚠️ {' | '.join(reasons)}\n\n")
    msg += f"⚠️ {len(caution)} stock(s) need extra caution"
    return msg


def format_strong_stocks(strong_stocks, scan_date=None):
    ds = _date_str(scan_date)
    if not strong_stocks:
        return (f"🔥 {_b('STRONG PICKS — '+ds)}\n\n"
                f"{_i('No stocks in top 25 for 5+ days yet')}\n\n"
                "Building history — check back soon.")
    msg = (f"🔥 {_b('STRONG PICKS — '+ds)}\n"
           f"{_i('In top 25 for 5+ consecutive days')}\n"
           f"{_i('Sustained momentum = strongest conviction')}\n" + "─"*34 + "\n\n")
    for i, s in enumerate(strong_stocks, 1):
        e  = float(s.get('close', 0))
        sl = float(s.get('sl', e*0.93))
        t1 = float(s.get('target1', e+(e-sl)))
        t2 = float(s.get('target2', e+2*(e-sl)))
        r3 = float(s.get('return_3m_pct', 0))
        sc = int(round(float(s.get('score', 0))))
        dy = s.get('consecutive_days', 0)
        cat = s.get('category', 'rising')
        m = CATEGORY_META.get(cat, CATEGORY_META['rising'])
        msg += (f"{_b(str(i)+'.')}  {_code(s['symbol'])}  {sc}/10  🔥{dy} days\n"
                f"   {m['icon']} {_i(m['label'])}\n"
                f"   Entry {_fmt_price(e)} | SL {_fmt_price(sl)}\n"
                f"   T1 {_fmt_price(t1)} | T2 {_fmt_price(t2)} | 3M {_fmt_return(r3)}\n\n")
    msg += f"🔥 {len(strong_stocks)} stock(s) with sustained momentum"
    return msg


def format_welcome(user_name=None):
    name = f" {user_name}" if user_name else ""
    return (
        f"👋 {_b('Hello' + name + '! Welcome to NSE Scanner Daily.')}\n\n"
        "Here is what I can show you:\n\n"
        + f"📊 {_b('Todays Scan')} — Top 25 bucketed by signal\n"
        + f"🆕 {_b('New Entries')} — Stocks added today\n"
        + f"📉 {_b('Exit Watch')} — Stocks removed today\n"
        + f"⚠️ {_b('Caution Flags')} — Weaker signals\n"
        + f"🔥 {_b('Strong Picks')} — 5+ day streak\n\n"
        "💡 Tap a button below!"
    )

def format_help():
    return (
        f"🤖 {_b('NSE Momentum Scanner Bot')}\n\n"
        f"{_b('Views:')}\n"
        "📊 /today — Bucketed daily scan\n"
        "🆕 /new — New entries today\n"
        "📉 /exit — Exit signals\n"
        "⚠️ /caution — Caution flags\n"
        "🔥 /strong — Strong picks (5+ days)\n\n"
        f"{_b('Navigation:')}\n"
        "/start — Welcome menu\n"
        "/list — Flat ranked list\n"
        "/next /prev — Paginate\n"
        "/news — Page with headlines\n"
        "/help — This message\n\n"
        f"{_b('Categories:')}\n"
        "📈 Rising — all returns positive\n"
        "🚀 Uptrend — breakout confirmed\n"
        "🔝 Near Peak — close to 52W high\n"
        "🛡️ Safer — high delivery, good RR\n"
        "📉 Recovering — bouncing back\n\n"
        "💡 Tap buttons to navigate!")


# ── CLI ───────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test",    action="store_true")
    parser.add_argument("--history", action="store_true")
    parser.add_argument("--demo",    action="store_true")
    args = parser.parse_args()

    if args.test:
        import pandas as pd
        cats = (["rising"]*5 + ["uptrend"]*3 + ["peak"]*5 +
                ["safer"]*5 + ["recovering"]*4 + ["rising"]*3)
        df = pd.DataFrame({
            'symbol':        [f'STOCK{i:02d}' for i in range(1, 26)],
            'score':         [9 - i*0.15 for i in range(25)],
            'return_1m_pct': [15 - i*0.3 for i in range(25)],
            'return_2m_pct': [25 - i*0.4 for i in range(25)],
            'return_3m_pct': [30 - i*1.0 for i in range(25)],
            'close':  [1000+i*50 for i in range(25)],
            'volume': [1000000   for _ in range(25)],
            'delivery_pct': [40+i*1.5 for i in range(25)],
            'sl':      [950+i*47  for i in range(25)],
            'target1': [1050+i*53 for i in range(25)],
            'target2': [1100+i*56 for i in range(25)],
            'category': cats[:25],
            'streak':  [12-i//2   for i in range(25)],
        })
        save_scan_results(df, date.today())
        print("✅ Test data saved\n")

    if args.demo:
        res = load_scan_results()
        if res:
            stocks = res['stocks']
            print("\n" + "="*50)
            print(format_welcome("Jayesh"))
            print("\n" + "="*50)
            print(format_today_scan(stocks, res['scan_date']))
            print("\n" + "="*50)
            print(format_help())

    if args.history:
        h = load_history()
        print(f"History: {len(h)} days")
        print(f"New:    {[s['symbol'] for s in get_new_stocks(h)]}")
        print(f"Exit:   {[s['symbol'] for s in get_exit_stocks(h)]}")
        print(f"Strong: {[s['symbol'] for s in get_strong_stocks(h)]}")


if __name__ == "__main__":
    main()
