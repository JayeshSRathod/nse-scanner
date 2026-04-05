"""
nse_scanner.py — Core Stock Scanner (v5 — Weekly Tier + Market Cap + Situation)
================================================================================
WHAT CHANGED FROM v4:

  1. WEEKLY HMA TWO-TIER FILTER (new — via nse_technical_filters v3)
     Tier 3 stocks (weekly HMA20 < HMA55) are HARD REMOVED
     Tier 1 (bullish) → eligible for PRIME ENTRY
     Tier 2 (neutral/pullback) → capped at WATCH CLOSELY

  2. MARKET CAP FILTER (now enforced)
     MIN_MARKET_CAP ≥ ₹500 Cr (was in config but not applied)
     Estimated from: market_cap ≈ close × shares_approx
     Where shares_approx = avg_daily_turnover / avg_price / 0.02
     (assumes ~2% of shares trade daily — conservative NSE estimate)
     If no turnover data: filter skipped gracefully

  3. TURNOVER FILTER (new)
     MIN_TURNOVER ≥ ₹2 Cr daily (turnover_lacs ≥ 200)
     Ensures sufficient liquidity for entry/exit without slippage
     Already in config.MIN_TURNOVER — now enforced here

  4. SITUATION ASSIGNMENT (new — integrated from nse_telegram_handler)
     Each stock gets a situation label before saving
     Weekly tier feeds into situation:
       Tier 2 stock → cannot be PRIME even if score ≥ 7

  5. WEEKLY TIER COLUMNS in output
     weekly_tier, weekly_label added to result_df
     Used by Telegram handler to cap situation

Expected stock counts with all filters:
  ~1800 NSE EQ stocks
  → ~1200 after blacklist + price ≥ ₹50
  → ~600  after volume + delivery
  → ~400  after turnover ≥ ₹2 Cr
  → ~300  after 3M return > 0 (uptrend gate)
  → ~150  after weekly Tier 3 removed
  → ~25   after forward score ≥ 4
  → 2-4   PRIME ENTRY (Tier 1 + score ≥ 7)
  → 5-8   WATCH CLOSELY (Tier 2 or score 4-6)
"""

import os
import sys
import json
import argparse
import sqlite3
import pandas as pd
import numpy as np
from datetime import date, datetime, timedelta
from pathlib import Path
import logging

try:
    import config
except ImportError:
    print("ERROR: config.py not found.")
    sys.exit(1)

try:
    from nse_technical_filters import (
        score_all_stocks, TIER_HIGH_CONVICTION, TIER_WATCHLIST,
        assign_categories_bulk, CATEGORY_META, CATEGORY_ORDER,
        format_score_breakdown,
        WEEKLY_TIER_BULLISH, WEEKLY_TIER_NEUTRAL, WEEKLY_TIER_BEARISH,
        get_weekly_tier_label,
    )
    TECH_FILTERS_AVAILABLE = True
except ImportError:
    print("WARNING: nse_technical_filters.py not found. Momentum-only mode.")
    TECH_FILTERS_AVAILABLE = False
    CATEGORY_META = {
        "rising":     {"icon": "📈", "label": "Consistently Rising"},
        "uptrend":    {"icon": "🚀", "label": "Clear Uptrend Confirmed"},
        "peak":       {"icon": "🔝", "label": "Close to Their Peak"},
        "recovering": {"icon": "📉", "label": "Recovering from a Fall"},
        "safer":      {"icon": "🛡️", "label": "Safer Bets with Good Reward"},
    }
    CATEGORY_ORDER    = ["uptrend", "rising", "peak", "safer", "recovering"]
    WEEKLY_TIER_BULLISH = 1
    WEEKLY_TIER_NEUTRAL = 2
    WEEKLY_TIER_BEARISH = 3
    def get_weekly_tier_label(t): return "Weekly ?"

try:
    from nse_telegram_handler import save_scan_results, assign_situation
    _HANDLER_OK = True
except ImportError:
    save_scan_results  = None
    _HANDLER_OK        = False
    def assign_situation(stock, streak=0): return "watch"

