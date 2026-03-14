"""
nse_scanner.py — Core Stock Scanner (v2 — with Technical Signals)
===================================================================
Loads data from SQLite -> applies filters -> momentum score ->
technical signal score -> returns ranked stocks with trade plan.

Changes from v1:
    - Fixed DAYS_3M: 66 trading days (was 180 — that is download window)
    - Integrated nse_technical_filters for HMA/RSI/MACD/RR scoring
    - Added entry, sl, target1, target2 columns to output
    - Added conviction tier: HIGH CONVICTION / Watchlist

Usage:
    python nse_scanner.py
    python nse_scanner.py --date 05-03-2026
    python nse_scanner.py --top 30
"""

import os
import sys
import argparse
import sqlite3
import pandas as pd
import numpy as np
from datetime import date, datetime, timedelta
import logging

try:
    import config
except ImportError:
    print("ERROR: config.py not found. Run setup_project.py first.")
    sys.exit(1)

try:
    from nse_technical_filters import score_all_stocks, TIER_HIGH_CONVICTION, TIER_WATCHLIST
    TECH_FILTERS_AVAILABLE = True
except ImportError:
    print("WARNING: nse_technical_filters.py not found. Running momentum-only mode.")
    TECH_FILTERS_AVAILABLE = False

try:
    from nse_telegram_handler import save_scan_results
except ImportError:
    save_scan_results = None

# ── Return periods (trading days) ────────────────────────────
DAYS_1M = 22    # 1 month
DAYS_2M = 44    # 2 months
DAYS_3M = 66    # 3 months  ← FIXED (was 180 in config — that is download window)
LOOKBACK = 180  # How many days to load from DB for indicator calculation

# ── Logging ──────────────────────────────────────────────────
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


def load_data_for_date(scan_date: date) -> dict:
    """
    Load price history and blacklist from SQLite.
    Loads LOOKBACK=180 days so technical indicators have enough history.
    """
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

    # Load latest week52 for bonus signal
    w52_df = pd.read_sql_query(f"""
        SELECT symbol, week52_high, week52_low FROM week52
        WHERE date = '{scan_date}'
    """, conn)
    w52_map = {
        row['symbol']: (row['week52_high'], row['week52_low'])
        for _, row in w52_df.iterrows()
    }

    conn.close()

    return {
        'prices'    : prices_df,
        'blacklist' : set(blacklist_df['symbol'].tolist()),
        'w52_map'   : w52_map,
        'scan_date' : scan_date,
    }


def calculate_returns(prices_df: pd.DataFrame, scan_date: date) -> pd.DataFrame:
    """
    Calculate 1M / 2M / 3M returns using correct 66-day lookback.
    Also calculates avg_volume over last 22 days for filter.
    """
    if prices_df.empty:
        return pd.DataFrame()

    recent = prices_df[prices_df['date'] <= pd.Timestamp(scan_date)].copy()
    recent['symbol'] = recent['symbol'].astype(str).str.strip()
    recent = recent.dropna(subset=['symbol', 'date', 'close'])
    recent = recent.sort_values(['symbol', 'date'])

    results = []

    for symbol, grp in recent.groupby('symbol'):
        grp = grp.tail(DAYS_3M + 5)   # a bit of buffer

        if len(grp) < DAYS_1M:
            continue

        current_close = grp.iloc[-1]['close']

        # 1M return
        r1m = 0.0
        if len(grp) >= DAYS_1M:
            p = grp.iloc[-DAYS_1M]['close']
            r1m = (current_close - p) / p if p > 0 else 0.0

        # 2M return
        r2m = 0.0
        if len(grp) >= DAYS_2M:
            p = grp.iloc[-DAYS_2M]['close']
            r2m = (current_close - p) / p if p > 0 else 0.0

        # 3M return (66 trading days)
        r3m = 0.0
        if len(grp) >= DAYS_3M:
            p = grp.iloc[-DAYS_3M]['close']
            r3m = (current_close - p) / p if p > 0 else 0.0

        latest      = grp.iloc[-1]
        avg_volume  = grp.tail(22)['volume'].mean()

        results.append({
            'symbol'       : str(symbol).strip(),
            'close'        : current_close,
            'open'         : latest.get('open', 0),
            'high'         : latest.get('high', 0),
            'low'          : latest.get('low', 0),
            'volume'       : latest.get('volume', 0),
            'avg_volume'   : avg_volume,
            'delivery_pct' : latest.get('delivery_pct', 0),
            'avg_price'    : latest.get('avg_price', 0),
            'return_1m'    : r1m,
            'return_2m'    : r2m,
            'return_3m'    : r3m,
        })

    return pd.DataFrame(results)


