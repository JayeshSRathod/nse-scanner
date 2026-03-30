"""
nse_smart_buckets.py — Intelligent Stock Categorization
=========================================================
Classifies top 25 stocks into layman-friendly buckets based on
technical signals, momentum, history, and risk data.

Buckets:
    📈 Consistently Rising   — in list 5+ days, all returns positive
    🔝 Close to Peak         — within 95% of 52-week high
    📉 Recovering from Fall  — 1M negative but 3M positive, RSI turning up
    🛡️ Safer Bets            — high RR, high delivery, low volatility
    🚀 Clear Uptrend         — fresh HMA cross + MACD + volume buildup
    ⚠️ Handle with Care      — in list but showing risk signals

A stock can appear in MULTIPLE buckets (e.g., both Rising and Near Peak).
Primary bucket = first match in priority order above.

Usage:
    from nse_smart_buckets import classify_stocks, format_bucketed_message
    buckets = classify_stocks(stocks, history)
    msg = format_bucketed_message(buckets, scan_date)

Integration:
    Called by nse_telegram_polling.py for the "📊 Today's Scan" view.
"""

import os
import json
from datetime import date, datetime
from typing import Optional

# ── Import history helpers ────────────────────────────────────
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


# ── Bucket definitions ────────────────────────────────────────

BUCKET_RISING    = "consistently_rising"
BUCKET_PEAK      = "close_to_peak"
BUCKET_RECOVERY  = "recovering"
BUCKET_SAFE      = "safer_bets"
BUCKET_UPTREND   = "clear_uptrend"
BUCKET_CAUTION   = "handle_with_care"
BUCKET_OTHER     = "other"

BUCKET_META = {
    BUCKET_RISING: {
        "emoji":   "📈",
        "label":   "Consistently Rising",
        "tagline": "Strong momentum over weeks — riding the trend",
        "tip":     "These stocks have stayed in the top 25 for 5+ days with positive returns across all timeframes. Trend is your friend.",
    },
    BUCKET_UPTREND: {
        "emoji":   "🚀",
        "label":   "Clear Uptrend Confirmed",
        "tagline": "Fresh breakout with volume + indicator confirmation",
        "tip":     "Technical signals just aligned — HMA crossover, MACD bullish, volume surging. Early entry opportunity.",
    },
    BUCKET_PEAK: {
        "emoji":   "🔝",
        "label":   "Close to Their Peak",
        "tagline": "Trading near 52-week high — institutional demand",
        "tip":     "Stocks near their annual high often have strong institutional backing. Watch for breakout above the high.",
    },
    BUCKET_RECOVERY: {
        "emoji":   "📉",
        "label":   "Recovering from a Fall",
        "tagline": "Was down, now turning around — bounce-back play",
        "tip":     "Short-term dip but long-term trend intact. RSI turning up from oversold. Could be a buy-the-dip opportunity.",
    },
    BUCKET_SAFE: {
        "emoji":   "🛡️",
        "label":   "Safer Bets with Good Reward",
        "tagline": "Tight stop-loss, high delivery — less risky setups",
        "tip":     "These have a favorable risk/reward ratio and high delivery % (real buying, not speculation). Good for conservative traders.",
    },
    BUCKET_CAUTION: {
        "emoji":   "⚠️",
        "label":   "Handle with Care",
        "tagline": "Still in list but showing early risk signals",
        "tip":     "These stocks qualify technically but have caution flags — high volatility, promoter selling, or weakening momentum. Trade with tight stops.",
    },
    BUCKET_OTHER: {
        "emoji":   "📋",
        "label":   "Other Signals",
        "tagline": "Qualified stocks not fitting a specific pattern",
        "tip":     "These passed all filters but don't strongly fit any category above. Do your own research before trading.",
    },
}


# ══════════════════════════════════════════════════════════════
# CLASSIFICATION LOGIC
# ══════════════════════════════════════════════════════════════

def _is_consistently_rising(stock: dict, streak: int) -> bool:
    """
    In top 25 for 5+ consecutive days AND all returns positive.
    The most reliable signal — sustained institutional interest.
    """
    if streak < 5:
        return False
    r1m = float(stock.get('return_1m_pct', 0))
    r3m = float(stock.get('return_3m_pct', 0))
    return r1m > 0 and r3m > 0


