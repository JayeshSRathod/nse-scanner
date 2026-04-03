"""
nse_scanner.py — Core Stock Scanner (v4 — Forward Probability Ranking)
=======================================================================
WHAT CHANGED FROM v3:
  OLD: Ranked stocks by 50% weight on 3M past return
  NEW: Ranked by forward probability score from nse_technical_filters

3M PAST RETURN ROLE:
  OLD: Primary ranking factor (50% weight in momentum_score)
  NEW: Filter only — must be > 0 to confirm uptrend exists
       Stored in output but NOT used for ranking

RANKING ORDER:
  1. HIGH CONVICTION stocks  → sorted by forward score (desc)
  2. Watchlist stocks        → sorted by forward score (desc)
  3. Unscored stocks         → sorted by momentum_score (fallback only)

Everything else (DB loading, filters, trade plan, streaks,
categories, Telegram save) unchanged.
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
    CATEGORY_ORDER = ["uptrend", "rising", "peak", "safer", "recovering"]

try:
    from nse_telegram_handler import save_scan_results
except ImportError:
    save_scan_results = None

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
# DATA LOADING (unchanged from v3)
# ═══════════════════════════════════════════════════════════════════════════

def load_data_for_date(scan_date):
    conn = sqlite3.connect(config.DB_PATH)
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
# RETURN CALCULATION (unchanged — stored for display, NOT for ranking)
# ═══════════════════════════════════════════════════════════════════════════

def calculate_returns(prices_df, scan_date):
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

        r1m = ((current_close - grp.iloc[-DAYS_1M]['close']) /
               grp.iloc[-DAYS_1M]['close']
               if len(grp) >= DAYS_1M and grp.iloc[-DAYS_1M]['close'] > 0 else 0.0)
        r2m = ((current_close - grp.iloc[-DAYS_2M]['close']) /
               grp.iloc[-DAYS_2M]['close']
               if len(grp) >= DAYS_2M and grp.iloc[-DAYS_2M]['close'] > 0 else 0.0)
        r3m = ((current_close - grp.iloc[-DAYS_3M]['close']) /
               grp.iloc[-DAYS_3M]['close']
               if len(grp) >= DAYS_3M and grp.iloc[-DAYS_3M]['close'] > 0 else 0.0)

        latest = grp.iloc[-1]
        avg_volume = grp.tail(22)['volume'].mean()

        results.append({
            'symbol':       str(symbol).strip(),
            'close':        current_close,
            'open':         latest.get('open', 0),
            'high':         latest.get('high', 0),
            'low':          latest.get('low', 0),
            'volume':       latest.get('volume', 0),
            'avg_volume':   avg_volume,
            'delivery_pct': latest.get('delivery_pct', 0),
            'avg_price':    latest.get('avg_price', 0),
            'return_1m':    r1m,
            'return_2m':    r2m,
            'return_3m':    r3m,
        })

    return pd.DataFrame(results)


# ═══════════════════════════════════════════════════════════════════════════
# FILTERS (unchanged — basic quality gates)
# ═══════════════════════════════════════════════════════════════════════════

def apply_filters(stocks_df, blacklist):
    print("\n" + "=" * 60 + "\n  NSE SCANNER — Applying Filters\n" + "=" * 60)
    print(f"Initial stocks     : {len(stocks_df):,}")

    stocks_df = stocks_df[~stocks_df['symbol'].isin(blacklist)]
    print(f"After blacklist    : {len(stocks_df):,}")

    stocks_df = stocks_df[stocks_df['close'] >= config.MIN_PRICE]
    print(f"After price >= {config.MIN_PRICE}  : {len(stocks_df):,}")

    stocks_df = stocks_df[stocks_df['avg_volume'] >= config.MIN_VOLUME]
    print(f"After volume       : {len(stocks_df):,}")

    stocks_df = stocks_df[stocks_df['delivery_pct'] >= config.MIN_DELIVERY]
    print(f"After delivery     : {len(stocks_df):,}")

    # ── NEW: 3M return must be positive (uptrend filter only) ────────────
    # This replaces the old 50% ranking weight.
    # We only want stocks in an established uptrend.
    stocks_df = stocks_df[stocks_df['return_3m'] > 0]
    print(f"After uptrend gate : {len(stocks_df):,}  (3M return > 0%)")

    print(f"Ready for scoring  : {len(stocks_df):,}")
    return stocks_df.reset_index(drop=True)


# ═══════════════════════════════════════════════════════════════════════════
# MOMENTUM SCORE — kept as fallback only, NOT used for ranking
# ═══════════════════════════════════════════════════════════════════════════

def calculate_momentum_score(stocks_df):
    """
    Kept for fallback display only.
    This score is NO LONGER used for ranking — forward score is used instead.
    """
    if stocks_df.empty:
        return stocks_df
    stocks_df['momentum_score'] = (
        config.WEIGHT_1M * stocks_df['return_1m'] +
        config.WEIGHT_2M * stocks_df['return_2m'] +
        config.WEIGHT_3M * stocks_df['return_3m']
    )
    # NOTE: Do NOT sort here — forward score will handle ranking
    return stocks_df


# ═══════════════════════════════════════════════════════════════════════════
# TRADE PLAN (updated to use HMA55-based SL from tech filters)
# ═══════════════════════════════════════════════════════════════════════════

def add_trade_plan(row, tech_row=None):
    entry = float(row['close'])

    # Use HMA55-based SL from technical filters if available (tighter, better)
    if tech_row is not None and pd.notna(tech_row.get('stop')) and float(tech_row.get('stop', 0)) > 0:
        sl = float(tech_row['stop'])
    else:
        sl = round(entry * 0.93, 2)  # fallback: 7% SL

    risk    = max(entry - sl, entry * 0.01)  # floor risk at 1%
    target1 = round(entry + (1.0 * risk), 2)
    target2 = round(entry + (2.0 * risk), 2)
    sl_pct  = round(-risk / entry * 100, 1) if entry > 0 else 0
    t1_pct  = round(risk / entry * 100, 1)  if entry > 0 else 0
    t2_pct  = round(risk * 2 / entry * 100, 1) if entry > 0 else 0

    return {
        'entry':   round(entry, 2),
        'sl':      round(sl, 2),
        'sl_pct':  sl_pct,
        'target1': target1,
        't1_pct':  t1_pct,
        'target2': target2,
        't2_pct':  t2_pct,
        'rr':      2.0,
    }


# ═══════════════════════════════════════════════════════════════════════════
# STREAK LOADER (unchanged)
# ═══════════════════════════════════════════════════════════════════════════

def _load_streaks():
    history_file = Path("scan_history.json")
    if not history_file.exists():
        return {}
    try:
        data = json.loads(history_file.read_text(encoding="utf-8"))
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
# SIMPLE CATEGORY FALLBACK (when tech filters unavailable)
# ═══════════════════════════════════════════════════════════════════════════

def _assign_category_simple(row):
    r1m = float(row.get("return_1m", 0))
    r3m = float(row.get("return_3m", 0))
    dlv = float(row.get("delivery_pct", 0))
    if r1m > r3m * 0.5 and r3m < 0.10:
        return "recovering"
    if dlv >= 55:
        return "safer"
    if r1m > 0 and r3m > 0:
        return "rising"
    return "rising"


# ═══════════════════════════════════════════════════════════════════════════
# MAIN SCAN FUNCTION
# ═══════════════════════════════════════════════════════════════════════════

def scan_stocks(scan_date=None, top_n=None):
    if scan_date is None:
        scan_date = date.today()
    if top_n is None:
        top_n = config.TOP_N_STOCKS

    print(f"\nScanning for date  : {scan_date.strftime('%d-%b-%Y')}")
    print(f"Ranking by         : FORWARD PROBABILITY SCORE (not 3M return)")

    # ── Load data ─────────────────────────────────────────────────────────
    data = load_data_for_date(scan_date)
    if data['prices'].empty:
        print("ERROR: No price data in database.")
        return pd.DataFrame()

    # ── Calculate returns (for display + uptrend filter) ──────────────────
    stocks_df = calculate_returns(data['prices'], scan_date)
    if stocks_df.empty:
        return pd.DataFrame()

    # ── Apply basic quality filters + 3M uptrend gate ─────────────────────
    filtered_df = apply_filters(stocks_df, data['blacklist'])
    if filtered_df.empty:
        return pd.DataFrame()

    # ── Momentum score (display only, not for ranking) ────────────────────
    scored_df = calculate_momentum_score(filtered_df)

    # ── Forward-looking technical scoring ─────────────────────────────────
    tech_df = pd.DataFrame()
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

        # All columns we want to bring in from tech scoring
        merge_cols = [c for c in [
            'symbol', 'score', 'conviction', 'stop', 'target', 'target2', 'rr',
            'rsi', 'pts_hma', 'pts_dist', 'pts_vol', 'pts_rsi', 'pts_macd',
            'pts_sector', 'pts_rr', 'pen_overext', 'pen_decel',
            'fresh_cross', 'cross_age', 'dist_pct', 'overextended',
            'obv_dir', 'acc_days', 'dist_days', 'del_trend',
            'hma_trend_up', 'near_52w', 'sector_bias',
        ] if c in tech_df.columns]

        scored_df = scored_df.merge(tech_df[merge_cols], on='symbol', how='left')
        scored_df['score']      = scored_df['score'].fillna(0)
        scored_df['conviction'] = scored_df['conviction'].fillna('')

        # ── RANKING: Forward score, HIGH CONVICTION first ─────────────────
        # This is the core change from v3
        hc   = (scored_df[scored_df['conviction'] == TIER_HIGH_CONVICTION]
                .sort_values('score', ascending=False))
        wl   = (scored_df[scored_df['conviction'] == TIER_WATCHLIST]
                .sort_values('score', ascending=False))
        rest = (scored_df[scored_df['conviction'] == '']
                .sort_values('momentum_score', ascending=False))  # fallback only

        scored_df = pd.concat([hc, wl, rest], ignore_index=True)

        print(f"\n  HIGH CONVICTION (score ≥7): {len(hc)} stocks")
        print(f"  Watchlist (score 4-6):       {len(wl)} stocks")

    else:
        # Fallback when tech filters unavailable — use momentum score
        scored_df['score']      = (scored_df['momentum_score'] * 100).round(1)
        scored_df['conviction'] = ''
        scored_df['stop']       = None
        scored_df = scored_df.sort_values('momentum_score', ascending=False)
        log.warning("Tech filters unavailable — falling back to momentum score ranking")

    # ── Build trade plans ─────────────────────────────────────────────────
    trade_plans = []
    for _, row in scored_df.head(top_n).iterrows():
        tech_row = None
        if not tech_df.empty:
            match = tech_df[tech_df['symbol'] == row['symbol']]
            if not match.empty:
                tech_row = match.iloc[0]
        trade_plans.append(add_trade_plan(row, tech_row))

    # ── Assemble result DataFrame ─────────────────────────────────────────
    result_df = scored_df.head(top_n).copy().reset_index(drop=True)
    trade_df  = pd.DataFrame(trade_plans)
    for col in trade_df.columns:
        result_df[col] = trade_df[col].values

    # Return pct versions for display
    result_df['return_1m_pct'] = (result_df['return_1m'] * 100).round(1)
    result_df['return_2m_pct'] = (result_df['return_2m'] * 100).round(1)
    result_df['return_3m_pct'] = (result_df['return_3m'] * 100).round(1)

    # ── Assign categories ─────────────────────────────────────────────────
    print(f"\n  Assigning forward-looking categories...")
    if TECH_FILTERS_AVAILABLE and not tech_df.empty:
        result_df['category'] = assign_categories_bulk(
            scored_df=result_df,
            returns_df=result_df,
            w52_map=data['w52_map'],
        )
    else:
        result_df['category'] = result_df.apply(_assign_category_simple, axis=1)

    cat_counts = result_df['category'].value_counts()
    for cat, count in cat_counts.items():
        meta = CATEGORY_META.get(cat, {})
        print(f"    {meta.get('icon', '•')} {meta.get('label', cat)}: {count}")

    # ── Add streaks ───────────────────────────────────────────────────────
    streaks = _load_streaks()
    result_df['streak'] = result_df['symbol'].map(lambda s: streaks.get(s, 0))
    strong = (result_df['streak'] >= 5).sum()
    if strong > 0:
        print(f"  🔥 {strong} stocks with 5+ day streak")

    # ── Score breakdown string (for Telegram display) ─────────────────────
    if TECH_FILTERS_AVAILABLE and not tech_df.empty:
        result_df['score_breakdown'] = result_df.apply(
            lambda r: format_score_breakdown(r.to_dict()), axis=1
        )

    log.info(
        f"Scan complete: {len(result_df)} stocks | "
        f"HC: {len(result_df[result_df.get('conviction','') == TIER_HIGH_CONVICTION] if 'conviction' in result_df.columns else [])} | "
        f"Cats: {dict(cat_counts)}"
    )
    return result_df


# ═══════════════════════════════════════════════════════════════════════════
# CLI ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="NSE Stock Scanner — Forward Probability Ranking")
    parser.add_argument("--date", help="Scan date DD-MM-YYYY or YYYY-MM-DD")
    parser.add_argument("--top",  type=int, help="Number of top stocks (default 25)")
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

    # ── Console output ────────────────────────────────────────────────────
    hc_df = results[results.get('conviction', pd.Series()) == TIER_HIGH_CONVICTION] if 'conviction' in results.columns else pd.DataFrame()
    wl_df = results[results.get('conviction', pd.Series()) == TIER_WATCHLIST]       if 'conviction' in results.columns else pd.DataFrame()

    def print_section(title, df):
        if df.empty:
            return
        print(f"\n{'─' * 80}\n  {title}\n{'─' * 80}")
        print(f"  {'#':<4} {'Symbol':<12} {'Score':>5} {'3M%':>7} "
              f"{'Entry':>8} {'SL':>8} {'T1':>8} {'T2':>8} "
              f"{'Cross':>7} {'Dist%':>6} {'Cat'}")
        print(f"  {'─'*4} {'─'*12} {'─'*5} {'─'*7} "
              f"{'─'*8} {'─'*8} {'─'*8} {'─'*8} "
              f"{'─'*7} {'─'*6} {'─'*12}")
        for i, (_, row) in enumerate(df.iterrows(), 1):
            cross_age = int(row.get('cross_age', 0))
            cross_str = f"{cross_age}d" if cross_age > 0 else "—"
            dist_str  = f"{row.get('dist_pct', 0):.1f}%" if 'dist_pct' in row else "—"
            print(
                f"  {i:<4} {str(row['symbol']):<12} "
                f"{int(row.get('score', 0)):>5} "
                f"{row.get('return_3m_pct', 0):>+7.1f}% "
                f"{row.get('entry', 0):>8.0f} "
                f"{row.get('sl', 0):>8.0f} "
                f"{row.get('target1', 0):>8.0f} "
                f"{row.get('target2', 0):>8.0f} "
                f"{cross_str:>7} "
                f"{dist_str:>6} "
                f"{row.get('category', '')}"
            )

    d_str = (scan_date or date.today()).strftime('%d-%b-%Y')
    print(f"\n{'#' * 80}")
    print(f"  NSE SCANNER — {d_str}  |  Ranked by FORWARD PROBABILITY SCORE")
    print(f"{'#' * 80}")
    print_section(f"HIGH CONVICTION — score ≥7 [{len(hc_df)}]", hc_df)
    print_section(f"WATCHLIST — score 4-6 [{len(wl_df)}]", wl_df)

    # Save for Telegram bot
    if save_scan_results:
        try:
            save_scan_results(results, scan_date or date.today())
            print(f"\n[OK] Results saved to telegram_last_scan.json")
        except Exception as e:
            print(f"[WARNING] Failed to save: {e}")


if __name__ == "__main__":
    main()
