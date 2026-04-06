"""
nse_output.py — Report Generator (v7 — Option C Morning Message)
=================================================================
WHAT CHANGED FROM v6:

  6 AM MORNING MESSAGE — Option C:
    PRIME stocks → Full detail cards (max 3)
    All other situations → Compact one-liner each
    Mini App button in keyboard

  /start and Hi/Hello → Same Option C layout
    format_welcome_scan() exported for polling.py

  KEYBOARD (updated):
    Row 1: [🎯 Prime] [📊 Today] [🆕 New] [📉 Exit]
    Row 2: [⚠️ Caution] [💰 Strong] [📅 Digest] [📖 Guide]
    Row 3: [📊 Open Scanner App]  ← Mini App button

  PARSE MODE: HTML (more reliable than Markdown)

Everything else (pagination JSON, tracker update, Excel) unchanged.
"""

import os
import sys
import glob
import json
import requests
import pandas as pd
from datetime import date, datetime
import logging

try:
    import config
except ImportError:
    print("ERROR: config.py not found.")
    sys.exit(1)

try:
    from nse_telegram_handler import (
        save_scan_results, RESULTS_FILE, PARSE_MODE,
        SITUATION_META, SITUATION_ORDER,
        SITUATION_PRIME, SITUATION_HOLD,
        SITUATION_WATCH, SITUATION_BOOK, SITUATION_AVOID,
    )
    _HANDLER_OK = True
    print(f"[OUTPUT] Pagination JSON: {RESULTS_FILE}")
except ImportError as e:
    save_scan_results = None
    RESULTS_FILE      = None
    PARSE_MODE        = "HTML"
    _HANDLER_OK       = False
    SITUATION_META    = {
        "prime": {"icon":"🎯","label":"Prime Entry",  "action":"Enter today"},
        "hold":  {"icon":"💰","label":"Hold & Trail", "action":"Trail your SL"},
        "watch": {"icon":"👀","label":"Watch Closely","action":"Monitor"},
        "book":  {"icon":"⚠️","label":"Book Profits", "action":"Protect gains"},
        "avoid": {"icon":"🚫","label":"Avoid Now",    "action":"Skip today"},
    }
    SITUATION_ORDER = ["prime","hold","watch","book","avoid"]
    SITUATION_PRIME = "prime"
    SITUATION_HOLD  = "hold"
    SITUATION_WATCH = "watch"
    SITUATION_BOOK  = "book"
    SITUATION_AVOID = "avoid"
    print(f"[WARN] nse_telegram_handler not found: {e}")

# Mini App URL
MINI_APP_URL = os.environ.get(
    "MINI_APP_URL",
    "https://jayeshsrathod.github.io/nse-scanner/nse_miniapp.html"
)

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
# HTML HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _h(v):    return str(v).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')
def _b(v):    return f"<b>{_h(v)}</b>"
def _i(v):    return f"<i>{_h(v)}</i>"
def _code(v): return f"<code>{_h(v)}</code>"

SEP  = "━" * 18
SEP2 = "─" * 18


# ═══════════════════════════════════════════════════════════════════════════
# TELEGRAM SEND HELPER
# ═══════════════════════════════════════════════════════════════════════════