def apply_filters(stocks_df: pd.DataFrame, blacklist: set) -> pd.DataFrame:
    """Apply all basic filters sequentially with counts."""
    print("\n" + "="*60)
    print("  NSE SCANNER — Applying Filters")
    print("="*60)

    n = len(stocks_df)
    print(f"Initial stocks     : {n:,}")

    stocks_df = stocks_df[~stocks_df['symbol'].isin(blacklist)]
    print(f"After blacklist    : {len(stocks_df):,}  (removed {n - len(stocks_df)} GSM/ASM/IRP)")

    n = len(stocks_df)
    stocks_df = stocks_df[stocks_df['close'] >= config.MIN_PRICE]
    print(f"After price >= {config.MIN_PRICE}  : {len(stocks_df):,}  (removed {n - len(stocks_df)} penny stocks)")

    n = len(stocks_df)
    stocks_df = stocks_df[stocks_df['avg_volume'] >= config.MIN_VOLUME]
    print(f"After volume {config.MIN_VOLUME//1000}k   : {len(stocks_df):,}  (removed {n - len(stocks_df)} illiquid)")

    n = len(stocks_df)
    stocks_df = stocks_df[stocks_df['delivery_pct'] >= config.MIN_DELIVERY]
    print(f"After delivery {config.MIN_DELIVERY}% : {len(stocks_df):,}  (removed {n - len(stocks_df)} speculative)")

    print("─"*60)
    print(f"Ready for scoring  : {len(stocks_df):,} quality stocks")

    return stocks_df.reset_index(drop=True)


def calculate_momentum_score(stocks_df: pd.DataFrame) -> pd.DataFrame:
    """Weighted momentum score from 1M/2M/3M returns."""
    if stocks_df.empty:
        return stocks_df

    stocks_df['momentum_score'] = (
        config.WEIGHT_1M * stocks_df['return_1m'] +
        config.WEIGHT_2M * stocks_df['return_2m'] +
        config.WEIGHT_3M * stocks_df['return_3m']
    )
    return stocks_df.sort_values('momentum_score', ascending=False)


def add_trade_plan(row: pd.Series, tech_row: pd.Series = None) -> dict:
    """
    Calculate Entry, SL, Target1, Target2 for one stock.

    Entry   = today's close
    SL      = from technical filter (HMA55 or 5D low)
              fallback = close * 0.92 (8% below)
    Target1 = Entry + (1 x Risk)   -- partial exit ~1 month
    Target2 = Entry + (2 x Risk)   -- full target  ~3 months
    """
    entry = row['close']

    # Use technical filter SL if available
    if tech_row is not None and pd.notna(tech_row.get('stop')) and tech_row['stop'] > 0:
        sl = tech_row['stop']
    else:
        sl = round(entry * 0.92, 2)   # fallback: 8% stop

    risk    = entry - sl
    target1 = round(entry + (1.0 * risk), 2)
    target2 = round(entry + (2.0 * risk), 2)

    sl_pct  = round(-risk / entry * 100, 1)
    t1_pct  = round(risk  / entry * 100, 1)
    t2_pct  = round(risk * 2 / entry * 100, 1)
    rr      = round(risk / risk, 1) if risk > 0 else 0   # always 2.0

    return {
        'entry'   : round(entry, 2),
        'sl'      : round(sl, 2),
        'sl_pct'  : sl_pct,
        'target1' : target1,
        't1_pct'  : t1_pct,
        'target2' : target2,
        't2_pct'  : t2_pct,
        'rr'      : 2.0,
    }


