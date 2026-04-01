"""
nse_smart_buckets.py — Intelligent Stock Categorization
=========================================================
Classifies top 25 stocks into layman-friendly buckets.

Buckets:
    📈 Consistently Rising   — in list 5+ days, all returns positive
    🔝 Close to Peak         — within 95% of 52-week high
    📉 Recovering from Fall  — 1M negative but 3M positive
    🛡️ Safer Bets            — high RR, high delivery, low volatility
    🚀 Clear Uptrend         — fresh HMA cross + MACD + volume buildup
    ⚠️ Handle with Care      — in list but showing risk signals

Usage:
    from nse_smart_buckets import classify_stocks, format_bucketed_message
"""

import os
import json
from datetime import date, datetime
from typing import Optional

try:
    from nse_telegram_handler import (
        load_history, get_stock_streak, load_scan_results,
        _b, _i, _h, _code, _fmt_price, _fmt_return,
        HISTORY_FILE, RESULTS_FILE
    )
except ImportError:
    print("[WARN] nse_telegram_handler not found — using fallback helpers")
    def _h(v): return str(v).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')
    def _b(v): return f"<b>{_h(v)}</b>"
    def _i(v): return f"<i>{_h(v)}</i>"
    def _code(v): return f"<code>{_h(v)}</code>"
    def _fmt_price(p): return f"{int(round(p)):,}"
    def _fmt_return(pct):
        sign = '+' if pct >= 0 else ''
        return f"{sign}{pct:.1f}%"
    def load_history(): return []
    def get_stock_streak(sym, hist): return 0
    def load_scan_results(): return None

_TRACKER_OK = False
try:
    from nse_signal_tracker import (
        get_signal, calculate_probability, set_category
    )
    _TRACKER_OK = True
except ImportError:
    def get_signal(s): return None
    def calculate_probability(**kw): return {"t1_pct": 0, "t2_pct": 0, "sl_pct": 0}
    def set_category(s, c): pass


BUCKET_RISING    = "consistently_rising"
BUCKET_PEAK      = "close_to_peak"
BUCKET_RECOVERY  = "recovering"
BUCKET_SAFE      = "safer_bets"
BUCKET_UPTREND   = "clear_uptrend"
BUCKET_CAUTION   = "handle_with_care"
BUCKET_OTHER     = "other"

BUCKET_META = {
    BUCKET_RISING: {
        "emoji":   "\U0001F4C8",
        "label":   "Consistently Rising",
        "tagline": "Strong momentum over weeks \u2014 riding the trend",
        "tip":     "These stocks have stayed in the top 25 for 5+ days with positive returns across all timeframes. Trend is your friend.",
    },
    BUCKET_UPTREND: {
        "emoji":   "\U0001F680",
        "label":   "Clear Uptrend Confirmed",
        "tagline": "Fresh breakout with volume + indicator confirmation",
        "tip":     "Technical signals just aligned \u2014 HMA crossover, MACD bullish, volume surging. Early entry opportunity.",
    },
    BUCKET_PEAK: {
        "emoji":   "\U0001F51D",
        "label":   "Close to Their Peak",
        "tagline": "Trading near 52-week high \u2014 institutional demand",
        "tip":     "Stocks near their annual high often have strong institutional backing. Watch for breakout above the high.",
    },
    BUCKET_RECOVERY: {
        "emoji":   "\U0001F4C9",
        "label":   "Recovering from a Fall",
        "tagline": "Was down, now turning around \u2014 bounce-back play",
        "tip":     "Short-term dip but long-term trend intact. RSI turning up from oversold. Could be a buy-the-dip opportunity.",
    },
    BUCKET_SAFE: {
        "emoji":   "\U0001F6E1\ufe0f",
        "label":   "Safer Bets with Good Reward",
        "tagline": "Tight stop-loss, high delivery \u2014 less risky setups",
        "tip":     "These have a favorable risk/reward ratio and high delivery %. Good for conservative traders.",
    },
    BUCKET_CAUTION: {
        "emoji":   "\u26A0\ufe0f",
        "label":   "Handle with Care",
        "tagline": "Still in list but showing early risk signals",
        "tip":     "These stocks qualify technically but have caution flags. Trade with tight stops.",
    },
    BUCKET_OTHER: {
        "emoji":   "\U0001F4CB",
        "label":   "Other Signals",
        "tagline": "Qualified stocks not fitting a specific pattern",
        "tip":     "These passed all filters but do not strongly fit any category above.",
    },
}