def _send(text, keyboard=None):
    if not getattr(config,'TELEGRAM_TOKEN',None) or \
       not getattr(config,'TELEGRAM_CHATID',None):
        log.warning("Telegram not configured")
        return False

    url  = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage"
    data = {
        'chat_id':    config.TELEGRAM_CHATID,
        'text':       text,
        'parse_mode': 'HTML',
    }
    if keyboard:
        data['reply_markup'] = json.dumps(keyboard)
    try:
        r = requests.post(url, data=data, timeout=10)
        if r.status_code == 200:
            return True
        log.error(f"Telegram error {r.status_code}: {r.text[:300]}")
        # Fallback: plain text
        data2 = {'chat_id': config.TELEGRAM_CHATID, 'text': text}
        if keyboard:
            data2['reply_markup'] = json.dumps(keyboard)
        return requests.post(url, data=data2, timeout=10).status_code == 200
    except Exception as e:
        log.error(f"Telegram send failed: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════════════
# KEYBOARD — Updated with Prime first + Mini App button
# ═══════════════════════════════════════════════════════════════════════════

def build_morning_keyboard():
    """
    Standard keyboard used on 6 AM message and /start.
    Row 1: Prime | Today | New | Exit
    Row 2: Caution | Strong | Digest | Guide
    Row 3: Open Scanner App (Mini App)
    """
    return {"inline_keyboard": [
        [
            {"text":"🎯 Prime",  "callback_data":"view_prime"},
            {"text":"📊 Today",  "callback_data":"view_today"},
            {"text":"🆕 New",    "callback_data":"view_new"},
            {"text":"📉 Exit",   "callback_data":"view_exit"},
        ],
        [
            {"text":"⚠️ Caution","callback_data":"view_caution"},
            {"text":"💰 Strong", "callback_data":"view_strong"},
            {"text":"📅 Digest", "callback_data":"/digest"},
            {"text":"📖 Guide",  "callback_data":"guide"},
        ],
        [
            {"text":"📊 Open Scanner App",
             "web_app":{"url": MINI_APP_URL}},
        ],
    ]}


# ═══════════════════════════════════════════════════════════════════════════
# SIGNAL LINE HELPER
# ═══════════════════════════════════════════════════════════════════════════

def _signal_line(s) -> str:
    """Compact signal: 🟢 Cross 4d · 3.2% room · Accum vol"""
    parts = []
    ca   = int(s.get('cross_age', 999))
    dp   = float(s.get('dist_pct', 0))
    acc  = int(s.get('acc_days', 0))
    dist = int(s.get('dist_days', 0))
    obv  = str(s.get('obv_dir', 'flat'))
    sb   = int(s.get('sector_bias', 0))

    if ca == -1:
        parts.append("Bearish HMA")
    elif s.get('fresh_cross'):
        parts.append(f"🟢 Cross {ca}d")
    elif ca <= 20:
        parts.append(f"Cross {ca}d")
    elif ca < 999:
        parts.append(f"⚪ Cross {ca}d")

    if s.get('overextended'):
        parts.append(f"⚠️ {dp:.0f}% stretched")
    elif dp <= 5.0 and dp > 0:
        parts.append(f"🟢 {dp:.1f}% room")
    elif dp > 0:
        parts.append(f"{dp:.1f}% above HMA")

    if acc >= 4 and obv == 'rising':
        parts.append("🟢 Accum vol")
    elif dist >= 4 or obv == 'falling':
        parts.append("🔴 Dist vol")

    if sb == 1:
        parts.append("Sector ✅")
    elif sb == -1:
        parts.append("Sector ❌")

    return " · ".join(parts)


# ═══════════════════════════════════════════════════════════════════════════
# OPTION C — Core message builder (used by 6 AM + /start + Hi)
# ═══════════════════════════════════════════════════════════════════════════

def format_option_c(stocks_list: list, scan_date_str: str,
                    greeting: str = "") -> str:
    """
    Build Option C message.

    PRIME stocks → Full detail cards (max 3)
    Other situations → Compact one-liner each

    Args:
        stocks_list:    list of stock dicts from telegram_last_scan.json
        scan_date_str:  'YYYY-MM-DD'
        greeting:       optional e.g. "👋 Hello Jayesh!\n\n"

    Returns:
        HTML message string
    """
    try:
        ds = datetime.strptime(scan_date_str,'%Y-%m-%d').strftime('%d-%b-%Y')
    except Exception:
        ds = scan_date_str

    total     = len(stocks_list)
    avg_score = sum(float(s.get('score',0)) for s in stocks_list) / max(total,1)
    prime_stocks = [s for s in stocks_list if s.get('situation') == SITUATION_PRIME]

    msg = greeting
    msg += f"📊 {_b('NSE Scan — ' + ds)}\n"
    msg += f"{_i(str(total) + ' stocks · Avg score ' + str(round(avg_score,1)))}\n"

    # ── PRIME — full cards ────────────────────────────────────
    if prime_stocks:
        msg += f"\n{SEP2}\n"
        msg += f"🎯 {_b('PRIME ENTRY (' + str(len(prime_stocks)) + ')')} — Enter today\n"
        msg += f"{SEP2}\n\n"

        for i, s in enumerate(prime_stocks[:3], 1):
            e   = float(s.get('close', 0))
            sl  = float(s.get('sl', e * 0.93))
            t1  = float(s.get('target1', e + (e-sl)))
            t2  = float(s.get('target2', e + 2*(e-sl)))
            sc  = int(round(float(s.get('score', 0))))
            r3  = float(s.get('return_3m_pct', 0))
            st  = int(s.get('streak', 0))
            wl  = str(s.get('weekly_label', ''))

            t1p = (t1-e)/e*100 if e > 0 else 0
            t2p = (t2-e)/e*100 if e > 0 else 0

            stag   = f" 🔥{st}d" if st >= 5 else ""
            ca_tag = " 🟢Fresh" if s.get('fresh_cross') else ""
            wl_str = f" · {_i(wl)}" if wl else ""

            msg += f"{_b(str(i) + '. ' + s['symbol'])}  {sc}/10{stag}{ca_tag}\n"
            msg += f"   Entry ₹{int(e):,} | SL ₹{int(sl):,}\n"
            msg += f"   T1 ₹{int(t1):,} (+{t1p:.1f}%) · T2 ₹{int(t2):,} (+{t2p:.1f}%)\n"

            sig = _signal_line(s)
            if sig:
                msg += f"   {_i(sig)}\n"
            msg += f"   3M {r3:+.1f}% {_i('(ref)')}{wl_str}\n\n"

        if len(prime_stocks) > 3:
            extra = [s['symbol'] for s in prime_stocks[3:]]
            msg += f"   {_i('+' + str(len(extra)) + ' more: ' + ', '.join(extra))}\n\n"
    else:
        msg += f"\n{SEP2}\n"
        msg += f"🎯 {_b('PRIME ENTRY')} — None today\n"
        msg += f"{_i('Market consolidating. Check Watch for setups building.')}\n"
        msg += f"{SEP2}\n\n"

    # ── Other situations — compact one-liners ─────────────────
    others = [SITUATION_HOLD, SITUATION_WATCH, SITUATION_BOOK, SITUATION_AVOID]
    has_others = any(
        any(s.get('situation') == sit for s in stocks_list)
        for sit in others
    )

    if has_others:
        msg += SEP + "\n"
        for sit in others:
            group = [s for s in stocks_list if s.get('situation') == sit]
            if not group:
                continue
            sm    = SITUATION_META.get(sit, {})
            icon  = sm.get('icon', '·')
            lbl   = sm.get('label', sit).split()[0]   # first word only

            names = []
            for s in group[:5]:
                sym = s['symbol']
                st  = int(s.get('streak', 0))
                names.append(f"{sym}({st}d)" if st >= 5 else sym)
            more = f" +{len(group)-5}" if len(group) > 5 else ""

            msg += f"{icon} {_b(lbl + ':')}  {', '.join(names)}{more}\n"
        msg += SEP + "\n"

    msg += f"\n{_i('Tap Prime for entry details · TV confirms timing')}"
    return msg


# ═══════════════════════════════════════════════════════════════════════════
# FORMAT WELCOME SCAN — exported to polling.py for /start + Hi + Hello
# ═══════════════════════════════════════════════════════════════════════════

def format_welcome_scan(user_name: str = "") -> tuple:
    """
    Build Option C welcome message for /start / Hi / Hello.

    Args:
        user_name: Telegram first name (optional)

    Returns:
        (message_str, keyboard_dict)
    """
    greeting = (f"👋 {_b('Hello ' + _h(user_name) + '!')}\n\n"
                if user_name else f"👋 {_b('Hello!')}\n\n")

    if RESULTS_FILE and os.path.exists(RESULTS_FILE):
        try:
            with open(RESULTS_FILE,'r',encoding='utf-8') as f:
                data = json.load(f)
            stocks    = data.get('stocks', [])
            scan_date = data.get('scan_date', '')
            if stocks:
                msg = format_option_c(stocks, scan_date, greeting)
                return msg, build_morning_keyboard()
        except Exception as e:
            log.warning(f"format_welcome_scan error: {e}")

    # Fallback
    msg  = greeting
    msg += f"📊 {_b('NSE Scanner Daily')}\n\n"
    msg += f"{_i('Scan data not available yet.')}\n"
    msg += "Pipeline runs at 6:00 AM IST daily.\n\n"
    msg += "Try again after 6 AM."
    return msg, build_morning_keyboard()


# ═══════════════════════════════════════════════════════════════════════════
# PAGINATION JSON SAVE + TRACKER UPDATE
# ═══════════════════════════════════════════════════════════════════════════

def _save_pagination_json(results_df, report_date):
    if not _HANDLER_OK or save_scan_results is None:
        log.error("[BOT] Cannot save pagination JSON — handler not loaded")
        return

    df = results_df.copy()
    sit_pri = {SITUATION_PRIME:0, SITUATION_HOLD:1,
               SITUATION_WATCH:2, SITUATION_BOOK:3, SITUATION_AVOID:4}
    if 'situation' in df.columns:
        df['_sp'] = df['situation'].map(lambda s: sit_pri.get(s,2))
        df = df.sort_values(['_sp','score'],
                            ascending=[True,False]).drop(columns=['_sp'])
    elif 'score' in df.columns:
        df = df.sort_values('score', ascending=False)
    df = df.reset_index(drop=True)

    try:
        save_scan_results(df, report_date)
        log.info(f"[BOT] Pagination JSON saved → {RESULTS_FILE}")

        if RESULTS_FILE and os.path.exists(RESULTS_FILE):
            with open(RESULTS_FILE, encoding='utf-8') as f:
                check = json.load(f)
            log.info(f"[BOT] JSON: {check['total_stocks']} stocks, "
                     f"date={check['scan_date']}")

            try:
                from nse_signal_tracker import update_tracker
                from nse_telegram_handler import load_history as _lh
                summary = update_tracker(check['stocks'], check['scan_date'], _lh())
                log.info(f"[TRACKER] {summary}")
                print(f"[TRACKER] {summary}")
            except Exception as te:
                log.warning(f"[TRACKER] Skipped: {te}")

    except Exception as e:
        log.error(f"[BOT] save_scan_results FAILED: {e}", exc_info=True)
        print(f"[BOT] Pagination JSON save FAILED: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# SEND TELEGRAM — 6 AM morning message
# ═══════════════════════════════════════════════════════════════════════════

def send_telegram(results_df, report_date):
    if not getattr(config,'TELEGRAM_TOKEN',None) or \
       not getattr(config,'TELEGRAM_CHATID',None):
        log.warning("Telegram not configured"); return False
    if results_df.empty:
        log.warning("Empty DataFrame"); return False

    # Step 1: Save JSON (always first)
    _save_pagination_json(results_df, report_date)

    # Step 2: Build Option C from saved JSON
    try:
        if RESULTS_FILE and os.path.exists(RESULTS_FILE):
            with open(RESULTS_FILE,'r',encoding='utf-8') as f:
                data = json.load(f)
            stocks_list = data.get('stocks', [])
            scan_date   = data.get('scan_date', str(report_date))
        else:
            stocks_list = _df_to_list(results_df)
            scan_date   = str(report_date)

        msg = format_option_c(stocks_list, scan_date)
        if len(msg) > 4096:
            msg = msg[:4050] + f"\n\n{_i('... truncated. Tap /today for full list.')}"

        sent = _send(msg, build_morning_keyboard())
        if sent:
            log.info(f"Morning message sent: {len(stocks_list)} stocks")
        return sent

    except Exception as e:
        log.error(f"send_telegram failed: {e}", exc_info=True)
        return _send(_fmt_fallback(results_df, report_date),
                     build_morning_keyboard())


def _df_to_list(df) -> list:
    rows = []
    for _, row in df.iterrows():
        e  = float(row.get('close', 0))
        sl = float(row.get('sl', e*0.93))
        rows.append({
            'symbol':        str(row['symbol']),
            'score':         round(float(row.get('score',0)),1),
            'situation':     str(row.get('situation','watch')),
            'close':         round(e,2),
            'sl':            round(sl,2),
            'target1':       round(float(row.get('target1', e+(e-sl))),2),
            'target2':       round(float(row.get('target2', e+2*(e-sl))),2),
            'return_3m_pct': round(float(row.get('return_3m_pct',0)),1),
            'streak':        int(row.get('streak',0)),
            'cross_age':     int(row.get('cross_age',999)),
            'fresh_cross':   bool(row.get('fresh_cross',False)),
            'dist_pct':      round(float(row.get('dist_pct',0)),1),
            'overextended':  bool(row.get('overextended',False)),
            'acc_days':      int(row.get('acc_days',0)),
            'dist_days':     int(row.get('dist_days',0)),
            'obv_dir':       str(row.get('obv_dir','flat')),
            'sector_bias':   int(row.get('sector_bias',0)),
            'weekly_label':  str(row.get('weekly_label','')),
        })
    return rows


def _fmt_fallback(df, report_date):
    try:    ds = report_date.strftime('%d-%b-%Y')
    except: ds = str(report_date)
    msg = f"📊 {_b('NSE Scan — ' + ds)}\n\n"
    for i, (_, row) in enumerate(df.head(6).iterrows(), 1):
        e   = float(row.get('entry', row.get('close',0)))
        sc  = int(row.get('score',0))
        sit = str(row.get('situation','watch'))
        msg += (f"{i}. {_code(str(row['symbol']))}  {sc}/10  "
                f"{SITUATION_META.get(sit,{}).get('icon','')}\n"
                f"   ₹{int(e):,}\n\n")
    msg += _i("Send /prime for entry-ready stocks")
    return msg


# ═══════════════════════════════════════════════════════════════════════════
# EXCEL EXPORT
# ═══════════════════════════════════════════════════════════════════════════

def save_excel(results_df, report_date):
    if results_df.empty: return None

    for f in glob.glob(os.path.join(config.OUTPUT_DIR,"NSE_Scanner_*.xlsx")):
        try: os.remove(f)
        except: pass

    df = results_df.copy()
    sit_pri = {SITUATION_PRIME:0, SITUATION_HOLD:1,
               SITUATION_WATCH:2, SITUATION_BOOK:3, SITUATION_AVOID:4}
    if 'situation' in df.columns:
        df['_sp'] = df['situation'].map(lambda s: sit_pri.get(s,2))
        df = df.sort_values(['_sp','score'],
                            ascending=[True,False]).drop(columns=['_sp'])
    elif 'score' in df.columns:
        df = df.sort_values('score', ascending=False)
    df = df.reset_index(drop=True)

    rename = {
        'symbol':'Symbol','situation':'Situation','score':'FwdScore',
        'return_1m_pct':'1M%','return_2m_pct':'2M%','return_3m_pct':'3M%(ref)',
        'close':'Close','avg_volume':'AvgVolume','delivery_pct':'DelivPct',
        'entry':'Entry','sl':'StopLoss','sl_pct':'SL%',
        'target1':'Target1','t1_pct':'T1%','target2':'Target2','t2_pct':'T2%','rr':'RR',
        'category':'Category','streak':'Streak',
        'cross_age':'HMA_CrossAge','dist_pct':'Dist_HMA55%',
        'fresh_cross':'FreshCross','overextended':'Overextended',
        'acc_days':'AccumDays','dist_days':'DistribDays',
        'obv_dir':'OBV_Dir','sector_bias':'SectorBias',
        'weekly_tier':'WeeklyTier','weekly_label':'WeeklyLabel',
        'pts_hma':'Pts_HMA','pts_dist':'Pts_Dist','pts_vol':'Pts_Vol',
        'pts_rsi':'Pts_RSI','pts_macd':'Pts_MACD','pts_sector':'Pts_Sector',
        'pts_rr':'Pts_RR','pen_overext':'Pen_Overext','pen_decel':'Pen_Decel',
        'rsi':'RSI','conviction':'Conviction',
    }
    df = df.rename(columns={k:v for k,v in rename.items() if k in df.columns})
    df.insert(0,'Rank', range(1, len(df)+1))

    order = [
        'Rank','Symbol','Situation','FwdScore','Streak',
        'WeeklyTier','WeeklyLabel','HMA_CrossAge','Dist_HMA55%',
        'FreshCross','Overextended','AccumDays','DistribDays','OBV_Dir','SectorBias',
        'Entry','StopLoss','SL%','Target1','T1%','Target2','T2%','RR',
        '1M%','2M%','3M%(ref)','Close','AvgVolume','DelivPct','RSI',
        'Pts_HMA','Pts_Dist','Pts_Vol','Pts_RSI','Pts_MACD',
        'Pts_Sector','Pts_RR','Pen_Overext','Pen_Decel','Conviction','Category',
    ]
    df = df[[c for c in order if c in df.columns]]

    fname = f"NSE_Scanner_{report_date.strftime('%Y-%m-%d')}.xlsx"
    fpath = os.path.join(config.OUTPUT_DIR, fname)
    try:
        df.to_excel(fpath, sheet_name='NSE_Scanner', index=False)
        log.info(f"Excel saved: {fpath}")
        return fpath
    except Exception as e:
        log.error(f"Excel save failed: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════
# GENERATE REPORT
# ═══════════════════════════════════════════════════════════════════════════

def generate_report(results_df, report_date=None):
    if report_date is None:
        report_date = date.today()

    print(f"\n{'='*56}\n  NSE OUTPUT v7\n{'='*56}")

    results = {
        'excel_file':    None,
        'telegram_sent': False,
        'date':          report_date,
        'stocks_count':  len(results_df),
    }

    excel_file = save_excel(results_df, report_date)
    if excel_file:
        results['excel_file'] = excel_file
        print(f"Excel: {os.path.basename(excel_file)}")

    ok = send_telegram(results_df, report_date)
    results['telegram_sent'] = ok
    prime = (results_df['situation'] == SITUATION_PRIME).sum() \
            if 'situation' in results_df.columns else 0
    print(f"Telegram: {'sent ✅' if ok else 'failed ❌'}")
    print(f"Stocks: {len(results_df)} | 🎯 Prime: {prime}")

    if RESULTS_FILE and os.path.exists(RESULTS_FILE):
        try:
            with open(RESULTS_FILE, encoding='utf-8') as f:
                check = json.load(f)
            expected = report_date.strftime('%Y-%m-%d')
            if check.get('scan_date') != expected:
                log.warning(f"JSON date mismatch: {expected} vs "
                            f"{check.get('scan_date')}")
        except Exception as e:
            log.warning(f"JSON check failed: {e}")

    return results


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--date",    help="YYYY-MM-DD")
    parser.add_argument("--test",    action="store_true")
    parser.add_argument("--preview", action="store_true",
                        help="Preview Option C message from existing JSON")
    args = parser.parse_args()

    report_date = date.today()
    if args.date:
        report_date = datetime.strptime(args.date, "%Y-%m-%d").date()

    if args.preview:
        msg, _ = format_welcome_scan("Jayesh")
        import re
        print(re.sub(r'<[^>]+>', '', msg))
        return

    if args.test:
        df = pd.DataFrame({
            'symbol':        ['KAYNES','DIXON','SYRMA','ASTERDM','EMCURE','HONASA'],
            'score':         [9, 8, 7, 6, 5, 3],
            'situation':     ['prime','prime','hold','watch','book','avoid'],
            'conviction':    ['HIGH CONVICTION','HIGH CONVICTION',
                              'HIGH CONVICTION','Watchlist','Watchlist',''],
            'return_1m_pct': [8.5, 7.1, 4.2, 3.1, 2.1, -2.1],
            'return_2m_pct': [12.4,11.8, 7.6, 5.8, 4.3, 1.5],
            'return_3m_pct': [21.6,19.3,11.4,12.6,13.3, 9.5],
            'close':  [5840, 8420, 796, 688, 1590, 307],
            'entry':  [5840, 8420, 796, 688, 1590, 307],
            'sl':     [5600, 8060, 757, 655, 1477, 280],
            'sl_pct': [-4.1,-4.3,-4.9,-4.8,-7.1,-8.8],
            'target1':[6080, 8780, 835, 721, 1703, 334],
            't1_pct': [4.1, 4.3, 4.9, 4.8, 7.1, 8.8],
            'target2':[6320, 9140, 874, 754, 1816, 361],
            't2_pct': [8.2, 8.5, 9.8, 9.6,14.2,17.6],
            'rr':     [2.0]*6,
            'avg_volume':   [87210,125430,234100,180000,95000,420000],
            'delivery_pct': [72.4, 61.2, 55.1, 58.3, 48.3, 38.5],
            'cross_age':    [4, 7, 12, 18, 42, -1],
            'fresh_cross':  [True, True, False, False, False, False],
            'dist_pct':     [3.2, 4.1, 5.8, 6.2, 18.2, 0],
            'overextended': [False,False,False,False,True,False],
            'acc_days':     [4, 3, 3, 2, 1, 1],
            'dist_days':    [0, 1, 1, 1, 4, 3],
            'obv_dir':      ['rising','rising','flat','rising','falling','falling'],
            'sector_bias':  [1, 0, 1, 1, 1, 0],
            'weekly_tier':  [1, 1, 2, 2, 1, 3],
            'weekly_label': ['Weekly ✅ Bullish','Weekly ✅ Bullish',
                             'Weekly 🟡 Pullback','Weekly 🟡 Pullback',
                             'Weekly ✅ Bullish','Weekly ❌ Bearish'],
            'category':     ['uptrend','uptrend','rising','safer','peak','recovering'],
            'streak':       [3, 1, 6, 2, 8, 1],
            'momentum_score':[0.18,0.16,0.10,0.09,0.12,0.08],
        })
    else:
        from nse_scanner import scan_stocks
        df = scan_stocks(scan_date=report_date)
        if df.empty:
            print("No scanner results"); return

    generate_report(df, report_date)


if __name__ == "__main__":
    main()
