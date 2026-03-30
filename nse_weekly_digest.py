"""
nse_weekly_digest.py — Weekly Performance Digest
==================================================
Sends a Saturday summary showing how the week's picks performed.

Features:
    1. Week's Top Performers — which picks moved most
    2. Hit Rate — how many stocks moved in the right direction
    3. SL Hits — which stocks breached stop-loss
    4. Target Hits — which stocks reached T1/T2
    5. New vs Exited — churn summary for the week
    6. Consistency Champions — stocks in list all 5 days
    7. Week-over-Week comparison

Data source: scan_history.json (already stores 30 days of data)
Price source: SQLite database (daily_prices table)

Usage:
    # Manual run
    python nse_weekly_digest.py
    
    # Dry run (print only, don't send Telegram)
    python nse_weekly_digest.py --dry-run
    
    # Specific week ending date
    python nse_weekly_digest.py --week-ending 28-03-2026

Integration:
    Add to crontab or Task Scheduler for Saturday 10 AM IST:
    python nse_weekly_digest.py

    OR call from nse_daily_runner.py on Saturdays:
    from nse_weekly_digest import generate_weekly_digest
    generate_weekly_digest()
"""

import os
import sys
import json
import sqlite3
import argparse
import requests
import logging
from datetime import date, datetime, timedelta
from pathlib import Path

try:
    import config
except ImportError:
    print("ERROR: config.py not found")
    sys.exit(1)

try:
    from nse_telegram_handler import (
        load_history, HISTORY_FILE,
        _b, _i, _h, _code, _fmt_price, _fmt_return
    )
except ImportError:
    print("ERROR: nse_telegram_handler.py not found")
    sys.exit(1)

