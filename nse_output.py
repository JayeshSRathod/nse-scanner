"""
nse_output.py — Report Generator (v5 — Bucketed + Bug fixes)
"""

import os
import sys
import glob
import json
import requests
import pandas as pd
from datetime import date, datetime
import logging
import re

try:
    import config
except ImportError:
    print("ERROR: config.py not found.")
    sys.exit(1)

try:
    from nse_telegram_handler import (
        save_scan_results, RESULTS_FILE, PARSE_MODE,
        CATEGORY_META, CATEGORY_ORDER,
    )
    _HANDLER_OK = True
    print(f"[OUTPUT] Pagination JSON will be saved to: {RESULTS_FILE}")
except ImportError as e:
    save_scan_results = None
    RESULTS_FILE      = None
    PARSE_MODE        = "HTML"
    _HANDLER_OK       = False
    CATEGORY_META = {
        "rising":     {"icon": "📈", "label": "Consistently Rising"},
        "uptrend":    {"icon": "🚀", "label": "Clear Uptrend"},
        "peak":       {"icon": "🔝", "label": "Close to Peak"},
        "recovering": {"icon": "📉", "label": "Recovering"},
        "safer":      {"icon": "🛡️", "label": "Safer Bets"},
    }
    CATEGORY_ORDER = ["uptrend", "rising", "peak", "safer", "recovering"]
    print(f"[WARN] nse_telegram_handler not found: {e}")

os.makedirs(config.LOG_DIR,    exist_ok=True)
os.makedirs(config.OUTPUT_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(config.LOG_DIR, "output.log")),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)


def _send(text, keyboard=None):
    if not getattr(config, 'TELEGRAM_TOKEN', None) or \
       not getattr(config, 'TELEGRAM_CHATID', None):
        log.warning("Telegram not configured")
        return False

    safe_text = re.sub(r'(?<!\\)-', r'\\-', text)
    url  = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage"
    data = {'chat_id': config.TELEGRAM_CHATID, 'text': safe_text, 'parse_mode': 'Markdown'}
    if keyboard:
        data['reply_markup'] = json.dumps(keyboard)
    try:
        r = requests.post(url, data=data, timeout=10)
        if r.status_code == 200:
            return True
        log.error(f"Telegram error {r.status_code}: {r.text[:300]}")
        data2 = dict(data)
        data2.pop('parse_mode', None)
        data2['text'] = text
        return requests.post(url, data=data2, timeout=10).status_code == 200
    except Exception as e:
        log.error(f"Telegram send failed: {e}")
        return False


def _fmt_fallback(df, report_date):
    d = report_date.strftime('%d\\-%b\\-%Y')
    msg = f"*NSE Momentum Scanner* \\- {d}\n\n"
    for i, (_, row) in enumerate(df.head(10).iterrows(), 1):
        sym   = str(row['symbol'])
        entry = float(row.get('entry', row.get('close', 0)))
        sl    = float(row.get('sl', 0))
        t1    = float(row.get('target1', 0))
        t2    = float(row.get('target2', 0))
        r1m   = float(row.get('return_1m_pct', 0))
        r3m   = float(row.get('return_3m_pct', 0))
        msg += f"*{i}. {sym}*\n"
        msg += f"  Entry {entry:,.0f} | SL {sl:,.0f} | T1 {t1:,.0f} | T2 {t2:,.0f}\n"
        msg += f"  1M {r1m:+.1f}% | 3M {r3m:+.1f}%\n\n"
    msg += f"Total: {len(df)} stocks scanned\n\n"
    msg += f"💡 Send /start to the bot to browse all stocks"
    return msg


def _fmt_bucketed(results_df, report_date):
    d = report_date.strftime('%d\\-%b\\-%Y')
    cat_groups = {}
    for _, row in results_df.iterrows():
        cat = str(row.get('category', 'rising'))
        cat_groups.setdefault(cat, []).append(row)

    summary = []
    for k in CATEGORY_ORDER:
        if k in cat_groups:
            m = CATEGORY_META.get(k, {})
            summary.append(f"{m.get('icon','•')} {len(cat_groups[k])} {m.get('label','').split()[0].lower()}")

    msg = f"*NSE MOMENTUM SCANNER*\nDate: {d}\n"
    msg += " | ".join(summary) + "\n" + f"{'─'*28}\n\n"

    rank = 1
    for k in CATEGORY_ORDER:
        stocks = cat_groups.get(k, [])
        if not stocks:
            continue
        m = CATEGORY_META.get(k, {})
        msg += f"*{m.get('icon','')} {m.get('label', k)}* ({len(stocks)})\n\n"
        for row in stocks:
            sym = str(row['symbol'])
            sc  = int(row.get('score', 0))
            e   = float(row.get('entry', row.get('close', 0)))
            sl  = float(row.get('sl', 0))
            t1  = float(row.get('target1', 0))
            t2  = float(row.get('target2', 0))
            r3  = float(row.get('return_3m_pct', 0))
            st  = int(row.get('streak', 0))
            stag = f" 🔥{st}d" if st >= 5 else ""
            msg += f"*{rank}. {sym}*  [{sc}/10]{stag}\n"
            msg += f"  Entry Rs {e:,.0f} | SL Rs {sl:,.0f}\n"
            msg += f"  T1 Rs {t1:,.0f} | T2 Rs {t2:,.0f} | 3M {r3:+.1f}%\n\n"
            rank += 1

    msg += f"{'─'*28}\nTotal: {len(results_df)} stocks\n"
    msg += "💡 Send /start to explore all views"
    return msg


