"""
nse_telegram_polling.py — Telegram Polling Bot (Phase 2.1)
============================================================
Views: Today / New / Exit / Caution / Strong / Buckets / Guide
Admin: /admin, /users, /health (admin-only)
Tracking: every user + every action logged
Health check: auto-sends to admin at 11:30 PM IST
Nav: symbol back buttons on all sub-menus
"""

import time
import sys
import json
import os
import threading
import logging
from datetime import date, datetime

try:
    import requests
except ImportError:
    print("ERROR: requests not installed.")
    sys.exit(1)

try:
    import config
except ImportError:
    print("ERROR: config.py not found.")
    sys.exit(1)

try:
    from nse_telegram_handler import (
        load_scan_results, load_history, sort_stocks,
        format_stock_list, format_help, format_welcome,
        format_today_scan, format_new_stocks, format_exit_stocks,
        format_caution_stocks, format_strong_stocks,
        get_new_stocks, get_exit_stocks, get_strong_stocks,
        PARSE_MODE, RESULTS_FILE, _b, _h, _code, _fmt_return,
    )
    print("[POLL] Handler imports OK")
except ImportError as e:
    print(f"ERROR importing nse_telegram_handler: {e}")
    sys.exit(1)

_ADMIN_OK   = False
_BUCKET_OK  = False
_TRACKER_OK = False

try:
    from nse_bot_admin import (
        track_user, log_activity, is_admin, is_blocked,
        format_health_report, format_user_list, format_user_detail,
        generate_health_report, send_health_check,
        format_guide_message, get_user_count,
    )
    _ADMIN_OK = True
    print("[POLL] Admin module loaded OK")
except ImportError as e:
    print(f"[WARN] nse_bot_admin not found: {e}")
    def track_user(u): pass
    def log_activity(uid, t, d): pass
    def is_admin(uid): return False
    def is_blocked(uid): return False
    def get_user_count(): return 0

try:
    from nse_smart_buckets import (
        classify_current_scan, format_bucketed_message,
        format_bucket_detail, format_quick_dashboard,
        BUCKET_RISING, BUCKET_UPTREND, BUCKET_PEAK,
        BUCKET_RECOVERY, BUCKET_SAFE, BUCKET_CAUTION,
    )
    _BUCKET_OK = True
    print("[POLL] Smart buckets loaded OK")
except ImportError as e:
    print(f"[WARN] nse_smart_buckets not found: {e}")

try:
    from nse_signal_tracker import (
        update_tracker, get_live_signals, get_exited_signals,
        get_signal, get_tracker_summary, calculate_probability,
        format_stock_with_prob, format_signal_card,
        format_exit_card, format_caution_card, set_category,
        STATE_ACTIVE, STATE_T1_HIT, STATE_WEAKENING, STATE_EXITED,
    )
    _TRACKER_OK = True
    print("[POLL] Signal tracker loaded OK")
except ImportError as e:
    print(f"[WARN] nse_signal_tracker not found: {e}")
    def get_signal(s): return None
    def get_tracker_summary(): return {}
    def calculate_probability(**kw): return {"t1_pct": 0, "t2_pct": 0, "sl_pct": 0}

os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[
        logging.FileHandler("logs/polling_bot.log", encoding="utf-8"),
        logging.StreamHandler(),
    ]
)
log = logging.getLogger(__name__)

GUIDE_PDF_URL = os.environ.get(
    "GUIDE_PDF_URL",
    "https://htmlpreview.github.io/?https://github.com/JayeshSRathod/nse-scanner/blob/main/docs/NSE_Scanner_Guide.html"
)


class FakeUser:
    def __init__(self, d):
        if d is None: d = {}
        self.id         = d.get("id", 0)
        self.username   = d.get("username", "")
        self.first_name = d.get("first_name", "")
        self.last_name  = d.get("last_name", "")


# ── Natural language mapping ──────────────────────────────────