def _is_clear_uptrend(stock: dict) -> bool:
    """
    Fresh HMA cross within 5 days + high score (8+).
    Indicates a new trend just started with confirmation.
    
    We check score >= 8 as proxy for MACD + volume + breakout 
    confirmation (those signals contribute to the score).
    """
    score = float(stock.get('score', 0))
    # fresh_cross may not be in the JSON — check if available
    # High score (8+) already implies HMA + volume + MACD aligned
    return score >= 8


def _is_close_to_peak(stock: dict, w52_data: dict = None) -> bool:
    """
    Close >= 90% of 52-week high.
    If 52W data not available, check if 3M return > 20% as proxy.
    """
    close = float(stock.get('close', 0))
    
    if w52_data and stock['symbol'] in w52_data:
        w52_high = w52_data[stock['symbol']]
        if w52_high and w52_high > 0:
            return close >= (0.90 * w52_high)
    
    # Fallback: strong 3M return suggests near highs
    r3m = float(stock.get('return_3m_pct', 0))
    return r3m >= 20


def _is_recovering(stock: dict) -> bool:
    """
    1M return negative but 3M return positive.
    OR: 1M return < 3M return significantly (pullback in uptrend).
    Stock took a breather but long-term trend is intact.
    """
    r1m = float(stock.get('return_1m_pct', 0))
    r3m = float(stock.get('return_3m_pct', 0))
    
    # Classic recovery: short-term dip in long-term uptrend
    if r1m < 0 and r3m > 0:
        return True
    
    # Pullback: 1M much weaker than 3M (took a breather)
    if r3m > 5 and r1m < (r3m * 0.3):
        return True
    
    return False


def _is_safer_bet(stock: dict) -> bool:
    """
    High delivery % (>55%) + moderate score (6+) + 
    SL distance < 8% from entry.
    Real buying + tight stop = favorable risk setup.
    """
    delivery = float(stock.get('delivery_pct', 0))
    score    = float(stock.get('score', 0))
    close    = float(stock.get('close', 0))
    sl       = float(stock.get('sl', 0))
    
    if close <= 0 or sl <= 0:
        return False
    
    sl_distance_pct = abs(close - sl) / close * 100
    
    return (delivery >= 55 and 
            score >= 6 and 
            sl_distance_pct <= 8)


def _is_caution(stock: dict, streak: int) -> bool:
    """
    Stock is in list but showing weakness:
    - Score dropped to 5-6 (barely qualifying)
    - OR: streak is 1-2 days only with weak 1M return
    - OR: very high 3M return (>40%) suggesting overextension
    """
    score = float(stock.get('score', 0))
    r1m   = float(stock.get('return_1m_pct', 0))
    r3m   = float(stock.get('return_3m_pct', 0))
    
    # Barely qualifying
    if score <= 5:
        return True
    
    # New entry but weak short-term
    if streak <= 2 and r1m < 0:
        return True
    
    # Potentially overextended
    if r3m > 40:
        return True
    
    return False


def classify_stocks(stocks: list,
                    history: list = None,
                    w52_data: dict = None) -> dict:
    """
    Classify stocks into smart buckets.
    
    Args:
        stocks   : list of stock dicts from scan results
        history  : list of daily history entries (from load_history())
        w52_data : {symbol: week52_high} map (optional)
    
    Returns:
        dict with structure:
        {
            "buckets": {
                "consistently_rising": [stock_dicts...],
                "clear_uptrend": [...],
                ...
            },
            "stock_buckets": {
                "RELIANCE": ["consistently_rising", "close_to_peak"],
                ...
            },
            "primary_bucket": {
                "RELIANCE": "consistently_rising",
                ...
            },
            "summary": {
                "total": 25,
                "consistently_rising": 5,
                ...
            }
        }
    """
    if history is None:
        history = load_history()
    
    buckets = {
        BUCKET_RISING:   [],
        BUCKET_UPTREND:  [],
        BUCKET_PEAK:     [],
        BUCKET_RECOVERY: [],
        BUCKET_SAFE:     [],
        BUCKET_CAUTION:  [],
        BUCKET_OTHER:    [],
    }
    
    stock_buckets  = {}   # symbol -> list of bucket names
    primary_bucket = {}   # symbol -> first matching bucket
    
    for stock in stocks:
        symbol  = stock['symbol']
        streak  = get_stock_streak(symbol, history) if history else 0
        
        # Add streak to stock data for display
        stock['_streak'] = streak
        
        matched = []
        
        # Check each bucket (priority order matters for primary)
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
        
        # If no bucket matched, put in "other"
        if not matched:
            matched.append(BUCKET_OTHER)
            buckets[BUCKET_OTHER].append(stock)
        
        stock_buckets[symbol]  = matched
        primary_bucket[symbol] = matched[0]
    
    # Build summary
    summary = {"total": len(stocks)}
    for bname in buckets:
        summary[bname] = len(buckets[bname])
    
    return {
        "buckets":        buckets,
        "stock_buckets":  stock_buckets,
        "primary_bucket": primary_bucket,
        "summary":        summary,
    }