def scan_stocks(scan_date: date = None, top_n: int = None) -> pd.DataFrame:
    """
    Main scan function. Returns ranked DataFrame with full trade plan.
    """
    if scan_date is None:
        scan_date = date.today()
    if top_n is None:
        top_n = config.TOP_N_STOCKS

    print(f"\nScanning for date  : {scan_date.strftime('%d-%b-%Y')}")
    print(f"3M lookback        : {DAYS_3M} trading days (fixed)")
    print(f"History loaded     : {LOOKBACK} days (for HMA stability)")

    # ── Load data ──
    data = load_data_for_date(scan_date)
    if data['prices'].empty:
        print("ERROR: No price data in database. Run nse_loader.py first.")
        return pd.DataFrame()

    # ── Returns ──
    stocks_df = calculate_returns(data['prices'], scan_date)
    if stocks_df.empty:
        print("ERROR: Could not calculate returns.")
        return pd.DataFrame()

    # ── Basic filters ──
    filtered_df = apply_filters(stocks_df, data['blacklist'])
    if filtered_df.empty:
        print("No stocks passed basic filters.")
        return pd.DataFrame()

    # ── Momentum score ──
    scored_df = calculate_momentum_score(filtered_df)

    # ── Technical signal scoring ──
    tech_df = pd.DataFrame()
    if TECH_FILTERS_AVAILABLE:
        print(f"\n  Running technical signal scoring...")
        tech_df = score_all_stocks(
            price_df         = data['prices'],
            filtered_symbols = filtered_df['symbol'].tolist(),
            scan_date        = scan_date,
            w52_map          = data['w52_map'],
        )

    # ── Merge technical scores into results ──
    if not tech_df.empty:
        tech_df = tech_df.reset_index()
        merge_cols = ['symbol', 'score', 'conviction', 'stop',
                      'target', 'rr', 'rsi', 'vol_ratio',
                      'pts_hma', 'pts_vol', 'pts_brk',
                      'pts_rsi', 'pts_macd', 'pts_52w', 'pts_rr',
                      'fresh_cross']
        merge_cols = [c for c in merge_cols if c in tech_df.columns]
        scored_df = scored_df.merge(
            tech_df[merge_cols],
            on='symbol', how='left'
        )
        scored_df['score']      = scored_df['score'].fillna(0)
        scored_df['conviction'] = scored_df['conviction'].fillna('')

        # Sort: HIGH CONVICTION first by tech score, then rest by momentum
        hc   = scored_df[scored_df['conviction'] == 'HIGH CONVICTION'].sort_values('score', ascending=False)
        wl   = scored_df[scored_df['conviction'] == 'Watchlist'].sort_values('score', ascending=False)
        rest = scored_df[scored_df['conviction'] == ''].sort_values('momentum_score', ascending=False)
        scored_df = pd.concat([hc, wl, rest], ignore_index=True)
    else:
        # No tech filter — use pure momentum ranking
        scored_df['score']      = (scored_df['momentum_score'] * 100).round(1)
        scored_df['conviction'] = ''
        scored_df['stop']       = None

    # ── Add trade plan ──
    trade_plans = []
    for _, row in scored_df.head(top_n).iterrows():
        tech_row = None
        if not tech_df.empty:
            match = tech_df[tech_df['symbol'] == row['symbol']]
            if not match.empty:
                tech_row = match.iloc[0]
        trade_plans.append(add_trade_plan(row, tech_row))

    # Take top N and add trade plan columns
    result_df = scored_df.head(top_n).copy().reset_index(drop=True)
    trade_df  = pd.DataFrame(trade_plans)

    for col in trade_df.columns:
        result_df[col] = trade_df[col].values

    # ── Format display columns ──
    result_df['return_1m_pct'] = (result_df['return_1m'] * 100).round(1)
    result_df['return_2m_pct'] = (result_df['return_2m'] * 100).round(1)
    result_df['return_3m_pct'] = (result_df['return_3m'] * 100).round(1)

    log.info(
        f"Scan complete: {len(result_df)} stocks | "
        f"HC={( result_df['conviction'] == 'HIGH CONVICTION').sum()} | "
        f"WL={(result_df['conviction'] == 'Watchlist').sum()}"
    )

    return result_df