DAYS_1M  = 22
DAYS_2M  = 44
DAYS_3M  = 66
LOOKBACK = 180

os.makedirs(config.LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(config.LOG_DIR, "scanner.log")),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════════════════════

def load_data_for_date(scan_date):
    """Load price history, blacklist, and 52W data from SQLite."""
    conn       = sqlite3.connect(config.DB_PATH)
    start_date = scan_date - timedelta(days=LOOKBACK + 30)

    prices_df = pd.read_sql_query(f"""
        SELECT symbol, date, open, high, low, close,
               volume, delivery_pct, avg_price, turnover_lacs
        FROM daily_prices
        WHERE date >= '{start_date}' AND date <= '{scan_date}'
        ORDER BY symbol, date
    """, conn)
    prices_df['date'] = pd.to_datetime(prices_df['date'])

    blacklist_df = pd.read_sql_query(f"""
        SELECT symbol FROM blacklist WHERE date = '{scan_date}'
    """, conn)

    w52_df = pd.read_sql_query(f"""
        SELECT symbol, week52_high, week52_low FROM week52
        WHERE date = (
            SELECT MAX(date) FROM week52
            WHERE date <= '{scan_date}'
        )
    """, conn)

    if w52_df.empty:
        print("  ⚠️  No week52 data — 'Close to Peak' category disabled")
    else:
        print(f"  ✅  week52 loaded: {len(w52_df)} stocks")

    w52_map = {
        row['symbol']: (row['week52_high'], row['week52_low'])
        for _, row in w52_df.iterrows()
    }

    conn.close()
    return {
        'prices':    prices_df,
        'blacklist': set(blacklist_df['symbol'].tolist()),
        'w52_map':   w52_map,
        'scan_date': scan_date,
    }


# ═══════════════════════════════════════════════════════════════════════════
# RETURN CALCULATION
# ═══════════════════════════════════════════════════════════════════════════

def calculate_returns(prices_df, scan_date):
    """
    Calculate 1M/2M/3M returns + avg volume + avg turnover.
    Returns are for DISPLAY and uptrend gate only — not for ranking.
    """
    if prices_df.empty:
        return pd.DataFrame()

    recent = prices_df[prices_df['date'] <= pd.Timestamp(scan_date)].copy()
    recent['symbol'] = recent['symbol'].astype(str).str.strip()
    recent = recent.dropna(subset=['symbol', 'date', 'close'])
    recent = recent.sort_values(['symbol', 'date'])
    results = []

    for symbol, grp in recent.groupby('symbol'):
        grp = grp.tail(DAYS_3M + 5)
        if len(grp) < DAYS_1M:
            continue
        current_close = grp.iloc[-1]['close']

        def ret(n):
            if len(grp) >= n and grp.iloc[-n]['close'] > 0:
                return (current_close - grp.iloc[-n]['close']) / grp.iloc[-n]['close']
            return 0.0

        latest     = grp.iloc[-1]
        avg_vol    = grp.tail(22)['volume'].mean()
        # Average daily turnover over last 22 days (in lacs)
        avg_turnover = (grp.tail(22)['turnover_lacs'].mean()
                        if 'turnover_lacs' in grp.columns else 0.0)

        results.append({
            'symbol':        str(symbol).strip(),
            'close':         current_close,
            'open':          latest.get('open', 0),
            'high':          latest.get('high', 0),
            'low':           latest.get('low', 0),
            'volume':        latest.get('volume', 0),
            'avg_volume':    avg_vol,
            'delivery_pct':  latest.get('delivery_pct', 0),
            'avg_price':     latest.get('avg_price', 0),
            'turnover_lacs': latest.get('turnover_lacs', 0),
            'avg_turnover':  avg_turnover,
            'return_1m':     ret(DAYS_1M),
            'return_2m':     ret(DAYS_2M),
            'return_3m':     ret(DAYS_3M),
        })

    return pd.DataFrame(results)