# ── Logging ───────────────────────────────────────────────────
os.makedirs(config.LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[
        logging.FileHandler(
            os.path.join(config.LOG_DIR, "weekly_digest.log"), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════
# DATA COLLECTION
# ══════════════════════════════════════════════════════════════

def get_week_dates(week_ending: date = None) -> list:
    """
    Get trading dates for the week ending on the given date.
    Returns list of dates (Mon-Fri), most recent first.
    """
    if week_ending is None:
        week_ending = date.today()
    
    # Walk back to find Friday (or last trading day)
    d = week_ending
    while d.weekday() >= 5:  # skip weekends
        d -= timedelta(days=1)
    
    friday = d
    monday = friday - timedelta(days=friday.weekday())  # back to Monday
    
    dates = []
    current = monday
    while current <= friday:
        if current.weekday() < 5:  # Mon-Fri only
            dates.append(current)
        current += timedelta(days=1)
    
    return dates


def get_week_history(history: list, week_dates: list) -> list:
    """
    Filter history to just this week's entries.
    Returns list of history entries for the week, latest first.
    """
    week_strs = {str(d) for d in week_dates}
    week_hist = [h for h in history if h['date'] in week_strs]
    week_hist.sort(key=lambda x: x['date'], reverse=True)
    return week_hist


def get_price_at_date(symbol: str, target_date: date,
                      conn: sqlite3.Connection) -> float:
    """Get closing price for a symbol on a specific date from DB."""
    row = conn.execute(
        "SELECT close FROM daily_prices WHERE symbol=? AND date=? LIMIT 1",
        [symbol, target_date.isoformat()]
    ).fetchone()
    return float(row[0]) if row else 0.0


def get_week_prices(symbols: list, week_dates: list,
                    conn: sqlite3.Connection) -> dict:
    """
    Get Monday open and Friday close for each symbol.
    Also gets high/low for the week to check SL/target hits.
    
    Returns: {
        symbol: {
            'monday_close': float,
            'friday_close': float,
            'week_high': float,
            'week_low': float,
            'week_return_pct': float,
        }
    }
    """
    if not week_dates:
        return {}
    
    start_date = min(week_dates)
    end_date   = max(week_dates)
    
    results = {}
    
    for symbol in symbols:
        rows = conn.execute("""
            SELECT date, open, high, low, close
            FROM daily_prices
            WHERE symbol = ? AND date >= ? AND date <= ?
            ORDER BY date
        """, [symbol, start_date.isoformat(), end_date.isoformat()]).fetchall()
        
        if not rows:
            continue
        
        monday_close = float(rows[0][4])   # first day's close
        friday_close = float(rows[-1][4])   # last day's close
        week_high    = max(float(r[2]) for r in rows)
        week_low     = min(float(r[3]) for r in rows)
        
        week_return  = 0.0
        if monday_close > 0:
            week_return = (friday_close - monday_close) / monday_close * 100
        
        results[symbol] = {
            'monday_close':    monday_close,
            'friday_close':    friday_close,
            'week_high':       week_high,
            'week_low':        week_low,
            'week_return_pct': round(week_return, 1),
        }
    
    return results


# ══════════════════════════════════════════════════════════════
# ANALYSIS
# ══════════════════════════════════════════════════════════════

def analyze_week(week_history: list, week_prices: dict) -> dict:
    """
    Full week analysis.
    
    Returns dict with all digest sections:
        top_performers, worst_performers, hit_rate,
        sl_hits, target_hits, consistency, churn, stats
    """
    if not week_history:
        return {"empty": True, "reason": "No scan history for this week"}
    
    # ── All unique symbols seen this week ──
    all_symbols = set()
    for day in week_history:
        all_symbols.update(day.get('symbols', []))
    
    # ── Symbols in Monday's list (start of week) ──
    monday_entry  = week_history[-1] if week_history else {}
    monday_stocks = {s['symbol']: s for s in monday_entry.get('stocks', [])}
    monday_syms   = set(monday_stocks.keys())
    
    # ── Symbols in Friday's list (end of week) ──
    friday_entry  = week_history[0] if week_history else {}
    friday_stocks = {s['symbol']: s for s in friday_entry.get('stocks', [])}
    friday_syms   = set(friday_stocks.keys())
    
    # ── Performance of Monday's picks ──
    performers = []
    sl_hits    = []
    t1_hits    = []
    t2_hits    = []
    
    for symbol, stock_data in monday_stocks.items():
        if symbol not in week_prices:
            continue
        
        wp    = week_prices[symbol]
        entry = float(stock_data.get('close', 0))
        sl    = float(stock_data.get('sl', entry * 0.93))
        t1    = float(stock_data.get('target1', entry * 1.07))
        t2    = float(stock_data.get('target2', entry * 1.14))
        
        performers.append({
            'symbol':          symbol,
            'entry':           entry,
            'friday_close':    wp['friday_close'],
            'week_return_pct': wp['week_return_pct'],
            'week_high':       wp['week_high'],
            'week_low':        wp['week_low'],
            'sl':              sl,
            'target1':         t1,
            'target2':         t2,
            'score':           float(stock_data.get('score', 0)),
        })
        
        # Check SL hit
        if wp['week_low'] <= sl:
            sl_hits.append({
                'symbol':   symbol,
                'sl':       sl,
                'week_low': wp['week_low'],
                'entry':    entry,
            })
        
        # Check target hits
        if wp['week_high'] >= t1:
            t1_hits.append({
                'symbol':    symbol,
                'target1':   t1,
                'week_high': wp['week_high'],
                'entry':     entry,
            })
        
        if wp['week_high'] >= t2:
            t2_hits.append({
                'symbol':    symbol,
                'target2':   t2,
                'week_high': wp['week_high'],
                'entry':     entry,
            })
    
    # Sort performers
    performers.sort(key=lambda x: x['week_return_pct'], reverse=True)
    
    # ── Hit rate ──
    total_tracked = len(performers)
    winners       = sum(1 for p in performers if p['week_return_pct'] > 0)
    losers        = sum(1 for p in performers if p['week_return_pct'] < 0)
    flat          = total_tracked - winners - losers
    hit_rate      = round(winners / total_tracked * 100, 1) if total_tracked else 0
    
    avg_winner = 0.0
    avg_loser  = 0.0
    if winners:
        avg_winner = round(
            sum(p['week_return_pct'] for p in performers if p['week_return_pct'] > 0) / winners, 1)
    if losers:
        avg_loser = round(
            sum(p['week_return_pct'] for p in performers if p['week_return_pct'] < 0) / losers, 1)
    
    # ── Consistency — stocks in list all week ──
    consistency = []
    days_count  = len(week_history)
    
    for symbol in all_symbols:
        days_in = sum(1 for day in week_history if symbol in day.get('symbols', []))
        if days_in == days_count and days_count >= 3:
            stock_data = friday_stocks.get(symbol, monday_stocks.get(symbol, {}))
            wp_data    = week_prices.get(symbol, {})
            consistency.append({
                'symbol':          symbol,
                'days':            days_in,
                'week_return_pct': wp_data.get('week_return_pct', 0),
                'score':           float(stock_data.get('score', 0)),
            })
    
    consistency.sort(key=lambda x: x['week_return_pct'], reverse=True)
    
    # ── Churn ──
    new_this_week   = friday_syms - monday_syms
    exited_this_week = monday_syms - friday_syms
    stayed          = monday_syms & friday_syms
    
    return {
        "empty":           False,
        "trading_days":    days_count,
        "total_tracked":   total_tracked,
        "top_performers":  performers[:5],
        "worst_performers": performers[-3:] if len(performers) >= 3 else [],
        "hit_rate":        hit_rate,
        "winners":         winners,
        "losers":          losers,
        "flat":            flat,
        "avg_winner":      avg_winner,
        "avg_loser":       avg_loser,
        "sl_hits":         sl_hits,
        "t1_hits":         t1_hits,
        "t2_hits":         t2_hits,
        "consistency":     consistency,
        "new_this_week":   list(new_this_week),
        "exited_this_week": list(exited_this_week),
        "stayed":          len(stayed),
        "churn_pct":       round(len(new_this_week) / max(len(monday_syms), 1) * 100, 1),
    }


# ══════════════════════════════════════════════════════════════
# MESSAGE FORMATTING
# ══════════════════════════════════════════════════════════════

def format_weekly_digest(analysis: dict, week_dates: list) -> str:
    """Format the weekly digest as HTML for Telegram."""
    
    if analysis.get("empty"):
        return (
            f"📅 {_b('Weekly Digest')}\n\n"
            f"{_i(analysis.get('reason', 'No data available for this week'))}\n\n"
            f"History builds automatically — check back next Saturday."
        )
    
    start_str = min(week_dates).strftime('%d-%b')
    end_str   = max(week_dates).strftime('%d-%b-%Y')
    
    msg  = f"📅 {_b('WEEKLY DIGEST — ' + start_str + ' to ' + end_str)}\n"
    msg += f"{_i('How did this week\\'s picks perform?')}\n"
    msg += "━" * 32 + "\n\n"
    
    # ── Scorecard ──
    msg += f"🎯 {_b('SCORECARD')}\n"
    msg += (
        f"   Tracked: {analysis['total_tracked']} stocks  |  "
        f"Trading days: {analysis['trading_days']}\n"
        f"   ✅ Winners: {analysis['winners']}  "
        f"({_fmt_return(analysis['avg_winner'])} avg)\n"
        f"   ❌ Losers: {analysis['losers']}  "
        f"({_fmt_return(analysis['avg_loser'])} avg)\n"
        f"   ➖ Flat: {analysis['flat']}\n"
        f"   📊 Hit Rate: {_b(str(analysis['hit_rate']) + '%')}\n\n"
    )
    
    # ── Top 5 Performers ──
    top = analysis.get('top_performers', [])
    if top:
        msg += f"🏆 {_b('TOP PERFORMERS THIS WEEK')}\n"
        for i, p in enumerate(top, 1):
            ret = p['week_return_pct']
            emoji = "🟢" if ret > 0 else "🔴"
            msg += (
                f"   {emoji} {_code(p['symbol'])}  "
                f"₹{_fmt_price(p['entry'])} → ₹{_fmt_price(p['friday_close'])}  "
                f"({_fmt_return(ret)})\n"
            )
        msg += "\n"
    
    # ── Worst 3 ──
    worst = analysis.get('worst_performers', [])
    worst_actual = [w for w in worst if w['week_return_pct'] < 0]
    if worst_actual:
        msg += f"📉 {_b('UNDERPERFORMERS')}\n"
        for p in worst_actual:
            msg += (
                f"   🔴 {_code(p['symbol'])}  "
                f"₹{_fmt_price(p['entry'])} → ₹{_fmt_price(p['friday_close'])}  "
                f"({_fmt_return(p['week_return_pct'])})\n"
            )
        msg += "\n"
    
    # ── Target Hits ──
    t1_hits = analysis.get('t1_hits', [])
    t2_hits = analysis.get('t2_hits', [])
    
    if t1_hits or t2_hits:
        msg += f"🎯 {_b('TARGET HITS')}\n"
        
        for t in t2_hits:
            msg += (
                f"   🎯🎯 {_code(t['symbol'])} hit T2 "
                f"₹{_fmt_price(t['target2'])}  "
                f"(high: ₹{_fmt_price(t['week_high'])})\n"
            )
        
        # T1 hits that didn't also hit T2
        t2_syms = {t['symbol'] for t in t2_hits}
        for t in t1_hits:
            if t['symbol'] not in t2_syms:
                msg += (
                    f"   🎯 {_code(t['symbol'])} hit T1 "
                    f"₹{_fmt_price(t['target1'])}  "
                    f"(high: ₹{_fmt_price(t['week_high'])})\n"
                )
        msg += "\n"
    
    # ── SL Hits ──
    sl_hits = analysis.get('sl_hits', [])
    if sl_hits:
        msg += f"🛑 {_b('STOP-LOSS BREACHED')}\n"
        for s in sl_hits:
            msg += (
                f"   ⚠️ {_code(s['symbol'])}  "
                f"SL ₹{_fmt_price(s['sl'])} hit  "
                f"(low: ₹{_fmt_price(s['week_low'])})\n"
            )
        msg += "\n"
    
    # ── Consistency Champions ──
    champs = analysis.get('consistency', [])
    if champs:
        msg += f"🔥 {_b('ALL WEEK CHAMPIONS')}\n"
        msg += f"{_i('In top 25 every single day this week')}\n"
        for c in champs[:7]:
            emoji = "🟢" if c['week_return_pct'] > 0 else "🔴"
            msg += (
                f"   {emoji} {_code(c['symbol'])}  "
                f"{c['score']:.0f}/10  "
                f"Week: {_fmt_return(c['week_return_pct'])}\n"
            )
        msg += "\n"
    
    # ── Churn ──
    msg += f"🔄 {_b('LIST CHURN')}\n"
    msg += (
        f"   Stayed all week: {analysis['stayed']}\n"
        f"   New entries: {len(analysis['new_this_week'])}\n"
        f"   Exited: {len(analysis['exited_this_week'])}\n"
        f"   Churn rate: {analysis['churn_pct']}%\n\n"
    )
    
    if analysis['new_this_week']:
        msg += f"   🆕 New: {', '.join(analysis['new_this_week'][:8])}\n"
    if analysis['exited_this_week']:
        msg += f"   👋 Exited: {', '.join(analysis['exited_this_week'][:8])}\n"
    
    msg += "\n━" * 32 + "\n"
    msg += f"📅 {_i('Next digest: Next Saturday')}"
    
    return msg


# ══════════════════════════════════════════════════════════════
# SEND TO TELEGRAM
# ══════════════════════════════════════════════════════════════

def send_telegram_message(text: str) -> bool:
    """Send HTML message to Telegram."""
    token   = getattr(config, 'TELEGRAM_TOKEN', '')
    chat_id = getattr(config, 'TELEGRAM_CHATID', '')
    
    if not token or not chat_id:
        log.warning("Telegram not configured")
        return False
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    
    try:
        r = requests.post(url, data={
            'chat_id':    chat_id,
            'text':       text,
            'parse_mode': 'HTML',
        }, timeout=10)
        
        if r.status_code == 200:
            return True
        
        log.error(f"Telegram error: {r.status_code} — {r.text[:200]}")
        
        # Retry without HTML
        r2 = requests.post(url, data={
            'chat_id': chat_id,
            'text':    text.replace('<b>', '').replace('</b>', '')
                          .replace('<i>', '').replace('</i>', '')
                          .replace('<code>', '').replace('</code>', ''),
        }, timeout=10)
        return r2.status_code == 200
    
    except Exception as e:
        log.error(f"Telegram send failed: {e}")
        return False


# ══════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ══════════════════════════════════════════════════════════════

def generate_weekly_digest(week_ending: date = None,
                           dry_run: bool = False) -> bool:
    """
    Generate and send the weekly digest.
    
    Args:
        week_ending : date the week ends (default: today/last Friday)
        dry_run     : if True, print message but don't send
    
    Returns:
        True if successful
    """
    print(f"\n{'='*55}")
    print(f"  NSE WEEKLY DIGEST")
    print(f"{'='*55}")
    
    # ── Get week dates ──
    week_dates = get_week_dates(week_ending)
    if not week_dates:
        print("  No trading dates found for this week")
        return False
    
    print(f"  Week: {min(week_dates).strftime('%d-%b')} to "
          f"{max(week_dates).strftime('%d-%b-%Y')}")
    print(f"  Trading days: {len(week_dates)}")
    
    # ── Load history ──
    history      = load_history()
    week_history = get_week_history(history, week_dates)
    
    print(f"  History entries for this week: {len(week_history)}")
    
    if not week_history:
        print("  No scan history for this week — digest cannot be generated")
        print("  History builds automatically as daily scans run")
        return False
    
    # ── Get prices from DB ──
    all_symbols = set()
    for day in week_history:
        all_symbols.update(day.get('symbols', []))
    
    week_prices = {}
    try:
        conn        = sqlite3.connect(config.DB_PATH)
        week_prices = get_week_prices(list(all_symbols), week_dates, conn)
        conn.close()
        print(f"  Price data found for: {len(week_prices)} symbols")
    except Exception as e:
        log.warning(f"Could not load prices from DB: {e}")
        print(f"  ⚠️ DB price lookup failed: {e}")
        print(f"  Digest will show history data only")
    
    # ── Analyze ──
    analysis = analyze_week(week_history, week_prices)
    
    if analysis.get("empty"):
        print(f"  {analysis.get('reason')}")
        return False
    
    # ── Format message ──
    message = format_weekly_digest(analysis, week_dates)
    
    # ── Print / Send ──
    if dry_run:
        print(f"\n{'─'*55}")
        print("  DRY RUN — Message preview:")
        print(f"{'─'*55}\n")
        import re
        plain = re.sub(r'<[^>]+>', '', message)
        print(plain)
    else:
        print(f"\n  Sending to Telegram...")
        ok = send_telegram_message(message)
        print(f"  {'✅ Sent!' if ok else '❌ Failed'}")
    
    # ── Save digest to output ──
    try:
        digest_path = os.path.join(
            config.OUTPUT_DIR,
            f"weekly_digest_{max(week_dates).strftime('%Y%m%d')}.json"
        )
        os.makedirs(config.OUTPUT_DIR, exist_ok=True)
        with open(digest_path, 'w', encoding='utf-8') as f:
            json.dump(analysis, f, indent=2, default=str)
        print(f"  Digest saved: {digest_path}")
    except Exception as e:
        log.warning(f"Could not save digest JSON: {e}")
    
    print(f"{'='*55}\n")
    return True


# ══════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="NSE Weekly Performance Digest",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python nse_weekly_digest.py                     # generate + send
  python nse_weekly_digest.py --dry-run           # preview only
  python nse_weekly_digest.py --week-ending 28-03-2026
        """
    )
    
    parser.add_argument("--dry-run", action="store_true",
                        help="Print message but don't send to Telegram")
    parser.add_argument("--week-ending", type=str,
                        help="Week ending date DD-MM-YYYY (default: today)")
    
    args = parser.parse_args()
    
    week_ending = None
    if args.week_ending:
        for fmt in ["%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"]:
            try:
                week_ending = datetime.strptime(args.week_ending, fmt).date()
                break
            except ValueError:
                pass
    
    generate_weekly_digest(week_ending=week_ending, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