def _is_consistently_rising(stock, streak):
    if streak < 5:
        return False
    r1m = float(stock.get('return_1m_pct', 0))
    r3m = float(stock.get('return_3m_pct', 0))
    return r1m > 0 and r3m > 0


def _is_clear_uptrend(stock):
    score = float(stock.get('score', 0))
    return score >= 8


def _is_close_to_peak(stock, w52_data=None):
    close = float(stock.get('close', 0))
    if w52_data and stock['symbol'] in w52_data:
        w52_high = w52_data[stock['symbol']]
        if w52_high and w52_high > 0:
            return close >= (0.90 * w52_high)
    r3m = float(stock.get('return_3m_pct', 0))
    return r3m >= 20


def _is_recovering(stock):
    r1m = float(stock.get('return_1m_pct', 0))
    r3m = float(stock.get('return_3m_pct', 0))
    if r1m < 0 and r3m > 0:
        return True
    if r3m > 5 and r1m < (r3m * 0.3):
        return True
    return False


def _is_safer_bet(stock):
    delivery = float(stock.get('delivery_pct', 0))
    score    = float(stock.get('score', 0))
    close    = float(stock.get('close', 0))
    sl       = float(stock.get('sl', 0))
    if close <= 0 or sl <= 0:
        return False
    sl_distance_pct = abs(close - sl) / close * 100
    return delivery >= 55 and score >= 6 and sl_distance_pct <= 8


def _is_caution(stock, streak):
    score = float(stock.get('score', 0))
    r1m   = float(stock.get('return_1m_pct', 0))
    r3m   = float(stock.get('return_3m_pct', 0))
    if score <= 5:
        return True
    if streak <= 2 and r1m < 0:
        return True
    if r3m > 40:
        return True
    return False


def classify_stocks(stocks, history=None, w52_data=None):
    if history is None:
        history = load_history()

    buckets = {
        BUCKET_RISING: [], BUCKET_UPTREND: [], BUCKET_PEAK: [],
        BUCKET_RECOVERY: [], BUCKET_SAFE: [], BUCKET_CAUTION: [],
        BUCKET_OTHER: [],
    }

    stock_buckets  = {}
    primary_bucket = {}

    for stock in stocks:
        symbol  = stock['symbol']
        streak  = get_stock_streak(symbol, history) if history else 0
        stock['_streak'] = streak
        matched = []

        if _is_consistently_rising(stock, streak):
            matched.append(BUCKET_RISING)
            buckets[BUCKET_RISING].append(stock)
        if _is_clear_uptrend(stock):
            matched.append(BUCKET_UPTREND)
            buckets[BUCKET_UPTREND].append(stock)
        if _is_close_to_peak(stock, w52_data):
            matched.append(BUCKET_PEAK)
            buckets[BUCKET_PEAK].append(stock)
        if _is_recovering(stock):
            matched.append(BUCKET_RECOVERY)
            buckets[BUCKET_RECOVERY].append(stock)
        if _is_safer_bet(stock):
            matched.append(BUCKET_SAFE)
            buckets[BUCKET_SAFE].append(stock)
        if _is_caution(stock, streak):
            matched.append(BUCKET_CAUTION)
            buckets[BUCKET_CAUTION].append(stock)
        if not matched:
            matched.append(BUCKET_OTHER)
            buckets[BUCKET_OTHER].append(stock)

        stock_buckets[symbol]  = matched
        primary_bucket[symbol] = matched[0]

        if _TRACKER_OK:
            category_label = BUCKET_META.get(matched[0], {}).get("label", "")
            set_category(symbol, category_label)

    summary = {"total": len(stocks)}
    for bname in buckets:
        summary[bname] = len(buckets[bname])

    return {
        "buckets":        buckets,
        "stock_buckets":  stock_buckets,
        "primary_bucket": primary_bucket,
        "summary":        summary,
    }