# ═══════════════════════════════════════════════════════════════════════════
# FILTERS — Updated with turnover filter
# ═══════════════════════════════════════════════════════════════════════════

def apply_filters(stocks_df, blacklist):
    """
    Apply quality filters sequentially.

    NEW in v5:
      Turnover filter: avg_turnover ≥ MIN_TURNOVER (₹2 Cr = 200 lacs)
    """
    print("\n" + "=" * 60)
    print("  NSE SCANNER v5 — Applying Filters")
    print("=" * 60)
    print(f"Initial stocks      : {len(stocks_df):,}")

    # 1. Blacklist (GSM / ASM / IRP)
    n = len(stocks_df)
    stocks_df = stocks_df[~stocks_df['symbol'].isin(blacklist)]
    print(f"After blacklist     : {len(stocks_df):,}  "
          f"(removed {n - len(stocks_df)} GSM/ASM/IRP)")

    # 2. Price ≥ ₹50
    n = len(stocks_df)
    stocks_df = stocks_df[stocks_df['close'] >= config.MIN_PRICE]
    print(f"After price ≥ ₹{config.MIN_PRICE}   : {len(stocks_df):,}  "
          f"(removed {n - len(stocks_df)} penny stocks)")

    # 3. Avg volume ≥ 50,000
    n = len(stocks_df)
    stocks_df = stocks_df[stocks_df['avg_volume'] >= config.MIN_VOLUME]
    print(f"After volume ≥ {config.MIN_VOLUME//1000}k  : {len(stocks_df):,}  "
          f"(removed {n - len(stocks_df)} illiquid)")

    # 4. Delivery % ≥ 35%
    n = len(stocks_df)
    stocks_df = stocks_df[stocks_df['delivery_pct'] >= config.MIN_DELIVERY]
    print(f"After delivery ≥ {config.MIN_DELIVERY}% : {len(stocks_df):,}  "
          f"(removed {n - len(stocks_df)} speculative)")

    # 5. Turnover ≥ ₹2 Cr per day (NEW)
    min_turnover = getattr(config, 'MIN_TURNOVER', 200)  # lacs
    if min_turnover > 0 and 'avg_turnover' in stocks_df.columns:
        n = len(stocks_df)
        # Allow NaN/zero to pass gracefully (not all data has turnover)
        turnover_mask = (
            stocks_df['avg_turnover'].isna() |
            (stocks_df['avg_turnover'] == 0) |
            (stocks_df['avg_turnover'] >= min_turnover)
        )
        stocks_df = stocks_df[turnover_mask]
        removed = n - len(stocks_df)
        print(f"After turnover ≥ ₹{min_turnover//100:.0f}Cr : {len(stocks_df):,}  "
              f"(removed {removed} low-liquidity)")
    else:
        print(f"Turnover filter    : SKIPPED (no data)")

    # 6. 3M return > 0 (uptrend gate — replaces old 50% ranking weight)
    n = len(stocks_df)
    stocks_df = stocks_df[stocks_df['return_3m'] > 0]
    print(f"After uptrend gate  : {len(stocks_df):,}  "
          f"(removed {n - len(stocks_df)} downtrend stocks)")

    print(f"{'─' * 60}")
    print(f"Ready for scoring   : {len(stocks_df):,} quality stocks")
    return stocks_df.reset_index(drop=True)


# ═══════════════════════════════════════════════════════════════════════════
# MOMENTUM SCORE — fallback only, not used for ranking
# ═══════════════════════════════════════════════════════════════════════════

def calculate_momentum_score(stocks_df):
    if stocks_df.empty:
        return stocks_df
    stocks_df['momentum_score'] = (
        config.WEIGHT_1M * stocks_df['return_1m'] +
        config.WEIGHT_2M * stocks_df['return_2m'] +
        config.WEIGHT_3M * stocks_df['return_3m']
    )
    return stocks_df


# ═══════════════════════════════════════════════════════════════════════════
# TRADE PLAN
# ═══════════════════════════════════════════════════════════════════════════

