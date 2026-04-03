"""
nse_output.py — Report Generator (v6 — Forward Score Display)
=============================================================
WHAT CHANGED FROM v5:
  1. Stock cards now show forward-score signals instead of 3M return rank
  2. Score breakdown line added (HMA freshness, room, volume quality)
  3. Caution flags updated to include overextension + mature cross warnings
  4. Excel export updated: new columns (cross_age, dist_pct, acc_days etc.)
  5. 3M return shown as reference only (not as ranking/sorting key)
  6. Sort order in Excel/Telegram follows forward score, not 3M return

Everything else (Telegram send, pagination JSON, tracker integration,
file structure, fallbacks) unchanged.
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
        "uptrend":    {"icon": "🚀", "label": "Clear Uptrend Confirmed"},
        "peak":       {"icon": "🔝", "label": "Close to Their Peak"},
        "recovering": {"icon": "📉", "label": "Recovering from a Fall"},
        "safer":      {"icon": "🛡️", "label": "Safer Bets with Good Reward"},
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


# ═══════════════════════════════════════════════════════════════════════════
# TELEGRAM SEND HELPER (unchanged)
# ═══════════════════════════════════════════════════════════════════════════

def _send(text, keyboard=None):
    if not getattr(config, 'TELEGRAM_TOKEN', None) or \
       not getattr(config, 'TELEGRAM_CHATID', None):
        log.warning("Telegram not configured")
        return False

    safe_text = re.sub(r'(?<!\\)-', r'\\-', text)
    url  = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage"
    data = {
        'chat_id':    config.TELEGRAM_CHATID,
        'text':       safe_text,
        'parse_mode': 'Markdown',
    }
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


# ═══════════════════════════════════════════════════════════════════════════
# SCORE SIGNAL LINE — new helper for forward-score display
# Shows what drove the score in a compact format
# ═══════════════════════════════════════════════════════════════════════════

def _fmt_signal_line(row) -> str:
    """
    Returns a compact signal summary line for a stock.
    Examples:
      "Fresh cross 3d | 4% from HMA55 | Accum vol | Sector ✅"
      "Cross 18d ago | 12% stretched | Dist vol ⚠️"
    """
    parts = []

    cross_age    = int(row.get('cross_age', 999))
    dist_pct     = float(row.get('dist_pct', 0))
    fresh_cross  = bool(row.get('fresh_cross', False))
    overextended = bool(row.get('overextended', False))
    acc_days     = int(row.get('acc_days', 0))
    dist_days    = int(row.get('dist_days', 0))
    obv_dir      = str(row.get('obv_dir', 'flat'))
    sector_bias  = int(row.get('sector_bias', 0))

    # HMA cross age
    if cross_age == -1 or cross_age == 999:
        parts.append("No fresh cross")
    elif fresh_cross:
        parts.append(f"🟢 Fresh cross {cross_age}d ago")
    else:
        parts.append(f"Cross {cross_age}d ago")

    # Distance from mean
    if overextended:
        parts.append(f"⚠️ {dist_pct:.0f}% stretched")
    elif dist_pct <= 5.0:
        parts.append(f"🟢 {dist_pct:.1f}% from HMA55")
    else:
        parts.append(f"{dist_pct:.1f}% from HMA55")

    # Volume quality
    if acc_days >= 4 and obv_dir == 'rising':
        parts.append("🟢 Accum vol")
    elif dist_days >= 4 or obv_dir == 'falling':
        parts.append("🔴 Dist vol")
    else:
        parts.append("Vol neutral")

    # Sector
    if sector_bias == 1:
        parts.append("Sector ✅")
    elif sector_bias == -1:
        parts.append("Sector ❌")

    return " | ".join(parts)


def _fmt_cross_tag(row) -> str:
    """Short tag for the score line: [Fresh] or [18d] or [Mature]."""
    cross_age = int(row.get('cross_age', 999))
    if cross_age <= 10:
        return "🟢Fresh"
    elif cross_age <= 20:
        return "🟡18d"
    elif cross_age < 999:
        return f"⚪{cross_age}d"
    return ""


# ═══════════════════════════════════════════════════════════════════════════
# FORMAT: FALLBACK (plain list — minimal)
# ═══════════════════════════════════════════════════════════════════════════

def _fmt_fallback(df, report_date):
    d = report_date.strftime('%d\\-%b\\-%Y')
    msg = f"*NSE Momentum Scanner* \\- {d}\n\n"
    for i, (_, row) in enumerate(df.head(10).iterrows(), 1):
        sym   = str(row['symbol'])
        entry = float(row.get('entry', row.get('close', 0)))
        sl    = float(row.get('sl', 0))
        t1    = float(row.get('target1', 0))
        t2    = float(row.get('target2', 0))
        sc    = int(row.get('score', 0))
        r3m   = float(row.get('return_3m_pct', 0))
        cross_tag = _fmt_cross_tag(row)
        msg += f"*{i}. {sym}*  [{sc}/10] {cross_tag}\n"
        msg += f"  Entry ₹{entry:,.0f} | SL ₹{sl:,.0f} | T1 ₹{t1:,.0f} | T2 ₹{t2:,.0f}\n"
        msg += f"  3M {r3m:+.1f}% (ref only)\n\n"
    msg += f"Total: {len(df)} stocks\n\n"
    msg += "Send /start to browse all stocks"
    return msg


# ═══════════════════════════════════════════════════════════════════════════
# FORMAT: BUCKETED (main Telegram message)
# Updated to show forward signals instead of 3M return as rank driver
# ═══════════════════════════════════════════════════════════════════════════

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
            summary.append(
                f"{m.get('icon', '.')} {len(cat_groups[k])} "
                f"{m.get('label', '').split()[0].lower()}"
            )

    msg = f"*NSE SCANNER — Forward Score*\nDate: {d}\n"
    msg += " | ".join(summary) + "\n"
    msg += f"{'_' * 28}\n\n"

    rank = 1
    for k in CATEGORY_ORDER:
        stocks = cat_groups.get(k, [])
        if not stocks:
            continue
        m = CATEGORY_META.get(k, {})
        msg += f"*{m.get('icon', '')} {m.get('label', k)}* ({len(stocks)})\n\n"

        for row in stocks:
            sym  = str(row['symbol'])
            sc   = int(row.get('score', 0))
            e    = float(row.get('entry', row.get('close', 0)))
            sl   = float(row.get('sl', 0))
            t1   = float(row.get('target1', 0))
            t2   = float(row.get('target2', 0))
            r3   = float(row.get('return_3m_pct', 0))
            st   = int(row.get('streak', 0))
            stag = f" 🔥{st}d" if st >= 5 else ""

            cross_tag = _fmt_cross_tag(row)
            cross_tag_str = f" {cross_tag}" if cross_tag else ""

            msg += f"*{rank}. {sym}*  [{sc}/10]{stag}{cross_tag_str}\n"
            msg += f"  Entry ₹{e:,.0f} | SL ₹{sl:,.0f}\n"
            msg += f"  T1 ₹{t1:,.0f} | T2 ₹{t2:,.0f}\n"

            # Signal line (new — shows what's driving the score)
            if any(k in row.index for k in ['cross_age', 'dist_pct', 'acc_days']):
                sig_line = _fmt_signal_line(row)
                if sig_line:
                    msg += f"  _{sig_line}_\n"

            msg += f"  3M {r3:+.1f}% \\(ref\\)\n\n"
            rank += 1

    msg += f"{'_' * 28}\nTotal: {len(results_df)} stocks\n"
    msg += "Send /start to explore all views"
    return msg


# ═══════════════════════════════════════════════════════════════════════════
# FORMAT: SUMMARY (unchanged logic, updated text)
# ═══════════════════════════════════════════════════════════════════════════

def _fmt_summary(results_df, report_date):
    d = report_date.strftime('%d\\-%b\\-%Y')
    msg = (f"*NSE SCANNER — Forward Score*\n"
           f"Date: {d} | {len(results_df)} stocks\n"
           f"{'_' * 28}\n\n")
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
        more  = f" +{len(stocks) - 3}" if len(stocks) > 3 else ""
        msg += f"{m.get('icon', '')} *{m.get('label', k)}*: {', '.join(names)}{more}\n"
    msg += f"\n{'_' * 28}\nSend /start or /today for full details"
    return msg


# ═══════════════════════════════════════════════════════════════════════════
# PAGINATION JSON SAVE + TRACKER UPDATE (unchanged)
# ═══════════════════════════════════════════════════════════════════════════

def _save_pagination_json(results_df, report_date):
    if not _HANDLER_OK or save_scan_results is None:
        log.error("[BOT] Cannot save pagination JSON — handler not loaded")
        return

    df = results_df.copy()
    # ── Sort by forward score (HIGH CONVICTION first, then score desc) ────
    if 'score' in df.columns:
        if 'conviction' in df.columns:
            conv_order = {
                'HIGH CONVICTION': 0,
                'Watchlist':        1,
                '':                 2,
            }
            df['_conv_rank'] = df['conviction'].map(
                lambda c: conv_order.get(c, 2)
            )
            df = df.sort_values(
                ['_conv_rank', 'score'], ascending=[True, False]
            ).drop(columns=['_conv_rank'])
        else:
            df = df.sort_values('score', ascending=False)
    df = df.reset_index(drop=True)

    try:
        save_scan_results(df, report_date)
        log.info(f"[BOT] Pagination JSON saved -> {RESULTS_FILE}")

        if RESULTS_FILE and os.path.exists(RESULTS_FILE):
            with open(RESULTS_FILE) as f:
                check = json.load(f)
            log.info(
                f"[BOT] JSON verified: {check['total_stocks']} stocks, "
                f"date={check['scan_date']}"
            )

            # ── Update signal tracker ─────────────────────────────────────
            try:
                from nse_signal_tracker import update_tracker
                from nse_telegram_handler import load_history as _load_hist
                _hist    = _load_hist()
                _summary = update_tracker(
                    check['stocks'], check['scan_date'], _hist
                )
                log.info(f"[TRACKER] {_summary}")
                print(f"[TRACKER] {_summary}")
            except Exception as _te:
                log.warning(f"[TRACKER] Skipped: {_te}")
                print(f"[TRACKER] Skipped: {_te}")

    except Exception as e:
        log.error(f"[BOT] save_scan_results FAILED: {e}", exc_info=True)
        print(f"[BOT] Pagination JSON save FAILED: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# TELEGRAM SEND (updated sort order)
# ═══════════════════════════════════════════════════════════════════════════

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
        [{"text": "Today",   "callback_data": "view_today"},
         {"text": "New",     "callback_data": "view_new"},
         {"text": "Exit",    "callback_data": "view_exit"}],
        [{"text": "Caution", "callback_data": "view_caution"},
         {"text": "Strong",  "callback_data": "view_strong"},
         {"text": "Help",    "callback_data": "help"}],
    ]}

    sent     = False
    has_cat  = 'category' in results_df.columns

    if has_cat:
        df = results_df.copy()
        # Sort by forward score (not 3M return)
        if 'score' in df.columns:
            df = df.sort_values('score', ascending=False)
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


# ═══════════════════════════════════════════════════════════════════════════
# EXCEL EXPORT (updated columns to include forward-score signals)
# ═══════════════════════════════════════════════════════════════════════════

def save_excel(results_df, report_date):
    if results_df.empty:
        return None

    pattern = os.path.join(config.OUTPUT_DIR, "NSE_Scanner_*.xlsx")
    for f in glob.glob(pattern):
        try:
            os.remove(f)
        except Exception:
            pass

    df = results_df.copy()

    # Sort by forward score
    if 'score' in df.columns:
        if 'conviction' in df.columns:
            conv_order = {'HIGH CONVICTION': 0, 'Watchlist': 1, '': 2}
            df['_cr'] = df['conviction'].map(lambda c: conv_order.get(c, 2))
            df = df.sort_values(['_cr', 'score'], ascending=[True, False]).drop(columns=['_cr'])
        else:
            df = df.sort_values('score', ascending=False)
    df = df.reset_index(drop=True)

    rename = {
        'symbol':        'Symbol',
        'conviction':    'Conviction',
        'score':         'FwdScore',         # renamed: forward score not tech score
        'return_1m_pct': '1M%',
        'return_2m_pct': '2M%',
        'return_3m_pct': '3M% (ref)',        # labelled as reference
        'close':         'Close',
        'avg_volume':    'AvgVolume',
        'delivery_pct':  'DelivPct',
        'entry':         'Entry',
        'sl':            'StopLoss',
        'sl_pct':        'SL%',
        'target1':       'Target1',
        't1_pct':        'T1%',
        'target2':       'Target2',
        't2_pct':        'T2%',
        'rr':            'RR',
        'momentum_score':'MomScore',
        'category':      'Category',
        'streak':        'Streak',
        # New forward-score columns
        'cross_age':     'HMA_CrossAge',
        'dist_pct':      'Dist_HMA55%',
        'fresh_cross':   'FreshCross',
        'overextended':  'Overextended',
        'acc_days':      'AccumDays',
        'dist_days':     'DistribDays',
        'obv_dir':       'OBV_Dir',
        'del_trend':     'DelivTrend',
        'sector_bias':   'SectorBias',
        'pts_hma':       'Pts_HMA',
        'pts_dist':      'Pts_Dist',
        'pts_vol':       'Pts_Vol',
        'pts_rsi':       'Pts_RSI',
        'pts_macd':      'Pts_MACD',
        'pts_sector':    'Pts_Sector',
        'pts_rr':        'Pts_RR',
        'pen_overext':   'Pen_Overext',
        'pen_decel':     'Pen_Decel',
        'rsi':           'RSI',
        # Legacy (keep for compatibility)
        'news_tone':     'NewsTone',
        'news_flags':    'NewsFlags',
        'deal_flag':     'DealFlag',
        'has_risk':      'HasRisk',
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    df.insert(0, 'Rank', range(1, len(df) + 1))

    order = [
        'Rank', 'Symbol', 'Conviction', 'Category', 'FwdScore', 'Streak',
        'HMA_CrossAge', 'Dist_HMA55%', 'FreshCross', 'Overextended',
        'AccumDays', 'DistribDays', 'OBV_Dir', 'DelivTrend', 'SectorBias',
        'Entry', 'StopLoss', 'SL%', 'Target1', 'T1%', 'Target2', 'T2%', 'RR',
        '1M%', '2M%', '3M% (ref)',
        'Close', 'AvgVolume', 'DelivPct', 'RSI', 'MomScore',
        'Pts_HMA', 'Pts_Dist', 'Pts_Vol', 'Pts_RSI', 'Pts_MACD',
        'Pts_Sector', 'Pts_RR', 'Pen_Overext', 'Pen_Decel',
        'NewsTone', 'NewsFlags', 'DealFlag', 'HasRisk',
    ]
    cols = [c for c in order if c in df.columns]
    df   = df[cols]

    fname = f"NSE_Scanner_{report_date.strftime('%Y-%m-%d')}.xlsx"
    fpath = os.path.join(config.OUTPUT_DIR, fname)
    try:
        df.to_excel(fpath, sheet_name='ForwardScore_Results', index=False)
        log.info(f"Excel saved: {fpath}")
        return fpath
    except Exception as e:
        log.error(f"Excel save failed: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════
# MAIN GENERATE REPORT (unchanged interface)
# ═══════════════════════════════════════════════════════════════════════════

def generate_report(results_df, report_date=None):
    if report_date is None:
        report_date = date.today()

    print(f"\n{'=' * 56}\n  NSE OUTPUT — Generating Reports\n{'=' * 56}")

    results = {
        'excel_file':     None,
        'telegram_sent':  False,
        'date':           report_date,
        'stocks_count':   len(results_df),
    }

    excel_file = save_excel(results_df, report_date)
    if excel_file:
        results['excel_file'] = excel_file
        print(f"Excel saved: {os.path.basename(excel_file)}")

    ok = send_telegram(results_df, report_date)
    results['telegram_sent'] = ok
    print(f"Telegram: {'sent' if ok else 'failed/skipped'}")

    hc = (results_df['conviction'] == 'HIGH CONVICTION').sum() \
         if 'conviction' in results_df.columns else 0
    wl = (results_df['conviction'] == 'Watchlist').sum() \
         if 'conviction' in results_df.columns else 0
    print(f"Stocks: {len(results_df)} | HC: {hc} | Watchlist: {wl}")

    # Verify JSON date
    if RESULTS_FILE and os.path.exists(RESULTS_FILE):
        try:
            with open(RESULTS_FILE, encoding="utf-8") as f:
                check = json.load(f)
            expected = report_date.strftime("%Y-%m-%d")
            found    = check.get("scan_date")
            if found != expected:
                log.warning(
                    f"JSON date mismatch: expected {expected}, found {found}"
                )
        except Exception as e:
            log.warning(f"JSON check failed: {e}")

    return results


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════

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
        # Test data with forward-score fields
        df = pd.DataFrame({
            'symbol':        ['FRESHSTOCK', 'DIPBUY', 'KAYNES', 'NEWENTRY', 'DIXON'],
            'conviction':    ['HIGH CONVICTION', 'HIGH CONVICTION',
                              'HIGH CONVICTION', 'Watchlist', 'Watchlist'],
            'score':         [9, 8, 8, 6, 6],
            'return_1m_pct': [8.5, 3.2, 7.1, 4.1, 6.8],
            'return_2m_pct': [12.4, 5.1, 11.8, 7.2, 10.4],
            'return_3m_pct': [8.0, 5.0, 19.3, 4.0, 21.6],  # ref only
            'close':  [420, 280, 5840, 1100, 8420],
            'entry':  [420, 280, 5840, 1100, 8420],
            'sl':     [405, 270, 5600, 1055, 8060],
            'sl_pct': [-3.6, -3.6, -4.1, -4.1, -4.3],
            'target1':[435, 290, 6080, 1145, 8780],
            't1_pct': [3.6, 3.6, 4.1, 4.1, 4.3],
            'target2':[450, 300, 6320, 1190, 9140],
            't2_pct': [7.1, 7.1, 8.2, 8.2, 8.5],
            'rr':     [2.0, 2.0, 2.0, 2.0, 2.0],
            'momentum_score': [0.08, 0.05, 0.16, 0.04, 0.18],
            'avg_volume':     [125430, 87210, 87210, 45000, 125430],
            'delivery_pct':   [61.2, 58.0, 72.4, 48.3, 61.2],
            # Forward score signals
            'cross_age':      [4, 7, 14, 3, 38],
            'fresh_cross':    [True, True, False, True, False],
            'dist_pct':       [3.2, 2.8, 6.4, 4.1, 18.2],
            'overextended':   [False, False, False, False, True],
            'acc_days':       [4, 3, 4, 3, 1],
            'dist_days':      [0, 1, 0, 1, 3],
            'obv_dir':        ['rising', 'rising', 'rising', 'flat', 'falling'],
            'del_trend':      ['rising', 'rising', 'rising', 'flat', 'flat'],
            'sector_bias':    [1, 0, 1, 0, 0],
            'pts_hma':        [2, 2, 1, 2, 0],
            'pts_dist':       [2, 2, 1, 2, -1],
            'pts_vol':        [2, 2, 2, 1, 0],
            'pts_rsi':        [1, 1, 1, 0, 0],
            'pts_macd':       [1, 1, 1, 1, 1],
            'pts_sector':     [1, 0, 1, 0, 0],
            'pts_rr':         [1, 1, 1, 1, 1],
            'pen_overext':    [0, 0, 0, 0, -1],
            'pen_decel':      [0, 0, 0, 0, 0],
            'rsi':            [52.1, 48.3, 55.2, 44.1, 67.8],
            'category':       ['uptrend', 'uptrend', 'rising', 'uptrend', 'peak'],
            'streak':         [3, 1, 5, 1, 8],
        })
        print("Using test data (forward-score format)...")
        print("\nNote: DIXON shows as Caution — overextended 18.2% above HMA55, "
              "cross 38d ago, distribution volume")
        print("      FRESHSTOCK leads — fresh cross 4d, 3.2% from HMA55, "
              "accumulation volume, sector tailwind\n")
    else:
        from nse_scanner import scan_stocks
        df = scan_stocks(scan_date=report_date)
        if df.empty:
            print("No scanner results")
            return

    generate_report(df, report_date)


if __name__ == "__main__":
    main()