GREETINGS = {
    "hi","hii","hiii","hello","hey","helo","hlo","start","begin","go",
    "good morning","good evening","good afternoon","gm","ge","ga",
    "namaste","namaskar","jai hind",
}
NEXT_WORDS    = {"next","n","aage","more","forward"}
PREV_WORDS    = {"prev","previous","p","back","peeche"}
NEWS_WORDS    = {"news","headline","headlines","khabar"}
TOP_WORDS     = {"top","best","top10","winners","leader"}
LIST_WORDS    = {"list","all","summary","sab"}
HELP_WORDS    = {"help","?","commands","menu"}
NEW_WORDS     = {"new","new entry","fresh","naya"}
EXIT_WORDS    = {"exit","exited","left","bahar"}
STRONG_WORDS  = {"strong","streak","consistent","strong stocks"}
CAUTION_WORDS = {"caution","risk","warning","careful"}
TODAY_WORDS   = {"today","scan","aaj"}
GUIDE_WORDS   = {"guide","pdf","how","learn","tutorial","padho","sikho"}
BUCKET_WORDS  = {"buckets","categories","groups","category","bucket"}
ADMIN_WORDS   = {"admin","dashboard","panel"}


def resolve_text_to_command(text):
    clean = text.strip().lower()
    if clean.startswith('/'):
        return clean
    if clean in ('next','prev','list','help','news',
                 'sort_3m','sort_score','sort_top10','noop',
                 'view_today','view_new','view_exit','view_caution',
                 'view_strong','view_buckets') \
       or clean.startswith('page_') or clean.startswith('bucket_') \
       or clean.startswith('stock_'):
        return clean
    if clean in GREETINGS:        return '/start'
    if clean.isdigit() and 1 <= int(clean) <= 99:
        return f'/page {clean}'
    if clean.startswith('page ') and clean[5:].isdigit():
        return f'/page {clean[5:]}'
    if clean in NEXT_WORDS:       return '/next'
    if clean in PREV_WORDS:       return '/prev'
    if clean in NEWS_WORDS:       return '/news'
    if clean in TOP_WORDS:        return 'sort_top10'
    if clean in LIST_WORDS:       return '/list'
    if clean in HELP_WORDS:       return '/help'
    if clean in NEW_WORDS:        return 'view_new'
    if clean in EXIT_WORDS:       return 'view_exit'
    if clean in STRONG_WORDS:     return 'view_strong'
    if clean in CAUTION_WORDS:    return 'view_caution'
    if clean in TODAY_WORDS:      return 'view_today'
    if clean in GUIDE_WORDS:      return '/guide'
    if clean in BUCKET_WORDS:     return 'view_buckets'
    if clean in ADMIN_WORDS:      return '/admin'
    return clean


# ── User state ────────────────────────────────────────────────

_user_state = {}

def _state(chat_id):
    if chat_id not in _user_state:
        _user_state[chat_id] = {'page': 0, 'sort': '3m', 'view': 'today'}
    return _user_state[chat_id]

def get_user_page(chat_id):    return _state(chat_id)['page']
def set_user_page(chat_id, v): _state(chat_id)['page'] = v
def get_user_sort(chat_id):    return _state(chat_id).get('sort', '3m')
def set_user_sort(chat_id, v): _state(chat_id)['sort'] = v
def get_user_view(chat_id):    return _state(chat_id).get('view', 'today')
def set_user_view(chat_id, v): _state(chat_id)['view'] = v


# ── Telegram API ──────────────────────────────────────────────

def send_message(chat_id, text, reply_markup=None):
    url  = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage"
    data = {'chat_id': str(chat_id), 'text': text, 'parse_mode': PARSE_MODE}
    if reply_markup:
        data['reply_markup'] = json.dumps(reply_markup)
    try:
        r = requests.post(url, data=data, timeout=10)
        if r.status_code != 200:
            print(f"[WARN] send_message FAILED: {r.status_code}")
            try: print(f"[WARN] {r.json().get('description', r.text[:300])}")
            except: print(f"[WARN] {r.text[:300]}")
            return False
        return True
    except Exception as e:
        print(f"[ERROR] send_message: {e}")
        return False


def answer_callback_query(cq_id, text=""):
    url  = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/answerCallbackQuery"
    data = {'callback_query_id': cq_id}
    if text: data['text'] = text
    try: requests.post(url, data=data, timeout=5)
    except: pass


def get_updates(offset=None):
    url    = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/getUpdates"
    params = {'timeout': 30, 'allowed_updates': json.dumps(['message', 'callback_query'])}
    if offset is not None: params['offset'] = offset
    try:
        r = requests.get(url, params=params, timeout=35)
        return r.json()
    except Exception as e:
        print(f"[ERROR] get_updates: {e}")
        return None


