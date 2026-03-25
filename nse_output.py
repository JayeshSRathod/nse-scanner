"""
nse_output.py — Report Generator (v4 — bot pagination fix)
===========================================================

Key fixes vs v3:
  1. save_scan_results() error is NO LONGER silently swallowed — it logs
     and shows the error so you know if the JSON wasn't written.
  2. Results sorted descending by 3M return before saving JSON + Excel.
  3. Old Excel files (NSE_Scanner_*.xlsx) deleted before writing new one.
  4. RESULTS_FILE path logged at startup so you can confirm location.
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

# Load handler for pagination storage
try:
    from nse_telegram_handler import save_scan_results, RESULTS_FILE, PARSE_MODE
    _HANDLER_OK = True
    print(f"[OUTPUT] Pagination JSON will be saved to: {RESULTS_FILE}")
except ImportError as e:
    save_scan_results = None
    RESULTS_FILE      = None
    PARSE_MODE        = "HTML"
    _HANDLER_OK       = False
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


# ── Telegram send (plain Markdown for daily notification) ─────────────────────

def _send(text: str, keyboard: dict = None) -> bool:
    """Send one Telegram message.  Falls back to plain text on parse failure."""
    if not getattr(config, 'TELEGRAM_TOKEN', None) or \
       not getattr(config, 'TELEGRAM_CHATID', None):
        log.warning("Telegram not configured")
        return False

    # Escape hyphens to avoid Markdown list-bullet parse errors
    safe_text = re.sub(r'(?<!\\)-', r'\\-', text)

    url  = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage"
    data = {
        'chat_id'    : config.TELEGRAM_CHATID,
        'text'       : safe_text,
        'parse_mode' : 'Markdown',
    }
    if keyboard:
        data['reply_markup'] = json.dumps(keyboard)

    try:
        r = requests.post(url, data=data, timeout=10)
        if r.status_code == 200:
            return True

        log.error(f"Telegram error {r.status_code}: {r.text[:300]}")
        # Retry without parse_mode (plain text fallback)
        data2 = dict(data)
        data2.pop('parse_mode', None)
        # un-escape for plain text
        data2['text'] = text
        r2 = requests.post(url, data=data2, timeout=10)
        return r2.status_code == 200

    except Exception as e:
        log.error(f"Telegram send failed: {e}")
        return False


# ── Formatters ────────────────────────────────────────────────────────────────

def _fmt_hc(df: pd.DataFrame, report_date: date) -> str:
    d   = report_date.strftime("%d\\-%b\\-%Y")
    msg = f"*NSE MOMENTUM SCANNER*\n"
    msg += f"Date: {d}\n"
    msg += f"{'─'*28}\n"
    msg += f"*HIGH CONVICTION SIGNALS*\n"
    msg += f"{'─'*28}\n\n"

    for i, (_, row) in enumerate(df.iterrows(), 1):
        sym    = str(row['symbol'])
        score  = int(row.get('score', 0))
        r1m    = float(row.get('return_1m_pct', 0))
        r3m    = float(row.get('return_3m_pct', 0))
        entry  = float(row.get('entry', row.get('close', 0)))
        sl     = float(row.get('sl', 0))
        sl_pct = float(row.get('sl_pct', 0))
        t1     = float(row.get('target1', 0))
        t1_pct = float(row.get('t1_pct', 0))
        t2     = float(row.get('target2', 0))
        t2_pct = float(row.get('t2_pct', 0))
        cross  = " X" if row.get('fresh_cross', False) else ""

        msg += f"*{i}. {sym}*{cross}  [{score}/10]\n"
        msg += f"  Entry  : Rs {entry:,.2f}\n"
        msg += f"  SL     : Rs {sl:,.2f}  ({sl_pct:.1f}%)\n"
        msg += f"  T1     : Rs {t1:,.2f}  (+{t1_pct:.1f}%)  1 month\n"
        msg += f"  T2     : Rs {t2:,.2f}  (+{t2_pct:.1f}%)  3 months\n"
        msg += f"  Return : 1M {r1m:+.1f}%  3M {r3m:+.1f}%\n"
        msg += f"  RR     : 1:2\n"
        msg += f"{'─'*28}\n\n"

    msg += "X = Fresh HMA20 x HMA55 cross\n"
    msg += "SL = HMA55 or 5\\-day low\n"
    msg += "T1 = book 50% | T2 = exit 50%"
    return msg


def _fmt_watchlist(df: pd.DataFrame, report_date: date, hc_count: int) -> str:
    d   = report_date.strftime("%d\\-%b\\-%Y")
    msg = f"*WATCHLIST SIGNALS* — {d}\n"
    msg += f"Score 5\\-7 | Monitor for entry\n"
    msg += f"{'─'*28}\n\n"

    for i, (_, row) in enumerate(df.iterrows(), 1):
        sym   = str(row['symbol'])
        score = int(row.get('score', 0))
        entry = float(row.get('entry', row.get('close', 0)))
        sl    = float(row.get('sl', 0))
        t1    = float(row.get('target1', 0))
        t2    = float(row.get('target2', 0))
        r3m   = float(row.get('return_3m_pct', 0))

        msg += f"*{i}. {sym}*  [{score}/10]\n"
        msg += f"  Entry {entry:,.0f} | SL {sl:,.0f} | T1 {t1:,.0f} | T2 {t2:,.0f} | 3M {r3m:+.1f}%\n\n"

    total = hc_count + len(df)
    msg += f"{'─'*28}\n"
    msg += f"Total: {total} signals | HC: {hc_count} | Watchlist: {len(df)}\n"
    msg += f"Next scan: Tomorrow 6:45 PM IST\n\n"
    msg += f"💡 Send /start to the bot to browse all stocks"
    return msg


def _fmt_fallback(df: pd.DataFrame, report_date: date) -> str:
    d   = report_date.strftime("%d\\-%b\\-%Y")
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


# ── Pagination JSON save ───────────────────────────────────────────────────────

def _save_pagination_json(results_df: pd.DataFrame, report_date: date):
    """
    Save JSON for bot pagination.

    THIS MUST NOT SILENTLY FAIL — logs full error if it breaks
    so you know why /start isn't working.
    """
    if not _HANDLER_OK or save_scan_results is None:
        log.error("[BOT] Cannot save pagination JSON — nse_telegram_handler not loaded")
        return

    # Sort descending by 3M return before saving
    df = results_df.copy()
    if 'return_3m_pct' in df.columns:
        df = df.sort_values('return_3m_pct', ascending=False).reset_index(drop=True)
        log.info(f"[BOT] Sorted {len(df)} stocks by 3M return (desc) before saving")
    else:
        log.warning("[BOT] 'return_3m_pct' column not found — saving unsorted")

    try:
        save_scan_results(df, report_date)
        log.info(f"[BOT] Pagination JSON saved → {RESULTS_FILE}")
        print(f"[BOT] ✅ Pagination JSON saved: {RESULTS_FILE}")

        # Quick sanity check — read it back
        if RESULTS_FILE and os.path.exists(RESULTS_FILE):
            with open(RESULTS_FILE) as f:
                check = json.load(f)
            log.info(f"[BOT] JSON verified: {check['total_stocks']} stocks, date={check['scan_date']}")
        else:
            log.error(f"[BOT] JSON file not found after save: {RESULTS_FILE}")

    except Exception as e:
        # DO NOT SILENTLY PASS — this is why /start was broken before
        log.error(f"[BOT] ❌ save_scan_results FAILED: {e}", exc_info=True)
        print(f"[BOT] ❌ Pagination JSON save FAILED: {e}")
        print(f"[BOT]    Bot /start will NOT work until this is fixed!")


# ── Telegram sender ───────────────────────────────────────────────────────────

def send_telegram(results_df: pd.DataFrame, report_date: date) -> bool:
    """
    Send scanner results to Telegram.
    Also saves pagination JSON for the bot.
    """
    if not getattr(config, 'TELEGRAM_TOKEN', None) or \
       not getattr(config, 'TELEGRAM_CHATID', None):
        log.warning("Telegram not configured")
        return False

    if results_df.empty:
        log.warning("Empty DataFrame — nothing to send")
        return False

    # ── STEP 1: Save pagination JSON for /start ───────────────
    # This is done FIRST and SEPARATELY from message formatting
    # so a formatting error cannot block the JSON save.
    _save_pagination_json(results_df, report_date)

    # ── STEP 2: Format and send Telegram notification ─────────
    sent = False

    has_conviction = (
        'conviction' in results_df.columns and
        results_df['conviction'].notna().any() and
        results_df['conviction'].astype(str).str.len().max() > 0
    )

    if has_conviction:
        hc_df = results_df[results_df['conviction'] == 'HIGH CONVICTION'].copy()
        wl_df = results_df[results_df['conviction'] == 'Watchlist'].copy()

        # Sort both by 3M return desc
        if 'return_3m_pct' in hc_df.columns:
            hc_df = hc_df.sort_values('return_3m_pct', ascending=False)
        if 'return_3m_pct' in wl_df.columns:
            wl_df = wl_df.sort_values('return_3m_pct', ascending=False)

        # Message 1 — HIGH CONVICTION
        if not hc_df.empty:
            kb = {"inline_keyboard": [[
                {"text": "📋 Watchlist",    "callback_data": "list"},
                {"text": "📱 Browse All",  "callback_data": "sort_3m"},
                {"text": "❓ Help",         "callback_data": "help"},
            ]]}
            if _send(_fmt_hc(hc_df, report_date), kb):
                log.info(f"HC message sent: {len(hc_df)} stocks")
                sent = True

        # Message 2 — Watchlist
        if not wl_df.empty:
            kb = {"inline_keyboard": [[
                {"text": "Next ➡️",        "callback_data": "next"},
                {"text": "📱 Browse All",  "callback_data": "sort_3m"},
                {"text": "❓ Help",         "callback_data": "help"},
            ]]}
            if _send(_fmt_watchlist(wl_df, report_date, len(hc_df)), kb):
                log.info(f"Watchlist message sent: {len(wl_df)} stocks")
                sent = True

    # Fallback
    if not sent:
        kb = {"inline_keyboard": [[
            {"text": "Next ➡️",       "callback_data": "next"},
            {"text": "📱 Browse All", "callback_data": "sort_3m"},
            {"text": "❓ Help",        "callback_data": "help"},
        ]]}
        if _send(_fmt_fallback(results_df, report_date), kb):
            log.info("Fallback message sent")
            sent = True

    return sent


# ── Excel builder ─────────────────────────────────────────────────────────────

def save_excel(results_df: pd.DataFrame, report_date: date) -> str:
    """
    Save Excel report.
    - Deletes previous NSE_Scanner_*.xlsx files first.
    - Sorts descending by 3M return.
    """
    if results_df.empty:
        return None

    # ── Delete old Excel files ────────────────────────────────
    pattern  = os.path.join(config.OUTPUT_DIR, "NSE_Scanner_*.xlsx")
    old_files = glob.glob(pattern)
    for f in old_files:
        try:
            os.remove(f)
            log.info(f"Deleted old Excel: {os.path.basename(f)}")
        except Exception as e:
            log.warning(f"Could not delete {f}: {e}")

    # ── Sort by 3M return desc ────────────────────────────────
    df = results_df.copy()
    if 'return_3m_pct' in df.columns:
        df = df.sort_values('return_3m_pct', ascending=False).reset_index(drop=True)

    rename = {
        'symbol'        : 'Symbol',
        'conviction'    : 'Conviction',
        'score'         : 'TechScore',
        'return_1m_pct' : '1M%',
        'return_2m_pct' : '2M%',
        'return_3m_pct' : '3M%',
        'close'         : 'Close',
        'avg_volume'    : 'AvgVolume',
        'delivery_pct'  : 'DelivPct',
        'entry'         : 'Entry',
        'sl'            : 'StopLoss',
        'sl_pct'        : 'SL%',
        'target1'       : 'Target1',
        't1_pct'        : 'T1%',
        'target2'       : 'Target2',
        't2_pct'        : 'T2%',
        'rr'            : 'RR',
        'momentum_score': 'MomScore',
        'news_tone'     : 'NewsTone',
        'news_flags'    : 'NewsFlags',
        'deal_flag'     : 'DealFlag',
        'has_risk'      : 'HasRisk',
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    df.insert(0, 'Rank', range(1, len(df) + 1))

    order = [
        'Rank', 'Symbol', 'Conviction', 'TechScore',
        '1M%', '2M%', '3M%',
        'Entry', 'StopLoss', 'SL%', 'Target1', 'T1%', 'Target2', 'T2%', 'RR',
        'Close', 'AvgVolume', 'DelivPct', 'MomScore',
        'NewsTone', 'NewsFlags', 'DealFlag', 'HasRisk',
    ]
    cols = [c for c in order if c in df.columns]
    df   = df[cols]

    fname = f"NSE_Scanner_{report_date.strftime('%Y-%m-%d')}.xlsx"
    fpath = os.path.join(config.OUTPUT_DIR, fname)

    try:
        df.to_excel(fpath, sheet_name='Scanner_Results', index=False)
        log.info(f"Excel saved: {fpath}")
        return fpath
    except Exception as e:
        log.error(f"Excel save failed: {e}")
        return None


# ── Main entry point ──────────────────────────────────────────────────────────

def generate_report(results_df: pd.DataFrame, report_date: date = None) -> dict:
    if report_date is None:
        report_date = date.today()

    print(f"\n{'='*56}")
    print("  NSE OUTPUT — Generating Reports")
    print(f"{'='*56}")

    results = {
        'excel_file'     : None,
        'telegram_sent'  : False,
        'date'           : report_date,
        'stocks_count'   : len(results_df),
    }

    # Excel
    excel_file = save_excel(results_df, report_date)
    if excel_file:
        results['excel_file'] = excel_file
        print(f"Excel saved: {os.path.basename(excel_file)}")
    else:
        print("Excel failed")

    # Telegram + pagination JSON
    ok = send_telegram(results_df, report_date)
    results['telegram_sent'] = ok
    print(f"Telegram: {'sent ✅' if ok else 'failed/skipped ❌'}")

    hc = (results_df['conviction'] == 'HIGH CONVICTION').sum() \
         if 'conviction' in results_df.columns else 0
    wl = (results_df['conviction'] == 'Watchlist').sum() \
         if 'conviction' in results_df.columns else 0
    print(f"Stocks: {len(results_df)} | HC: {hc} | Watchlist: {wl}")
    print(f"Bot JSON: {RESULTS_FILE or 'not configured'}")

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
            'symbol'        : ['DIXON',   'KAYNES',  'JYOTHY',      'LALPATHLAB'],
            'conviction'    : ['HIGH CONVICTION', 'HIGH CONVICTION', 'Watchlist', 'Watchlist'],
            'score'         : [9,          8,         6,              5],
            'return_1m_pct' : [8.5,        7.1,       4.2,            3.8],
            'return_2m_pct' : [12.4,       11.8,      7.6,            6.9],
            'return_3m_pct' : [21.6,       19.3,      11.4,           9.7],
            'close'         : [8420,       5840,      540,            2840],
            'entry'         : [8420,       5840,      540,            2840],
            'sl'            : [8050,       5580,      518,            2710],
            'sl_pct'        : [-4.4,       -4.5,      -4.1,           -4.6],
            'target1'       : [8790,       6100,      562,            2970],
            't1_pct'        : [4.4,        4.5,       4.1,            4.6],
            'target2'       : [9160,       6360,      584,            3100],
            't2_pct'        : [8.8,        9.0,       8.2,            9.2],
            'rr'            : [2.0,        2.0,       2.0,            2.0],
            'momentum_score': [0.18,       0.16,      0.10,           0.09],
            'avg_volume'    : [125430,     87210,     234100,         98200],
            'delivery_pct'  : [61.2,       72.4,      48.3,           55.1],
            'fresh_cross'   : [True,       False,     False,          False],
        })
        print("Using test data...")
    else:
        from nse_scanner import scan_stocks
        df = scan_stocks(scan_date=report_date)
        if df.empty:
            print("No scanner results")
            return

    generate_report(df, report_date)
    
# ── HARD GUARANTEE: Pagination JSON must exist & be fresh ──
if RESULTS_FILE:
    if not os.path.exists(RESULTS_FILE):
        raise RuntimeError(
            "telegram_last_scan.json was NOT created — aborting pipeline"
        )

    with open(RESULTS_FILE, encoding="utf-8") as f:
        check = json.load(f)

    expected = report_date.strftime("%Y-%m-%d")
    found = check.get("scan_date")

    if found != expected:
        raise RuntimeError(
            f"telegram_last_scan.json STALE "
            f"(expected {expected}, found {found})"
        )


if __name__ == "__main__":
    main()