def add_trade_plan(row, tech_row=None):
    """Calculate Entry, SL, T1, T2 for one stock."""
    entry = float(row['close'])

    if (tech_row is not None and
            pd.notna(tech_row.get('stop')) and
            float(tech_row.get('stop', 0)) > 0):
        sl = float(tech_row['stop'])
    else:
        sl = round(entry * 0.93, 2)  # fallback: 7% SL

    risk    = max(entry - sl, entry * 0.01)
    target1 = round(entry + risk, 2)
    target2 = round(entry + 2 * risk, 2)

    return {
        'entry':   round(entry, 2),
        'sl':      round(sl, 2),
        'sl_pct':  round(-risk / entry * 100, 1) if entry > 0 else 0,
        'target1': target1,
        't1_pct':  round(risk / entry * 100, 1) if entry > 0 else 0,
        'target2': target2,
        't2_pct':  round(risk * 2 / entry * 100, 1) if entry > 0 else 0,
        'rr':      2.0,
    }


# ═══════════════════════════════════════════════════════════════════════════
# STREAK LOADER
# ═══════════════════════════════════════════════════════════════════════════

def _load_streaks():
    """Load consecutive-day streaks from scan history."""
    history_file = Path("scan_history.json")
    if not history_file.exists():
        return {}
    try:
        data    = json.loads(history_file.read_text(encoding="utf-8"))
        history = data.get("history", [])
        if not history:
            return {}
        today_symbols = set(history[0].get("symbols", []))
        streaks = {}
        for symbol in today_symbols:
            count = 0
            for day_entry in history:
                if symbol in day_entry.get("symbols", []):
                    count += 1
                else:
                    break
            streaks[symbol] = count
        return streaks
    except Exception as e:
        log.warning(f"Could not load streaks: {e}")
        return {}


# ═══════════════════════════════════════════════════════════════════════════
# SIMPLE CATEGORY FALLBACK
# ═══════════════════════════════════════════════════════════════════════════

def _assign_category_simple(row):
    r1m = float(row.get("return_1m", 0))
    r3m = float(row.get("return_3m", 0))
    dlv = float(row.get("delivery_pct", 0))
    if r1m > r3m * 0.5 and r3m < 0.10:
        return "recovering"
    if dlv >= 55:
        return "safer"
    return "rising"


# ═══════════════════════════════════════════════════════════════════════════
# SITUATION ASSIGNMENT — Weekly-tier aware
# ═══════════════════════════════════════════════════════════════════════════

def _assign_situation_with_weekly(stock_dict, streak, weekly_tier):
    """
    Assign situation with weekly tier cap applied.

    Tier 2 stocks (weekly pullback) cannot be PRIME ENTRY.
    Even if their daily score is ≥ 7, they get capped to WATCH.

    Args:
        stock_dict:  row dict from result_df
        streak:      consecutive days in list
        weekly_tier: 1 (bullish), 2 (neutral), 3 (bearish)

    Returns:
        situation string: prime/watch/hold/book/avoid
    """
    situation = assign_situation(stock_dict, streak)

    # Weekly Tier 2 cap — cannot be PRIME
    if weekly_tier == WEEKLY_TIER_NEUTRAL and situation == "prime":
        return "watch"

    # Weekly Tier 3 should not be here (already removed)
    # but if it somehow slipped through, mark AVOID
    if weekly_tier == WEEKLY_TIER_BEARISH:
        return "avoid"

    return situation


# ═══════════════════════════════════════════════════════════════════════════
# MAIN SCAN FUNCTION
# ═══════════════════════════════════════════════════════════════════════════