def _fmt_summary(results_df, report_date):
    d = report_date.strftime('%d\\-%b\\-%Y')
    msg = f"*NSE MOMENTUM SCANNER*\nDate: {d} | {len(results_df)} stocks\n{'─'*28}\n\n"
    cat_groups = {}
    for _, row in results_df.iterrows():
        cat = str(row.get('category', 'rising'))
        cat_groups.setdefault(cat, []).append(row)
    for k in CATEGORY_ORDER:
        stocks = cat_groups.get(k, [])
        if not stocks:
            continue
        m = CATEGORY_META.get(k, {})
        names = [str(s['symbol']) for s in stocks[:3]]
        more = f" +{len(stocks)-3}" if len(stocks) > 3 else ""
        msg += f"{m.get('icon','')} *{m.get('label',k)}*: {', '.join(names)}{more}\n"
    msg += f"\n{'─'*28}\n💡 Send /start or /today for full details"
    return msg


def _save_pagination_json(results_df, report_date):
    if not _HANDLER_OK or save_scan_results is None:
        log.error("[BOT] Cannot save pagination JSON — handler not loaded")
        return
    df = results_df.copy()
    if 'return_3m_pct' in df.columns:
        df = df.sort_values('return_3m_pct', ascending=False).reset_index(drop=True)
    try:
        save_scan_results(df, report_date)
        log.info(f"[BOT] Pagination JSON saved → {RESULTS_FILE}")
        if RESULTS_FILE and os.path.exists(RESULTS_FILE):
            with open(RESULTS_FILE) as f:
                check = json.load(f)
            log.info(f"[BOT] JSON verified: {check['total_stocks']} stocks, date={check['scan_date']}")
    except Exception as e:
        log.error(f"[BOT] save_scan_results FAILED: {e}", exc_info=True)
        print(f"[BOT] ❌ Pagination JSON save FAILED: {e}")


def send_telegram(results_df, report_date):
    if not getattr(config, 'TELEGRAM_TOKEN', None) or \
       not getattr(config, 'TELEGRAM_CHATID', None):
        log.warning("Telegram not configured")
        return False
    if results_df.empty:
        log.warning("Empty DataFrame")
        return False

    _save_pagination_json(results_df, report_date)

    kb = {"inline_keyboard": [
        [{"text": "📊 Today",   "callback_data": "view_today"},
         {"text": "🆕 New",     "callback_data": "view_new"},
         {"text": "📉 Exit",    "callback_data": "view_exit"}],
        [{"text": "⚠️ Caution", "callback_data": "view_caution"},
         {"text": "🔥 Strong",  "callback_data": "view_strong"},
         {"text": "❓ Help",     "callback_data": "help"}],
    ]}

    sent = False
    has_cat = 'category' in results_df.columns

    if has_cat:
        df = results_df.copy()
        if 'return_3m_pct' in df.columns:
            df = df.sort_values('return_3m_pct', ascending=False)
        msg = _fmt_bucketed(df, report_date)
        if len(msg) <= 4000:
            if _send(msg, kb):
                log.info(f"Bucketed message sent: {len(results_df)} stocks")
                sent = True
        else:
            if _send(_fmt_summary(df, report_date), kb):
                sent = True

    if not sent:
        if _send(_fmt_fallback(results_df, report_date), kb):
            sent = True

    return sent