def format_bucketed_message(classification, scan_date=None, compact=False):
    try:
        dt       = datetime.strptime(scan_date or '', '%Y-%m-%d')
        date_str = dt.strftime('%d-%b-%Y')
    except Exception:
        date_str = scan_date or 'Today'

    buckets = classification["buckets"]
    summary = classification["summary"]

    msg  = f"\U0001F4CA {_b('NSE DAILY SCAN ' + chr(8212) + ' ' + date_str)}\n"
    msg += f"{_i(str(summary['total']) + ' stocks scanned and categorized')}\n"
    msg += "\u2501" * 28 + "\n\n"

    msg += f"{_b('Quick Summary')}\n"

    bucket_order = [
        BUCKET_RISING, BUCKET_UPTREND, BUCKET_PEAK,
        BUCKET_RECOVERY, BUCKET_SAFE, BUCKET_CAUTION
    ]

    for bname in bucket_order:
        count = summary.get(bname, 0)
        if count == 0:
            continue
        meta = BUCKET_META[bname]
        msg += f"  {meta['emoji']} {meta['label']}: {_b(str(count))}\n"

    other_count = summary.get(BUCKET_OTHER, 0)
    if other_count:
        msg += f"  \U0001F4CB Other: {_b(str(other_count))}\n"

    msg += "\n"

    if compact:
        msg += f"{_i('Tap a category button below for details')}"
        return msg

    for bname in bucket_order:
        stocks = buckets.get(bname, [])
        if not stocks:
            continue
        meta = BUCKET_META[bname]
        msg += f"{meta['emoji']} {_b(meta['label'])}\n"
        msg += f"{_i(meta['tagline'])}\n"

        stocks_sorted = sorted(
            stocks,
            key=lambda x: float(x.get('return_3m_pct', 0)),
            reverse=True
        )

        for stock in stocks_sorted:
            sym    = stock['symbol']
            close  = float(stock.get('close', 0))
            r1m    = float(stock.get('return_1m_pct', 0))
            r3m    = float(stock.get('return_3m_pct', 0))
            score  = int(round(float(stock.get('score', 0))))
            streak = stock.get('_streak', 0)
            streak_badge = f" {streak}d" if streak >= 5 else ""

            msg += (
                f"  {_code(sym)}  \u20b9{_fmt_price(close)}  "
                f"{score}/10  "
                f"1M {_fmt_return(r1m)}  3M {_fmt_return(r3m)}"
                f"{streak_badge}\n"
            )
        msg += "\n"

    other_stocks = buckets.get(BUCKET_OTHER, [])
    if other_stocks:
        msg += f"\U0001F4CB {_b('Other Signals')}\n"
        names = [s['symbol'] for s in other_stocks]
        msg += f"  {', '.join(names)}\n\n"

    msg += "\u2501" * 28 + "\n"
    msg += f"{_i('Tap a stock for details / Tap category for tips')}"
    return msg