# ── Keyboards ─────────────────────────────────────────────────

BUCKET_CB_MAP = {
    "bucket_rising":   BUCKET_RISING   if _BUCKET_OK else "rising",
    "bucket_uptrend":  BUCKET_UPTREND  if _BUCKET_OK else "uptrend",
    "bucket_peak":     BUCKET_PEAK     if _BUCKET_OK else "peak",
    "bucket_recovery": BUCKET_RECOVERY if _BUCKET_OK else "recovery",
    "bucket_safe":     BUCKET_SAFE     if _BUCKET_OK else "safe",
    "bucket_caution":  BUCKET_CAUTION  if _BUCKET_OK else "caution",
}


def create_inline_keyboard(current_page, total_pages, active_sort='3m', active_view='today'):
    kb = []
    kb.append([
        {"text": f"{'●' if active_view=='today'   else '○'} Today",   "callback_data": "view_today"},
        {"text": f"{'●' if active_view=='new'     else '○'} New",     "callback_data": "view_new"},
        {"text": f"{'●' if active_view=='exit'    else '○'} Exit",    "callback_data": "view_exit"},
    ])
    kb.append([
        {"text": f"{'●' if active_view=='caution' else '○'} Caution", "callback_data": "view_caution"},
        {"text": f"{'●' if active_view=='strong'  else '○'} Strong",  "callback_data": "view_strong"},
        {"text": f"{'●' if active_view=='buckets' else '○'} Buckets", "callback_data": "view_buckets"},
    ])
    if active_view == 'today':
        kb.append([
            {"text": f"{'●' if active_sort=='3m'    else '○'} 3M",    "callback_data": "sort_3m"},
            {"text": f"{'●' if active_sort=='score' else '○'} Score", "callback_data": "sort_score"},
            {"text": f"{'●' if active_sort=='top10' else '○'} Top10", "callback_data": "sort_top10"},
        ])
    if active_view == 'today' and total_pages > 1:
        nav = []
        if current_page > 0:
            nav.append({"text": "\u25c0 Prev", "callback_data": "prev"})
        nav.append({"text": f"{current_page+1}/{total_pages}", "callback_data": "noop"})
        if current_page < total_pages - 1:
            nav.append({"text": "Next \u25b6", "callback_data": "next"})
        kb.append(nav)
        start_p = max(0, min(current_page - 2, total_pages - 5))
        end_p   = min(total_pages, start_p + 5)
        kb.append([
            {"text": f"\u25cf{p+1}" if p == current_page else str(p+1),
             "callback_data": f"page_{p}"}
            for p in range(start_p, end_p)
        ])
    kb.append([
        {"text": "News", "callback_data": "news"},
        {"text": "Summary", "callback_data": "list"},
        {"text": "Guide", "callback_data": "guide"},
        {"text": "Help", "callback_data": "help"},
    ])
    return {"inline_keyboard": kb}


def create_bucket_keyboard():
    return {"inline_keyboard": [
        [{"text": "\U0001F4C8 Rising","callback_data": "bucket_rising"},
         {"text": "\U0001F680 Uptrend","callback_data": "bucket_uptrend"},
         {"text": "\U0001F51D Peak","callback_data": "bucket_peak"}],
        [{"text": "\U0001F4C9 Recovery","callback_data": "bucket_recovery"},
         {"text": "\U0001F6E1 Safer","callback_data": "bucket_safe"},
         {"text": "\u26A0 Caution","callback_data": "bucket_caution"}],
        [{"text": "\u25c0\u25c0 Main", "callback_data": "view_today"}],
    ]}


def create_bucket_detail_keyboard():
    return {"inline_keyboard": [
        [{"text": "\U0001F4C8 Rising","callback_data": "bucket_rising"},
         {"text": "\U0001F680 Uptrend","callback_data": "bucket_uptrend"},
         {"text": "\U0001F51D Peak","callback_data": "bucket_peak"}],
        [{"text": "\U0001F4C9 Recovery","callback_data": "bucket_recovery"},
         {"text": "\U0001F6E1 Safer","callback_data": "bucket_safe"},
         {"text": "\u26A0 Caution","callback_data": "bucket_caution"}],
        [{"text": "\u25c0 Buckets", "callback_data": "view_buckets"},
         {"text": "\u25c0\u25c0 Main", "callback_data": "view_today"}],
    ]}