def save_excel(results_df, report_date):
    if results_df.empty:
        return None
    pattern = os.path.join(config.OUTPUT_DIR, "NSE_Scanner_*.xlsx")
    for f in glob.glob(pattern):
        try: os.remove(f)
        except Exception: pass

    df = results_df.copy()
    if 'return_3m_pct' in df.columns:
        df = df.sort_values('return_3m_pct', ascending=False).reset_index(drop=True)

    rename = {
        'symbol': 'Symbol', 'conviction': 'Conviction', 'score': 'TechScore',
        'return_1m_pct': '1M%', 'return_2m_pct': '2M%', 'return_3m_pct': '3M%',
        'close': 'Close', 'avg_volume': 'AvgVolume', 'delivery_pct': 'DelivPct',
        'entry': 'Entry', 'sl': 'StopLoss', 'sl_pct': 'SL%',
        'target1': 'Target1', 't1_pct': 'T1%', 'target2': 'Target2', 't2_pct': 'T2%',
        'rr': 'RR', 'momentum_score': 'MomScore', 'category': 'Category', 'streak': 'Streak',
        'news_tone': 'NewsTone', 'news_flags': 'NewsFlags', 'deal_flag': 'DealFlag', 'has_risk': 'HasRisk',
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    df.insert(0, 'Rank', range(1, len(df) + 1))

    order = ['Rank','Symbol','Conviction','Category','TechScore','Streak',
             '1M%','2M%','3M%','Entry','StopLoss','SL%','Target1','T1%','Target2','T2%','RR',
             'Close','AvgVolume','DelivPct','MomScore','NewsTone','NewsFlags','DealFlag','HasRisk']
    cols = [c for c in order if c in df.columns]
    df = df[cols]

    fname = f"NSE_Scanner_{report_date.strftime('%Y-%m-%d')}.xlsx"
    fpath = os.path.join(config.OUTPUT_DIR, fname)
    try:
        df.to_excel(fpath, sheet_name='Scanner_Results', index=False)
        log.info(f"Excel saved: {fpath}")
        return fpath
    except Exception as e:
        log.error(f"Excel save failed: {e}")
        return None


def generate_report(results_df, report_date=None):
    if report_date is None:
        report_date = date.today()

    print(f"\n{'='*56}\n  NSE OUTPUT — Generating Reports\n{'='*56}")

    results = {'excel_file': None, 'telegram_sent': False, 'date': report_date, 'stocks_count': len(results_df)}

    excel_file = save_excel(results_df, report_date)
    if excel_file:
        results['excel_file'] = excel_file
        print(f"Excel saved: {os.path.basename(excel_file)}")

    ok = send_telegram(results_df, report_date)
    results['telegram_sent'] = ok
    print(f"Telegram: {'sent ✅' if ok else 'failed/skipped ❌'}")

    hc = (results_df['conviction'] == 'HIGH CONVICTION').sum() if 'conviction' in results_df.columns else 0
    wl = (results_df['conviction'] == 'Watchlist').sum() if 'conviction' in results_df.columns else 0
    print(f"Stocks: {len(results_df)} | HC: {hc} | Watchlist: {wl}")

    if RESULTS_FILE and os.path.exists(RESULTS_FILE):
        try:
            with open(RESULTS_FILE, encoding="utf-8") as f:
                check = json.load(f)
            expected = report_date.strftime("%Y-%m-%d")
            found = check.get("scan_date")
            if found != expected:
                log.warning(f"JSON date mismatch: expected {expected}, found {found}")
        except Exception as e:
            log.warning(f"JSON check failed: {e}")

    return results


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="YYYY-MM-DD")
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()

    report_date = date.today()
    if args.date:
        report_date = datetime.strptime(args.date, "%Y-%m-%d").date()

    if args.test:
        df = pd.DataFrame({
            'symbol':        ['DIXON','KAYNES','JYOTHY','LALPATHLAB'],
            'conviction':    ['HIGH CONVICTION','HIGH CONVICTION','Watchlist','Watchlist'],
            'score':         [9, 8, 6, 5],
            'return_1m_pct': [8.5, 7.1, 4.2, 3.8],
            'return_2m_pct': [12.4, 11.8, 7.6, 6.9],
            'return_3m_pct': [21.6, 19.3, 11.4, 9.7],
            'close':  [8420, 5840, 540, 2840],
            'entry':  [8420, 5840, 540, 2840],
            'sl':     [8050, 5580, 518, 2710],
            'sl_pct': [-4.4, -4.5, -4.1, -4.6],
            'target1':[8790, 6100, 562, 2970],
            't1_pct': [4.4, 4.5, 4.1, 4.6],
            'target2':[9160, 6360, 584, 3100],
            't2_pct': [8.8, 9.0, 8.2, 9.2],
            'rr':     [2.0, 2.0, 2.0, 2.0],
            'momentum_score': [0.18, 0.16, 0.10, 0.09],
            'avg_volume':     [125430, 87210, 234100, 98200],
            'delivery_pct':   [61.2, 72.4, 48.3, 55.1],
            'fresh_cross':    [True, False, False, False],
            'category':       ['uptrend','rising','safer','recovering'],
            'streak':         [8, 5, 3, 1],
        })
        print("Using test data...")
    else:
        from nse_scanner import scan_stocks
        df = scan_stocks(scan_date=report_date)
        if df.empty:
            print("No scanner results")
            return

    generate_report(df, report_date)


if __name__ == "__main__":
    main()
