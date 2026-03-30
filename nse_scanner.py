"""
nse_scanner.py — Core Stock Scanner (v3 — Categories + Streaks)
================================================================
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
        'prices': prices_df,
        'blacklist': set(blacklist_df['symbol'].tolist()),
        'w52_map': w52_map,
        'scan_date': scan_date,
    }


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
        r1m = (current_close - grp.iloc[-DAYS_1M]['close']) / grp.iloc[-DAYS_1M]['close'] if len(grp) >= DAYS_1M and grp.iloc[-DAYS_1M]['close'] > 0 else 0.0
        r2m = (current_close - grp.iloc[-DAYS_2M]['close']) / grp.iloc[-DAYS_2M]['close'] if len(grp) >= DAYS_2M and grp.iloc[-DAYS_2M]['close'] > 0 else 0.0
        r3m = (current_close - grp.iloc[-DAYS_3M]['close']) / grp.iloc[-DAYS_3M]['close'] if len(grp) >= DAYS_3M and grp.iloc[-DAYS_3M]['close'] > 0 else 0.0
        latest = grp.iloc[-1]
        avg_volume = grp.tail(22)['volume'].mean()
        results.append({
            'symbol': str(symbol).strip(), 'close': current_close,
            'open': latest.get('open', 0), 'high': latest.get('high', 0),
            'low': latest.get('low', 0), 'volume': latest.get('volume', 0),
            'avg_volume': avg_volume, 'delivery_pct': latest.get('delivery_pct', 0),
            'avg_price': latest.get('avg_price', 0),
            'return_1m': r1m, 'return_2m': r2m, 'return_3m': r3m,
        })
    return pd.DataFrame(results)


def apply_filters(stocks_df, blacklist):
    print("\n" + "="*60 + "\n  NSE SCANNER — Applying Filters\n" + "="*60)
    n = len(stocks_df)
    print(f"Initial stocks     : {n:,}")
    stocks_df = stocks_df[~stocks_df['symbol'].isin(blacklist)]
    print(f"After blacklist    : {len(stocks_df):,}")
    n = len(stocks_df)
    stocks_df = stocks_df[stocks_df['close'] >= config.MIN_PRICE]
    print(f"After price >= {config.MIN_PRICE}  : {len(stocks_df):,}")
    n = len(stocks_df)
    stocks_df = stocks_df[stocks_df['avg_volume'] >= config.MIN_VOLUME]
    print(f"After volume       : {len(stocks_df):,}")
    n = len(stocks_df)
    stocks_df = stocks_df[stocks_df['delivery_pct'] >= config.MIN_DELIVERY]
    print(f"After delivery     : {len(stocks_df):,}")
    print(f"Ready for scoring  : {len(stocks_df):,}")
    return stocks_df.reset_index(drop=True)


def calculate_momentum_score(stocks_df):
    if stocks_df.empty:
        return stocks_df
    stocks_df['momentum_score'] = (
        config.WEIGHT_1M * stocks_df['return_1m'] +
        config.WEIGHT_2M * stocks_df['return_2m'] +
        config.WEIGHT_3M * stocks_df['return_3m']
    )
    return stocks_df.sort_values('momentum_score', ascending=False)


def add_trade_plan(row, tech_row=None):
    entry = row['close']
    if tech_row is not None and pd.notna(tech_row.get('stop')) and tech_row['stop'] > 0:
        sl = tech_row['stop']
    else:
        sl = round(entry * 0.93, 2)

    risk    = entry - sl
    target1 = round(entry + (1.0 * risk), 2)
    target2 = round(entry + (2.0 * risk), 2)
    sl_pct  = round(-risk / entry * 100, 1) if entry > 0 else 0
    t1_pct  = round(risk / entry * 100, 1)  if entry > 0 else 0
    t2_pct  = round(risk * 2 / entry * 100, 1) if entry > 0 else 0

    return {
        'entry': round(entry, 2), 'sl': round(sl, 2), 'sl_pct': sl_pct,
        'target1': target1, 't1_pct': t1_pct,
        'target2': target2, 't2_pct': t2_pct, 'rr': 2.0,
    }


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


def _assign_category_simple(row):
    r1m = float(row.get("return_1m", 0))
    r2m = float(row.get("return_2m", 0))
    r3m = float(row.get("return_3m", 0))
    dlv = float(row.get("delivery_pct", 0))
    if r1m > r3m + 0.02 and r3m < 0.10:
        return "recovering"
    if dlv >= 55:
        return "safer"
    if r1m > 0 and r2m > 0 and r3m > 0:
        return "rising"
    return "rising"


def scan_stocks(scan_date=None, top_n=None):
    if scan_date is None:
        scan_date = date.today()
    if top_n is None:
        top_n = config.TOP_N_STOCKS

    print(f"\nScanning for date  : {scan_date.strftime('%d-%b-%Y')}")

    data = load_data_for_date(scan_date)
    if data['prices'].empty:
        print("ERROR: No price data in database.")
        return pd.DataFrame()

    stocks_df = calculate_returns(data['prices'], scan_date)
    if stocks_df.empty:
        return pd.DataFrame()

    filtered_df = apply_filters(stocks_df, data['blacklist'])
    if filtered_df.empty:
        return pd.DataFrame()

    scored_df = calculate_momentum_score(filtered_df)

    tech_df = pd.DataFrame()
    if TECH_FILTERS_AVAILABLE:
        print(f"\n  Running technical signal scoring...")
        tech_df = score_all_stocks(
            price_df=data['prices'],
            filtered_symbols=filtered_df['symbol'].tolist(),
            scan_date=scan_date, w52_map=data['w52_map'],
        )

    if not tech_df.empty:
        tech_df = tech_df.reset_index()
        merge_cols = [c for c in ['symbol','score','conviction','stop','target','rr','rsi',
                      'vol_ratio','pts_hma','pts_vol','pts_brk','pts_rsi','pts_macd',
                      'pts_52w','pts_rr','fresh_cross'] if c in tech_df.columns]
        scored_df = scored_df.merge(tech_df[merge_cols], on='symbol', how='left')
        scored_df['score']      = scored_df['score'].fillna(0)
        scored_df['conviction'] = scored_df['conviction'].fillna('')
        hc   = scored_df[scored_df['conviction'] == 'HIGH CONVICTION'].sort_values('score', ascending=False)
        wl   = scored_df[scored_df['conviction'] == 'Watchlist'].sort_values('score', ascending=False)
        rest = scored_df[scored_df['conviction'] == ''].sort_values('momentum_score', ascending=False)
        scored_df = pd.concat([hc, wl, rest], ignore_index=True)
    else:
        scored_df['score']      = (scored_df['momentum_score'] * 100).round(1)
        scored_df['conviction'] = ''
        scored_df['stop']       = None

    trade_plans = []
    for _, row in scored_df.head(top_n).iterrows():
        tech_row = None
        if not tech_df.empty:
            match = tech_df[tech_df['symbol'] == row['symbol']]
            if not match.empty:
                tech_row = match.iloc[0]
        trade_plans.append(add_trade_plan(row, tech_row))

    result_df = scored_df.head(top_n).copy().reset_index(drop=True)
    trade_df  = pd.DataFrame(trade_plans)
    for col in trade_df.columns:
        result_df[col] = trade_df[col].values

    result_df['return_1m_pct'] = (result_df['return_1m'] * 100).round(1)
    result_df['return_2m_pct'] = (result_df['return_2m'] * 100).round(1)
    result_df['return_3m_pct'] = (result_df['return_3m'] * 100).round(1)

    # ── Assign categories ──
    print(f"\n  Assigning layman categories...")
    if TECH_FILTERS_AVAILABLE and not tech_df.empty:
        result_df['category'] = assign_categories_bulk(
            scored_df=result_df, returns_df=result_df, w52_map=data['w52_map'])
    else:
        result_df['category'] = result_df.apply(_assign_category_simple, axis=1)

    cat_counts = result_df['category'].value_counts()
    for cat, count in cat_counts.items():
        meta = CATEGORY_META.get(cat, {})
        print(f"    {meta.get('icon','•')} {meta.get('label', cat)}: {count}")

    # ── Add streaks ──
    streaks = _load_streaks()
    result_df['streak'] = result_df['symbol'].map(lambda s: streaks.get(s, 0))
    strong = (result_df['streak'] >= 5).sum()
    if strong > 0:
        print(f"  🔥 {strong} stocks with 5+ day streak")

    log.info(f"Scan complete: {len(result_df)} stocks | Cats: {dict(cat_counts)}")
    return result_df


def main():
    parser = argparse.ArgumentParser(description="NSE Stock Momentum Scanner")
    parser.add_argument("--date", help="Scan date DD-MM-YYYY")
    parser.add_argument("--top",  type=int, help="Number of top stocks")
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

    hc_df = results[results['conviction'] == 'HIGH CONVICTION']
    wl_df = results[results['conviction'] == 'Watchlist']

    def print_section(title, df):
        if df.empty: return
        print(f"\n{'─'*72}\n  {title}\n{'─'*72}")
        for i, (_, row) in enumerate(df.iterrows(), 1):
            print(f"  {i:<4} {str(row['symbol']):<12} {int(row.get('score',0)):>3} "
                  f"{row['return_3m_pct']:>+6.1f}% {row['entry']:>8.2f} "
                  f"{row['sl']:>8.2f} {row['target1']:>8.2f} {row['target2']:>8.2f} "
                  f"{row.get('category','')}")

    print(f"\n{'#'*72}\n  NSE SCANNER RESULTS — {(scan_date or date.today()).strftime('%d-%b-%Y')}\n{'#'*72}")
    print_section(f"HIGH CONVICTION [{len(hc_df)}]", hc_df)
    print_section(f"WATCHLIST [{len(wl_df)}]", wl_df)

    if save_scan_results:
        try:
            save_scan_results(results, scan_date or date.today())
            print(f"[OK] Results saved to telegram_last_scan.json")
        except Exception as e:
            print(f"[WARNING] Failed to save: {e}")


if __name__ == "__main__":
    main()