def create_guide_keyboard():
    return {"inline_keyboard": [
        [{"text": "\U0001F4D6 Open Full Guide", "url": GUIDE_PDF_URL}],
        [{"text": "\u25c0\u25c0 Main", "callback_data": "view_today"}],
    ]}


def create_admin_keyboard():
    return {"inline_keyboard": [
        [{"text": "Health Check", "callback_data": "admin_health"},
         {"text": "Users", "callback_data": "admin_users"}],
        [{"text": "Activity", "callback_data": "admin_stats"},
         {"text": "\u25c0\u25c0 Main", "callback_data": "view_today"}],
    ]}


def create_signal_card_keyboard(symbol=""):
    kb = []
    kb.append([
        {"text": "\u25c0 Back", "callback_data": "back_from_card"},
        {"text": "\u25c0\u25c0 Main", "callback_data": "view_today"},
    ])
    return {"inline_keyboard": kb}


# ── Command handler ───────────────────────────────────────────

def handle_command(chat_id, text, is_callback=False, raw_user=None):
    cmd = (text or '').strip().lower()
    if '@' in cmd: cmd = cmd.split('@')[0]

    print(f"[CMD] chat={chat_id}  cmd={cmd!r}  callback={is_callback}")

    if raw_user:
        track_user(FakeUser(raw_user))
        log_activity(raw_user.get("id", chat_id),
                     "callback" if is_callback else "command", cmd)

    if raw_user and is_blocked(raw_user.get("id", 0)):
        return {"message": None, "keyboard": None} if is_callback else None

    results = load_scan_results()
    if not results:
        msg = "No scan results found.\nPipeline runs at 6:00 AM IST daily."
        if is_callback: return {"message": msg, "keyboard": None}
        send_message(chat_id, msg)
        return None

    all_stocks = results['stocks']
    page_size  = results['page_size']
    scan_date  = results['scan_date']
    history    = load_history()
    cur_sort   = get_user_sort(chat_id)
    cur_page   = get_user_page(chat_id)
    cur_view   = get_user_view(chat_id)

    def respond_today(page, sort_mode):
        sorted_stocks = sort_stocks(all_stocks, sort_mode)
        tot_pages     = max(1, (len(sorted_stocks) + page_size - 1) // page_size)
        safe_page     = max(0, min(page, tot_pages - 1))
        set_user_page(chat_id, safe_page)
        set_user_sort(chat_id, sort_mode)
        set_user_view(chat_id, 'today')
        msg      = format_stock_list(sorted_stocks, safe_page * page_size, page_size, scan_date)
        keyboard = create_inline_keyboard(safe_page, tot_pages, sort_mode, 'today')
        if is_callback: return {"message": msg, "keyboard": keyboard}
        send_message(chat_id, msg, reply_markup=keyboard)
        return None

    def respond_view(view_name, msg, keyboard=None):
        set_user_view(chat_id, view_name)
        if keyboard is None:
            keyboard = create_inline_keyboard(0, 1, cur_sort, view_name)
        if is_callback: return {"message": msg, "keyboard": keyboard}
        send_message(chat_id, msg, reply_markup=keyboard)
        return None

    # ── /start ──
    if cmd == '/start':
        msg = format_welcome()
        set_user_view(chat_id, 'today')
        keyboard = create_inline_keyboard(0, 1, '3m', 'today')
        if is_callback: return {"message": msg, "keyboard": keyboard}
        send_message(chat_id, msg, reply_markup=keyboard)
        return None

    elif cmd in ('/today', 'view_today'):
        msg = format_today_scan(all_stocks, scan_date)
        return respond_view('today', msg)

    elif cmd in ('/next', '/continue', 'next'):
        if cur_view != 'today': return respond_today(0, cur_sort)
        ss = sort_stocks(all_stocks, cur_sort)
        tot_pages = max(1, (len(ss) + page_size - 1) // page_size)
        if cur_page + 1 >= tot_pages:
            msg = "You've reached the last page!"
            if is_callback: return {"message": msg, "keyboard": None}
            send_message(chat_id, msg); return None
        return respond_today(cur_page + 1, cur_sort)

    elif cmd in ('/prev', 'prev'):
        if cur_view != 'today': return respond_today(0, cur_sort)
        if cur_page == 0:
            msg = "Already on the first page!"
            if is_callback: return {"message": msg, "keyboard": None}
            send_message(chat_id, msg); return None
        return respond_today(cur_page - 1, cur_sort)

    elif cmd.startswith('/page') or cmd.startswith('page_'):
        try:
            if cmd.startswith('/page'): page_num = int(cmd.split()[1]) - 1
            else: page_num = int(cmd.split('_')[1])
            return respond_today(page_num, cur_sort)
        except (IndexError, ValueError):
            msg = "Usage: /page N"
            if is_callback: return {"message": msg, "keyboard": None}
            send_message(chat_id, msg); return None

    elif cmd == 'sort_3m':    return respond_today(0, '3m')
    elif cmd == 'sort_score': return respond_today(0, 'score')
    elif cmd == 'sort_top10': return respond_today(0, 'top10')
    elif cmd == 'noop':
        return {"message": None, "keyboard": None} if is_callback else None

    elif cmd in ('/new', 'view_new'):
        if len(history) < 2:
            msg = ("<b>History Building...</b>\n\n"
                   "Need 2+ days of scan history for New Entries.\n"
                   f"Currently have: {len(history)} day(s)\n\n"
                   "Check back tomorrow after 6 AM scan.")
            return respond_view('new', msg)
        new_stocks = get_new_stocks(history)
        msg = format_new_stocks(new_stocks, scan_date)
        return respond_view('new', msg)

    elif cmd in ('/exit', 'view_exit'):
        if len(history) < 2:
            msg = ("<b>History Building...</b>\n\n"
                   "Need 2+ days of scan history for Exit Watch.\n"
                   f"Currently have: {len(history)} day(s)\n\n"
                   "Check back tomorrow after 6 AM scan.")
            return respond_view('exit', msg)
        exit_stocks = get_exit_stocks(history)
        msg = format_exit_stocks(exit_stocks, scan_date)
        return respond_view('exit', msg)

    elif cmd in ('/caution', 'view_caution'):
        msg = format_caution_stocks(all_stocks, scan_date)
        return respond_view('caution', msg)

    elif cmd in ('/strong', 'view_strong'):
        if len(history) < 5:
            days_left = 5 - len(history)
            msg = (f"<b>Strong Signals</b>\n\n"
                   f"Needs 5 days of history.\n"
                   f"Currently have: {len(history)} day(s)\n"
                   f"Ready in: {days_left} more trading day(s)")
            return respond_view('strong', msg)
        strong_stocks = get_strong_stocks(history)
        msg = format_strong_stocks(strong_stocks, scan_date)
        return respond_view('strong', msg)

    elif cmd in ('/news', 'news'):
        sorted_stocks = sort_stocks(all_stocks, cur_sort)
        tot_pages = max(1, (len(sorted_stocks) + page_size - 1) // page_size)
        safe_page = max(0, min(cur_page, tot_pages - 1))
        msg = format_stock_list(sorted_stocks, safe_page * page_size,
                                page_size, scan_date, include_news=True)
        keyboard = create_inline_keyboard(safe_page, tot_pages, cur_sort, 'today')
        if is_callback: return {"message": msg, "keyboard": keyboard}
        send_message(chat_id, msg, reply_markup=keyboard); return None

    elif cmd in ('/list', 'list'):
        top10 = sort_stocks(all_stocks, 'top10')
        sorted_stocks = sort_stocks(all_stocks, cur_sort)
        tot_pages = max(1, (len(sorted_stocks) + page_size - 1) // page_size)
        history_line = ""
        if len(history) >= 2:
            new_count    = len(get_new_stocks(history))
            exit_count   = len(get_exit_stocks(history))
            strong_count = len(get_strong_stocks(history))
            history_line = (f"\n<b>Today:</b>\n"
                           f"{new_count} new  |  {exit_count} exited  |  {strong_count} strong\n")
        msg  = f"<b>All Scanned Stocks Summary</b>\n\n"
        msg += f"Total: {len(all_stocks)} stocks  |  Scan: {scan_date}\n"
        msg += history_line
        msg += f"\n<b>Top 10 by 3M Return:</b>\n"
        for j, s in enumerate(top10, 1):
            r3m = float(s.get('return_3m_pct', 0))
            sign = '+' if r3m >= 0 else ''
            msg += f"{j}. <code>{s['symbol']}</code> {int(s.get('score',0))}/10 | 3M: {sign}{r3m:.1f}%\n"
        remaining = len(all_stocks) - 10
        if remaining > 0: msg += f"\n... and {remaining} more\n"
        keyboard = create_inline_keyboard(cur_page, tot_pages, cur_sort, cur_view)
        if is_callback: return {"message": msg, "keyboard": keyboard}
        send_message(chat_id, msg, reply_markup=keyboard); return None

    elif cmd in ('/help', 'help'):
        ss = sort_stocks(all_stocks, cur_sort)
        tot_pages = max(1, (len(ss) + page_size - 1) // page_size)
        keyboard = create_inline_keyboard(cur_page, tot_pages, cur_sort, cur_view)
        msg = format_help()
        if is_callback: return {"message": msg, "keyboard": keyboard}
        send_message(chat_id, msg, reply_markup=keyboard); return None

    # ── NEW: Guide ──
    elif cmd in ('/guide', 'guide'):
        if _ADMIN_OK:
            msg = format_guide_message()
        else:
            msg = ("<b>NSE Scanner Guide</b>\n\n"
                   "Learn how to read the scanner signals, "
                   "understand scores, and use trade plans.\n\n"
                   "Tap below to open the full guide.")
        keyboard = create_guide_keyboard()
        if is_callback: return {"message": msg, "keyboard": keyboard}
        send_message(chat_id, msg, reply_markup=keyboard); return None

    # ── NEW: Buckets ──
    elif cmd in ('/buckets', 'view_buckets'):
        if not _BUCKET_OK:
            msg = ("<b>Bucketed View</b>\n\n"
                   "Coming soon \u2014 stocks grouped into categories.")
            return respond_view('buckets', msg)
        classification, sd = classify_current_scan()
        if classification:
            msg = format_bucketed_message(classification, sd)
            return respond_view('buckets', msg, create_bucket_keyboard())
        else:
            return respond_view('buckets', "No scan data for bucketed view.")

    # ── NEW: Bucket detail ──
    elif cmd in BUCKET_CB_MAP and _BUCKET_OK:
        bucket_name = BUCKET_CB_MAP[cmd]
        classification, sd = classify_current_scan()
        if classification:
            msg = format_bucket_detail(bucket_name, classification, sd)
            keyboard = create_bucket_detail_keyboard()
            if is_callback: return {"message": msg, "keyboard": keyboard}
            send_message(chat_id, msg, reply_markup=keyboard)
        else:
            msg = "No data for this category."
            if is_callback: return {"message": msg, "keyboard": None}
            send_message(chat_id, msg)
        return None

    # ── NEW: Stock detail card ──
    elif cmd.startswith('stock_') and not cmd.startswith('stock_news_'):
        symbol = cmd.replace('stock_', '').upper()
        if _TRACKER_OK:
            msg = format_signal_card(symbol)
        else:
            msg = f"Signal tracker not available. Stock: <code>{symbol}</code>"
        keyboard = create_signal_card_keyboard(symbol)
        if is_callback: return {"message": msg, "keyboard": keyboard}
        send_message(chat_id, msg, reply_markup=keyboard); return None

    # ── NEW: Back from card ──
    elif cmd == 'back_from_card':
        prev_view = get_user_view(chat_id)
        return handle_command(chat_id, f'view_{prev_view}',
                              is_callback=is_callback, raw_user=raw_user)

    # ── NEW: Admin ──
    elif cmd in ('/admin', 'admin_health'):
        if not _ADMIN_OK or not (raw_user and is_admin(raw_user.get("id", 0))):
            msg = "Admin access only."
            if is_callback: return {"message": msg, "keyboard": None}
            send_message(chat_id, msg); return None
        report  = generate_health_report()
        msg     = format_health_report(report)
        keyboard = create_admin_keyboard()
        if is_callback: return {"message": msg, "keyboard": keyboard}
        send_message(chat_id, msg, reply_markup=keyboard); return None

    elif cmd in ('/users', 'admin_users'):
        if not _ADMIN_OK or not (raw_user and is_admin(raw_user.get("id", 0))):
            msg = "Admin access only."
            if is_callback: return {"message": msg, "keyboard": None}
            send_message(chat_id, msg); return None
        msg = format_user_list()
        keyboard = create_admin_keyboard()
        if is_callback: return {"message": msg, "keyboard": keyboard}
        send_message(chat_id, msg, reply_markup=keyboard); return None

    elif cmd == '/health':
        if _ADMIN_OK and raw_user and is_admin(raw_user.get("id", 0)):
            report = generate_health_report()
            send_message(chat_id, format_health_report(report),
                         reply_markup=create_admin_keyboard())
        else:
            send_message(chat_id, "Admin access only.")
        return None

    elif cmd == 'admin_stats':
        if _ADMIN_OK and raw_user and is_admin(raw_user.get("id", 0)):
            from nse_bot_admin import get_activity_stats
            stats = get_activity_stats(days=1)
            msg  = f"<b>Activity Stats (Today)</b>\n\n"
            msg += f"Total actions: {stats['total_actions']}\n"
            msg += f"Unique users: {stats['unique_users']}\n\n"
            if stats.get("top_actions"):
                msg += "<b>Top Actions:</b>\n"
                for action, count in stats["top_actions"][:8]:
                    msg += f"  <code>{action}</code>: {count}\n"
            if stats.get("hourly"):
                msg += "\n<b>Hourly:</b>\n"
                for hour, count in sorted(stats["hourly"].items()):
                    bar = "\u2588" * min(count // 2, 15)
                    msg += f"  {hour}:00 {bar} {count}\n"
            keyboard = create_admin_keyboard()
            if is_callback: return {"message": msg, "keyboard": keyboard}
            send_message(chat_id, msg, reply_markup=keyboard)
        else:
            msg = "Admin access only."
            if is_callback: return {"message": msg, "keyboard": None}
            send_message(chat_id, msg)
        return None

    # ── Unknown ──
    else:
        ss = sort_stocks(all_stocks, cur_sort)
        tot_pages = max(1, (len(ss) + page_size - 1) // page_size)
        keyboard = create_inline_keyboard(cur_page, tot_pages, cur_sort, cur_view)
        msg = (f"Didn't understand: <code>{_h(cmd)}</code>\n\n"
               f"Try: <b>hi</b>, <b>today</b>, <b>new</b>, <b>exit</b>, "
               f"<b>strong</b>, <b>caution</b>, <b>buckets</b>, <b>guide</b>, <b>help</b>")
        if is_callback: return {"message": msg, "keyboard": keyboard}
        send_message(chat_id, msg, reply_markup=keyboard); return None


# ── Update processor ──────────────────────────────────────────

def process_update(update):
    try:
        if 'callback_query' in update:
            cq       = update['callback_query']
            cq_id    = cq['id']
            chat_id  = str(cq['message']['chat']['id'])
            cb_data  = cq.get('data', '')
            raw_user = cq.get('from', {})
            print(f"[CB]  chat={chat_id}  data={cb_data!r}")
            answer_callback_query(cq_id)
            result = handle_command(chat_id, cb_data, is_callback=True, raw_user=raw_user)
            if isinstance(result, dict):
                msg      = result.get('message')
                keyboard = result.get('keyboard')
                if msg: send_message(chat_id, msg, reply_markup=keyboard)
            return

        if 'message' in update:
            msg_obj  = update['message']
            chat_id  = str(msg_obj['chat']['id'])
            text     = msg_obj.get('text', '').strip()
            raw_user = msg_obj.get('from', {})
            if not text: return
            print(f"[MSG] chat={chat_id}  text={text!r}")
            resolved = resolve_text_to_command(text)
            print(f"[RES] resolved -> {resolved!r}")
            handle_command(chat_id, resolved, is_callback=False, raw_user=raw_user)

    except Exception as e:
        import traceback
        print(f"[ERROR] process_update: {e}")
        traceback.print_exc()


# ── Health check scheduler ────────────────────────────────────

def health_check_scheduler():
    if not _ADMIN_OK:
        log.info("[SCHEDULER] Admin module not loaded")
        return
    log.info("[SCHEDULER] Health check scheduler started (11:30 PM daily)")
    last_sent_date = None
    while True:
        try:
            now = datetime.now()
            if (now.hour == 23 and 30 <= now.minute < 32 and
                    last_sent_date != now.date()):
                log.info("[SCHEDULER] Sending daily health check...")
                ok = send_health_check()
                if ok:
                    last_sent_date = now.date()
                    log.info("[SCHEDULER] Health check sent")
                else:
                    log.error("[SCHEDULER] Health check failed")
            time.sleep(60)
        except Exception as e:
            log.error(f"[SCHEDULER] Error: {e}")
            time.sleep(60)


# ── Startup checks ────────────────────────────────────────────

def startup_checks():
    ok = True
    print("[CHECK] Validating bot token...")
    try:
        r = requests.get(f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/getMe", timeout=5)
        data = r.json()
        if data.get('ok'):
            bot = data['result']
            print(f"[OK]   Bot: @{bot['username']}  ({bot['first_name']})")
        else:
            print(f"[FAIL] Token invalid: {data.get('description')}")
            ok = False
    except Exception as e:
        print(f"[FAIL] getMe: {e}"); ok = False

    print("[CHECK] Checking for webhook...")
    try:
        r  = requests.get(f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/getWebhookInfo", timeout=5)
        wh = r.json().get('result', {}).get('url', '')
        if wh:
            print(f"[WARN] Webhook registered — polling blocked"); ok = False
        else:
            print("[OK]   No webhook — polling will work")
    except Exception as e:
        print(f"[WARN] Webhook check: {e}")

    print(f"[CHECK] Scan results...")
    results = load_scan_results()
    if results:
        print(f"[OK]   {len(results['stocks'])} stocks (date: {results['scan_date']})")
    else:
        print("[FAIL] No scan results"); ok = False

    history = load_history()
    print(f"[CHECK] History: {len(history)} day(s)")
    if len(history) < 2: print("[INFO] New/Exit need 2+ days")
    if len(history) < 5: print(f"[INFO] Strong needs {5-len(history)} more day(s)")

    print(f"[CHECK] Admin module:    {'loaded' if _ADMIN_OK else 'not found'}")
    print(f"[CHECK] Smart buckets:   {'loaded' if _BUCKET_OK else 'not found'}")
    print(f"[CHECK] Signal tracker:  {'loaded' if _TRACKER_OK else 'not found'}")
    if _ADMIN_OK: print(f"[CHECK] Registered users: {get_user_count()}")
    if _TRACKER_OK:
        ts = get_tracker_summary()
        print(f"[CHECK] Tracked signals: {ts.get('total_active',0)} active, "
              f"{ts.get('total_exited',0)} exited")
    print(f"[CHECK] Guide URL: {GUIDE_PDF_URL[:60]}...")

    return ok


# ── Main ──────────────────────────────────────────────────────

def main():
    print("=" * 55)
    print("  NSE Momentum Scanner — Telegram Polling Bot")
    print("  Phase 2.1: Buckets + Guide + Admin + Tracker + Probability")
    print("  Views: Today / New / Exit / Caution / Strong / Buckets")
    print("  Nav: symbol back buttons on all sub-menus")
    print("=" * 55 + "\n")

    if not startup_checks():
        print("\n[BOT] Fix issues above then restart")
        return

    scheduler = threading.Thread(target=health_check_scheduler, daemon=True,
                                 name="health-scheduler")
    scheduler.start()
    if _ADMIN_OK: print("[BOT] Health check scheduler running (11:30 PM daily)")

    print(f"\n[BOT] Ready! Listening... (Ctrl+C to stop)\n")

    last_update_id = None
    while True:
        try:
            updates = get_updates(last_update_id)
            if updates and updates.get('ok') and updates.get('result'):
                for upd in updates['result']:
                    process_update(upd)
                    last_update_id = upd['update_id'] + 1
            time.sleep(1)
        except KeyboardInterrupt:
            print("\n[BOT] Stopped.")
            break
        except Exception as e:
            print(f"[ERROR] Main loop: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