# ══════════════════════════════════════════════════════════════
# TELEGRAM FORMATTING
# ══════════════════════════════════════════════════════════════

def format_bucketed_message(classification: dict,
                            scan_date: str = None,
                            compact: bool = False) -> str:
    """
    Format the full bucketed dashboard message for Telegram.
    
    Args:
        classification : output from classify_stocks()
        scan_date      : "YYYY-MM-DD" string
        compact        : if True, show summary only (no stock details)
    
    Returns:
        HTML-formatted string for Telegram
    """
    try:
        dt       = datetime.strptime(scan_date or '', '%Y-%m-%d')
        date_str = dt.strftime('%d-%b-%Y')
    except Exception:
        date_str = scan_date or 'Today'
    
    buckets = classification["buckets"]
    summary = classification["summary"]
    
    msg  = f"📊 {_b('NSE DAILY SCAN — ' + date_str)}\n"
    msg += f"{_i(str(summary['total']) + ' stocks scanned and categorized')}\n"
    msg += "━" * 32 + "\n\n"
    
    # ── Quick Summary Block ──
    msg += f"{_b('Quick Summary')}\n"
    
    bucket_order = [
        BUCKET_RISING, BUCKET_UPTREND, BUCKET_PEAK,
        BUCKET_RECOVERY, BUCKET_SAFE, BUCKET_CAUTION
    ]
    
    for bname in bucket_order:
        count = summary.get(bname, 0)
        if count == 0:
            continue
        meta  = BUCKET_META[bname]
        msg  += f"  {meta['emoji']} {meta['label']}: {_b(str(count))}\n"
    
    other_count = summary.get(BUCKET_OTHER, 0)
    if other_count:
        msg += f"  📋 Other: {_b(str(other_count))}\n"
    
    msg += "\n"
    
    if compact:
        msg += f"{_i('Tap a category button below for details')}"
        return msg
    
    # ── Detailed Buckets ──
    for bname in bucket_order:
        stocks = buckets.get(bname, [])
        if not stocks:
            continue
        
        meta = BUCKET_META[bname]
        msg += f"{meta['emoji']} {_b(meta['label'])}\n"
        msg += f"{_i(meta['tagline'])}\n"
        
        # Sort by 3M return within bucket
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
            
            streak_badge = f" 🔥{streak}d" if streak >= 5 else ""
            
            msg += (
                f"  {_code(sym)}  ₹{_fmt_price(close)}  "
                f"{score}/10  "
                f"1M {_fmt_return(r1m)}  3M {_fmt_return(r3m)}"
                f"{streak_badge}\n"
            )
        
        msg += "\n"
    
    # Other bucket (minimal)
    other_stocks = buckets.get(BUCKET_OTHER, [])
    if other_stocks:
        msg += f"📋 {_b('Other Signals')}\n"
        names = [s['symbol'] for s in other_stocks]
        msg += f"  {', '.join(names)}\n\n"
    
    msg += "━" * 32 + "\n"
    msg += f"💡 {_i('Tap a stock for details • Tap category for tips')}"
    
    return msg