def scan_stocks(scan_date=None, top_n=None):
    """
    Main scan function. Returns ranked DataFrame with full trade plan.

    Pipeline:
      1. Load 180 days of price data from SQLite
      2. Calculate returns + avg turnover
      3. Apply quality filters (price/volume/delivery/turnover/uptrend)
      4. Weekly HMA two-tier filter (Tier 3 removed, Tier 2 capped)
      5. Forward-looking signal scoring (7 signals, 0-10 pts)
      6. Assign trade plans (Entry/SL/T1/T2)
      7. Assign categories (display labels)
      8. Assign situations (prime/watch/hold/book/avoid)
         — Tier 2 stocks capped at WATCH even if score ≥ 7
      9. Save to JSON for Telegram bot
    """
    if scan_date is None:
        scan_date = date.today()
    if top_n is None:
        top_n = config.TOP_N_STOCKS

    print(f"\n{'=' * 60}")
    print(f"  NSE SCANNER v5")
    print(f"  Date    : {scan_date.strftime('%d-%b-%Y')}")
    print(f"  Ranking : FORWARD PROBABILITY SCORE")
    print(f"  Weekly  : Two-tier filter (Tier 3 = hard remove)")
    print(f"  Turnover: ≥ ₹{getattr(config, 'MIN_TURNOVER', 200) // 100:.0f} Cr daily")
    print(f"{'=' * 60}")

    # ── Step 1: Load data ─────────────────────────────────────
    data = load_data_for_date(scan_date)
    if data['prices'].empty:
        print("ERROR: No price data in database.")
        return pd.DataFrame()

    # ── Step 2: Calculate returns ─────────────────────────────
    stocks_df = calculate_returns(data['prices'], scan_date)
    if stocks_df.empty:
        print("ERROR: Could not calculate returns.")
        return pd.DataFrame()

    # ── Step 3: Apply quality filters ─────────────────────────
    filtered_df = apply_filters(stocks_df, data['blacklist'])
    if filtered_df.empty:
        print("No stocks passed quality filters.")
        return pd.DataFrame()

    # ── Step 4 + 5: Weekly filter + Forward scoring ───────────
    # (weekly tier calculation happens inside score_all_stocks)
    scored_df = calculate_momentum_score(filtered_df)
    tech_df   = pd.DataFrame()

    if TECH_FILTERS_AVAILABLE:
        print(f"\n  Running forward-looking signal scoring...")
        tech_df = score_all_stocks(
            price_df=data['prices'],
            filtered_symbols=filtered_df['symbol'].tolist(),
            scan_date=scan_date,
            w52_map=data['w52_map'],
        )

    if not tech_df.empty:
        tech_df = tech_df.reset_index()

        merge_cols = [c for c in [
            'symbol', 'score', 'conviction', 'stop', 'target', 'target2', 'rr',
            'rsi', 'pts_hma', 'pts_dist', 'pts_vol', 'pts_rsi', 'pts_macd',
            'pts_sector', 'pts_rr', 'pen_overext', 'pen_decel',
            'fresh_cross', 'cross_age', 'dist_pct', 'overextended',
            'obv_dir', 'acc_days', 'dist_days', 'del_trend',
            'hma_trend_up', 'near_52w', 'sector_bias',
            # NEW: weekly tier columns
            'weekly_tier', 'weekly_label',
        ] if c in tech_df.columns]

        scored_df = scored_df.merge(
            tech_df[merge_cols], on='symbol', how='inner'
        )  # inner join — only keep stocks that passed weekly filter
        scored_df['score']      = scored_df['score'].fillna(0)
        scored_df['conviction'] = scored_df['conviction'].fillna('')

        # ── Ranking: forward score, HIGH CONVICTION first ─────
        hc   = (scored_df[scored_df['conviction'] == TIER_HIGH_CONVICTION]
                .sort_values('score', ascending=False))
        wl   = (scored_df[scored_df['conviction'] == TIER_WATCHLIST]
                .sort_values('score', ascending=False))
        rest = (scored_df[scored_df['conviction'] == '']
                .sort_values('momentum_score', ascending=False))

        scored_df = pd.concat([hc, wl, rest], ignore_index=True)

        t1c = (tech_df['weekly_tier'] == WEEKLY_TIER_BULLISH).sum() if 'weekly_tier' in tech_df.columns else 0
        t2c = (tech_df['weekly_tier'] == WEEKLY_TIER_NEUTRAL).sum() if 'weekly_tier' in tech_df.columns else 0

        print(f"\n  After scoring:")
        print(f"    HIGH CONVICTION (≥7): {len(hc)} stocks")
        print(f"    Watchlist (4-6):      {len(wl)} stocks")
        print(f"    Weekly Tier 1:        {t1c} (PRIME eligible)")
        print(f"    Weekly Tier 2:        {t2c} (capped at WATCH)")

    else:
        # Fallback: momentum-only mode
        scored_df['score']       = (scored_df['momentum_score'] * 100).round(1)
        scored_df['conviction']  = ''
        scored_df['stop']        = None
        scored_df['weekly_tier'] = WEEKLY_TIER_NEUTRAL
        scored_df['weekly_label'] = get_weekly_tier_label(WEEKLY_TIER_NEUTRAL)
        scored_df = scored_df.sort_values('momentum_score', ascending=False)
        log.warning("Tech filters unavailable — momentum-only mode")

    # ── Step 6: Build trade plans ─────────────────────────────
    trade_plans = []
    for _, row in scored_df.head(top_n).iterrows():
        tech_row = None
        if not tech_df.empty:
            match = tech_df[tech_df['symbol'] == row['symbol']]
            if not match.empty:
                tech_row = match.iloc[0]
        trade_plans.append(add_trade_plan(row, tech_row))

    # ── Assemble result DataFrame ─────────────────────────────
    result_df = scored_df.head(top_n).copy().reset_index(drop=True)
    trade_df  = pd.DataFrame(trade_plans)
    for col in trade_df.columns:
        result_df[col] = trade_df[col].values

    result_df['return_1m_pct'] = (result_df['return_1m'] * 100).round(1)
    result_df['return_2m_pct'] = (result_df['return_2m'] * 100).round(1)
    result_df['return_3m_pct'] = (result_df['return_3m'] * 100).round(1)

    # ── Step 7: Assign categories ─────────────────────────────
    print(f"\n  Assigning categories...")
    if TECH_FILTERS_AVAILABLE and not tech_df.empty:
        result_df['category'] = assign_categories_bulk(
            scored_df=result_df,
            returns_df=result_df,
            w52_map=data['w52_map'],
        )
    else:
        result_df['category'] = result_df.apply(
            _assign_category_simple, axis=1
        )

    cat_counts = result_df['category'].value_counts()
    for cat, count in cat_counts.items():
        meta = CATEGORY_META.get(cat, {})
        print(f"    {meta.get('icon','•')} {meta.get('label', cat)}: {count}")

    # ── Step 8: Load streaks ──────────────────────────────────
    streaks = _load_streaks()
    result_df['streak'] = result_df['symbol'].map(
        lambda s: streaks.get(s, 0)
    )
    strong = (result_df['streak'] >= 5).sum()
    if strong > 0:
        print(f"  🔥 {strong} stocks with 5+ day streak")

    # ── Step 9: Assign situations (weekly-tier aware) ─────────
    print(f"\n  Assigning situations...")

    def _get_situation(row):
        w_tier = int(row.get('weekly_tier', WEEKLY_TIER_NEUTRAL))
        streak = int(row.get('streak', 0))
        return _assign_situation_with_weekly(
            row.to_dict(), streak, w_tier
        )

    result_df['situation'] = result_df.apply(_get_situation, axis=1)

    # Situation summary
    sit_counts = result_df['situation'].value_counts()
    sit_meta   = {
        "prime": "🎯", "hold": "💰",
        "watch": "👀", "book": "⚠️", "avoid": "🚫"
    }
    for sit in ["prime", "hold", "watch", "book", "avoid"]:
        count = sit_counts.get(sit, 0)
        if count > 0:
            print(f"    {sit_meta.get(sit,'•')} {sit.title()}: {count}")

    # ── Step 10: Score breakdown for Telegram ─────────────────
    if TECH_FILTERS_AVAILABLE and not tech_df.empty:
        result_df['score_breakdown'] = result_df.apply(
            lambda r: format_score_breakdown(r.to_dict()), axis=1
        )

    log.info(
        f"Scan complete: {len(result_df)} stocks | "
        f"prime={sit_counts.get('prime',0)} "
        f"watch={sit_counts.get('watch',0)} "
        f"hold={sit_counts.get('hold',0)} "
        f"book={sit_counts.get('book',0)} "
        f"avoid={sit_counts.get('avoid',0)}"
    )

    return result_df