def main():
    parser = argparse.ArgumentParser(description="NSE Stock Momentum Scanner")
    parser.add_argument("--date", help="Scan date DD-MM-YYYY")
    parser.add_argument("--top",  type=int, help="Number of top stocks to show")
    args = parser.parse_args()

    scan_date = None
    if args.date:
        for fmt in ["%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"]:
            try:
                scan_date = datetime.strptime(args.date, fmt).date()
                break
            except ValueError:
                pass
        if not scan_date:
            print(f"ERROR: Invalid date: {args.date}. Use DD-MM-YYYY")
            sys.exit(1)

    results = scan_stocks(scan_date=scan_date, top_n=args.top)

    if results.empty:
        print("\nNo results to display.")
        return

    # ── Print results ──
    hc_df = results[results['conviction'] == 'HIGH CONVICTION']
    wl_df = results[results['conviction'] == 'Watchlist']
    ot_df = results[~results['conviction'].isin(['HIGH CONVICTION', 'Watchlist'])]

    def print_section(title, df):
        if df.empty:
            return
        print(f"\n{'─'*72}")
        print(f"  {title}")
        print(f"{'─'*72}")
        print(f"  {'#':<4} {'Symbol':<12} {'Scr':>3} {'1M%':>6} {'2M%':>6} {'3M%':>6} "
              f"{'Entry':>8} {'SL':>8} {'T1':>8} {'T2':>8}")
        print(f"  {'─'*68}")
        for i, (_, row) in enumerate(df.iterrows(), 1):
            print(
                f"  {i:<4} {str(row['symbol']):<12} "
                f"{int(row.get('score',0)):>3} "
                f"{row['return_1m_pct']:>+6.1f}% "
                f"{row['return_2m_pct']:>+6.1f}% "
                f"{row['return_3m_pct']:>+6.1f}% "
                f"{row['entry']:>8.2f} "
                f"{row['sl']:>8.2f} "
                f"{row['target1']:>8.2f} "
                f"{row['target2']:>8.2f}"
            )

    print(f"\n{'#'*72}")
    print(f"  NSE SCANNER RESULTS — {(scan_date or date.today()).strftime('%d-%b-%Y')}")
    print(f"  Entry=Close | SL=HMA55/5DLow | T1=1xRisk | T2=2xRisk")
    print(f"{'#'*72}")
    print_section(f"HIGH CONVICTION (8-10)  [{len(hc_df)} stocks]", hc_df)
    print_section(f"WATCHLIST (5-7)         [{len(wl_df)} stocks]", wl_df)
    print_section(f"MOMENTUM ONLY           [{len(ot_df)} stocks]", ot_df)
    print(f"\n  Total: {len(results)} stocks\n")
    
    # Save results to Telegram JSON for bot pagination
    if save_scan_results:
        try:
            save_scan_results(results, scan_date or date.today())
            print(f"[OK] Results saved to telegram_last_scan.json for bot pagination")
        except Exception as e:
            print(f"[WARNING] Failed to save to Telegram JSON: {e}")


if __name__ == "__main__":
    main()