def format_bucket_detail(bucket_name, classification, scan_date=None):
    try:
        dt       = datetime.strptime(scan_date or '', '%Y-%m-%d')
        date_str = dt.strftime('%d-%b-%Y')
    except Exception:
        date_str = scan_date or 'Today'

    meta   = BUCKET_META.get(bucket_name, BUCKET_META[BUCKET_OTHER])
    stocks = classification["buckets"].get(bucket_name, [])

    if not stocks:
        return (
            f"{meta['emoji']} {_b(meta['label'])} \u2014 {date_str}\n\n"
            f"{_i('No stocks in this category today')}"
        )

    msg  = f"{meta['emoji']} {_b(meta['label'])} \u2014 {date_str}\n"
    msg += f"{_i(meta['tagline'])}\n"
    msg += "\u2501" * 28 + "\n\n"

    stocks_sorted = sorted(
        stocks,
        key=lambda x: float(x.get('return_3m_pct', 0)),
        reverse=True
    )

    for i, stock in enumerate(stocks_sorted, 1):
        sym    = stock['symbol']
        entry  = float(stock.get('close',   0))
        sl     = float(stock.get('sl',      round(entry * 0.93, 2)))
        t1     = float(stock.get('target1', round(entry + (entry - sl), 2)))
        t2     = float(stock.get('target2', round(entry + 2*(entry - sl), 2)))
        r1m    = float(stock.get('return_1m_pct', 0))
        r3m    = float(stock.get('return_3m_pct', 0))
        score  = int(round(float(stock.get('score', 0))))
        streak = stock.get('_streak', 0)

        sig = get_signal(sym) if _TRACKER_OK else None
        if sig:
            t1_prob = sig.get("t1_prob", 0)
            t2_prob = sig.get("t2_prob", 0)
        else:
            prob = calculate_probability(score=score, streak=streak,
                                         category=meta.get("label", ""))
            t1_prob = prob["t1_pct"]
            t2_prob = prob["t2_pct"]

        streak_txt = f"  {streak}d" if streak >= 3 else ""

        msg += (
            f"{_b(str(i) + '.')}  {_code(sym)}  {score}/10{streak_txt}\n"
            f"   Entry \u20b9{_fmt_price(entry)} \u2192 "
            f"SL \u20b9{_fmt_price(sl)} | "
            f"T1 \u20b9{_fmt_price(t1)} | T2 \u20b9{_fmt_price(t2)}\n"
            f"   1M {_fmt_return(r1m)}  |  3M {_fmt_return(r3m)}\n"
            f"   T1 {t1_prob}% | T2 {t2_prob}%\n\n"
        )

    msg += "\u2501" * 28 + "\n"
    msg += f"{_i(meta['tip'])}"
    return msg


def format_quick_dashboard(classification, scan_date=None):
    try:
        dt       = datetime.strptime(scan_date or '', '%Y-%m-%d')
        date_str = dt.strftime('%d-%b-%Y')
    except Exception:
        date_str = scan_date or 'Today'

    buckets = classification["buckets"]

    msg  = f"\u2600\ufe0f {_b('Good morning! NSE Scan ' + chr(8212) + ' ' + date_str)}\n"
    msg += f"{_i('Top 25 stocks, categorized:')}\n\n"

    bucket_order = [
        BUCKET_RISING, BUCKET_UPTREND, BUCKET_PEAK,
        BUCKET_RECOVERY, BUCKET_SAFE, BUCKET_CAUTION
    ]

    for bname in bucket_order:
        stocks = buckets.get(bname, [])
        if not stocks:
            continue
        meta = BUCKET_META[bname]
        top_names = sorted(
            stocks,
            key=lambda x: float(x.get('return_3m_pct', 0)),
            reverse=True
        )[:3]
        names_str = ", ".join(s['symbol'] for s in top_names)
        extra     = f" +{len(stocks)-3} more" if len(stocks) > 3 else ""
        msg += f"{meta['emoji']} {_b(meta['label'])}\n"
        msg += f"   {names_str}{extra}\n\n"

    msg += f"\U0001F447 {_i('Tap a category below for entry/SL/targets')}"
    return msg


def classify_current_scan(w52_data=None):
    results = load_scan_results()
    if not results or not results.get('stocks'):
        return None, None
    stocks    = results['stocks']
    scan_date = results.get('scan_date', str(date.today()))
    history   = load_history()
    classification = classify_stocks(stocks, history, w52_data)
    return classification, scan_date


if __name__ == "__main__":
    print("=" * 55)
    print("  nse_smart_buckets.py — Classification Test")
    print("=" * 55)
    classification, scan_date = classify_current_scan()
    if classification is None:
        print("\n  No scan data found. Run nse_output.py --test first.")
    else:
        print(f"\n  Scan date: {scan_date}")
        print(f"  Total stocks: {classification['summary']['total']}")
        for bname, stocks in classification['buckets'].items():
            if stocks:
                meta = BUCKET_META[bname]
                names = [s['symbol'] for s in stocks]
                print(f"  {meta['emoji']} {meta['label']} ({len(stocks)}): "
                      f"{', '.join(names)}")
    print("=" * 55)