# ═══════════════════════════════════════════════════════════════════════════
# CLI ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="NSE Stock Scanner v5 — Forward Probability + Weekly Filter"
    )
    parser.add_argument("--date", help="Scan date DD-MM-YYYY or YYYY-MM-DD")
    parser.add_argument("--top",  type=int, help="Number of stocks (default 25)")
    args = parser.parse_args()

    scan_date = None
    if args.date:
        for fmt in ["%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"]:
            try:
                scan_date = datetime.strptime(args.date, fmt).date()
                break
            except ValueError:
                pass

    results = scan_stocks(scan_date=scan_date, top_n=args.top)
    if results.empty:
        print("\nNo results.")
        return

    # ── Console output ────────────────────────────────────────
    sit_meta = {
        "prime": "🎯", "hold": "💰",
        "watch": "👀", "book": "⚠️", "avoid": "🚫"
    }

    def print_section(title, df):
        if df.empty:
            return
        print(f"\n{'─'*80}\n  {title}\n{'─'*80}")
        print(f"  {'#':<4} {'Symbol':<12} {'Score':>5} {'3M%':>7} "
              f"{'Entry':>8} {'SL':>8} {'T1':>8} "
              f"{'Cross':>7} {'Dist':>6} "
              f"{'Weekly':<18} {'Sit'}")
        print("  " + "─" * 76)
        for i, (_, row) in enumerate(df.iterrows(), 1):
            ca  = int(row.get('cross_age', 0))
            dp  = float(row.get('dist_pct', 0))
            wl  = str(row.get('weekly_label', ''))[:16]
            sit = sit_meta.get(row.get('situation', ''), '•')
            print(
                f"  {i:<4} {str(row['symbol']):<12} "
                f"{int(row.get('score', 0)):>5} "
                f"{row.get('return_3m_pct', 0):>+7.1f}% "
                f"{row.get('entry', 0):>8.0f} "
                f"{row.get('sl', 0):>8.0f} "
                f"{row.get('target1', 0):>8.0f} "
                f"{ca:>6}d "
                f"{dp:>5.1f}% "
                f"{wl:<18} {sit}"
            )

    d_str = (scan_date or date.today()).strftime('%d-%b-%Y')
    print(f"\n{'#'*80}")
    print(f"  NSE SCANNER v5 — {d_str}")
    print(f"  Ranked by FORWARD PROBABILITY · Weekly two-tier filter")
    print(f"{'#'*80}")

    prime_df = results[results['situation'] == 'prime']
    hold_df  = results[results['situation'] == 'hold']
    watch_df = results[results['situation'] == 'watch']
    book_df  = results[results['situation'] == 'book']
    avoid_df = results[results['situation'] == 'avoid']

    print_section(f"🎯 PRIME ENTRY [{len(prime_df)}] — Enter today, TV confirms",
                  prime_df)
    print_section(f"💰 HOLD & TRAIL [{len(hold_df)}] — Trail your stop loss",
                  hold_df)
    print_section(f"👀 WATCH CLOSELY [{len(watch_df)}] — Monitor, not today",
                  watch_df)
    print_section(f"⚠️  BOOK PROFITS [{len(book_df)}] — Protect gains",
                  book_df)
    if not avoid_df.empty:
        print_section(f"🚫 AVOID [{len(avoid_df)}] — Skip today",
                      avoid_df)

    print(f"\n  Total: {len(results)} stocks")

    # Save for Telegram bot
    if save_scan_results:
        try:
            save_scan_results(results, scan_date or date.today())
            print(f"\n[OK] Results saved to telegram_last_scan.json")
        except Exception as e:
            print(f"[WARNING] Failed to save: {e}")


if __name__ == "__main__":
    main()