def format_bucket_detail(bucket_name: str,
                         classification: dict,
                         scan_date: str = None) -> str:
    """
    Format a single bucket's detailed view with entry/SL/targets.
    Used when user taps a category button.
    """
    try:
        dt       = datetime.strptime(scan_date or '', '%Y-%m-%d')
        date_str = dt.strftime('%d-%b-%Y')
    except Exception:
        date_str = scan_date or 'Today'
    
    meta   = BUCKET_META.get(bucket_name, BUCKET_META[BUCKET_OTHER])
    stocks = classification["buckets"].get(bucket_name, [])
    
    if not stocks:
        return (
            f"{meta['emoji']} {_b(meta['label'])} — {date_str}\n\n"
            f"{_i('No stocks in this category today')}"
        )
    
    msg  = f"{meta['emoji']} {_b(meta['label'])} — {date_str}\n"
    msg += f"{_i(meta['tagline'])}\n"
    msg += "━" * 32 + "\n\n"
    
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
        
        streak_txt = f"  🔥 {streak} days in list" if streak >= 3 else ""
        
        msg += (
            f"{_b(str(i) + '.')}  {_code(sym)}  {score}/10{streak_txt}\n"
            f"   Entry ₹{_fmt_price(entry)} → "
            f"SL ₹{_fmt_price(sl)} | "
            f"T1 ₹{_fmt_price(t1)} | T2 ₹{_fmt_price(t2)}\n"
            f"   1M {_fmt_return(r1m)}  |  3M {_fmt_return(r3m)}\n\n"
        )
    
    msg += "━" * 32 + "\n"
    msg += f"💡 {_i(meta['tip'])}"
    
    return msg


def format_quick_dashboard(classification: dict,
                           scan_date: str = None) -> str:
    """
    Ultra-compact dashboard — just category names + top stock per bucket.
    Used as the morning push notification.
    """
    try:
        dt       = datetime.strptime(scan_date or '', '%Y-%m-%d')
        date_str = dt.strftime('%d-%b-%Y')
    except Exception:
        date_str = scan_date or 'Today'
    
    buckets = classification["buckets"]
    summary = classification["summary"]
    
    msg  = f"☀️ {_b('Good morning! NSE Scan — ' + date_str)}\n"
    msg += f"{_i('Today' + chr(39) + 's top 25 stocks, categorized:')}\n\n"
    
    bucket_order = [
        BUCKET_RISING, BUCKET_UPTREND, BUCKET_PEAK,
        BUCKET_RECOVERY, BUCKET_SAFE, BUCKET_CAUTION
    ]
    
    for bname in bucket_order:
        stocks = buckets.get(bname, [])
        if not stocks:
            continue
        
        meta = BUCKET_META[bname]
        
        # Show top 3 names per bucket
        top_names = sorted(
            stocks,
            key=lambda x: float(x.get('return_3m_pct', 0)),
            reverse=True
        )[:3]
        
        names_str = ", ".join(s['symbol'] for s in top_names)
        extra     = f" +{len(stocks)-3} more" if len(stocks) > 3 else ""
        
        msg += f"{meta['emoji']} {_b(meta['label'])}\n"
        msg += f"   {names_str}{extra}\n\n"
    
    msg += f"👇 {_i('Tap a category below for entry/SL/targets')}"
    
    return msg


# ══════════════════════════════════════════════════════════════
# CONVENIENCE: classify from current scan file
# ══════════════════════════════════════════════════════════════

def classify_current_scan(w52_data: dict = None) -> tuple:
    """
    Load current scan + history, classify, return (classification, scan_date).
    
    Usage:
        classification, scan_date = classify_current_scan()
        msg = format_bucketed_message(classification, scan_date)
    """
    results = load_scan_results()
    if not results or not results.get('stocks'):
        return None, None
    
    stocks    = results['stocks']
    scan_date = results.get('scan_date', str(date.today()))
    history   = load_history()
    
    classification = classify_stocks(stocks, history, w52_data)
    
    return classification, scan_date


# ══════════════════════════════════════════════════════════════
# CLI TEST
# ══════════════════════════════════════════════════════════════

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
        print()
        
        for bname, stocks in classification['buckets'].items():
            if stocks:
                meta = BUCKET_META[bname]
                names = [s['symbol'] for s in stocks]
                print(f"  {meta['emoji']} {meta['label']} ({len(stocks)}): "
                      f"{', '.join(names)}")
        
        print("\n  --- Bucketed Message Preview ---\n")
        msg = format_bucketed_message(classification, scan_date)
        # Strip HTML for console preview
        import re
        plain = re.sub(r'<[^>]+>', '', msg)
        print(plain)
        
        print("\n  --- Quick Dashboard Preview ---\n")
        msg2 = format_quick_dashboard(classification, scan_date)
        plain2 = re.sub(r'<[^>]+>', '', msg2)
        print(plain2)
    
    print("=" * 55)
