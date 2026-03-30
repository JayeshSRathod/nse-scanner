"""
nse_telegram_polling.py — Telegram Polling Bot (Phase 2)
=========================================================
Added view buttons:
  📊 Today   → today's 25 stocks (existing)
  🆕 New     → stocks that entered today
  ⚠️ Exit    → stocks that left today
  🔥 Strong  → stocks in list 5+ consecutive days

Smart text handling unchanged.
"""

import time
import sys
import json
from datetime import date

try:
    import requests
except ImportError:
    print("ERROR: requests not installed. Run: pip install requests")
    sys.exit(1)

try:
    import config
except ImportError:
    print("ERROR: config.py not found.")
    sys.exit(1)

try:
    """
nse_telegram_polling.py — 3 EDITS
====================================
EDIT A: Add new imports at the top
EDIT B: Add keyboard + handler functions (paste anywhere above main())
EDIT C: Wire into your existing callback/command handlers
"""


# ══════════════════════════════════════════════════════════════
# EDIT A: ADD these imports alongside your existing ones
# ══════════════════════════════════════════════════════════════

from nse_telegram_handler import (
    load_scan_results,
    load_history,
    sort_stocks,
    format_stock_list,
    format_help,
    format_welcome,          # NEW
    format_today_scan,       # NEW
    format_new_stocks,       # NEW
    format_exit_stocks,      # NEW
    format_caution_stocks,   # NEW
    format_strong_stocks,    # NEW
    get_new_stocks,          # NEW
    get_exit_stocks,         # NEW
    get_strong_stocks,       # NEW
    PARSE_MODE,
)

except ImportError as e:
    print(f"ERROR importing nse_telegram_handler: {e}")
    sys.exit(1)


# ── Greeting + shortcut word lists ────────────────────────────

GREETINGS = {
    "hi", "hii", "hiii", "hello", "hey", "helo", "hlo",
    "start", "begin", "go",
    "good morning", "good evening", "good afternoon",
    "gm", "ge", "ga",
    "namaste", "namaskar", "jai hind",
}

NEXT_WORDS   = {"next", "n", "aage", "more", "forward"}
PREV_WORDS   = {"prev", "previous", "p", "back", "peeche"}
NEWS_WORDS   = {"news", "headline", "headlines", "khabar"}
TOP_WORDS    = {"top", "best", "top10", "winners", "leader"}
LIST_WORDS   = {"list", "all", "summary", "sab"}
HELP_WORDS   = {"help", "?", "commands", "guide", "menu"}
NEW_WORDS    = {"new", "new entry", "fresh", "naya"}
EXIT_WORDS   = {"exit", "exited", "left", "bahar"}
STRONG_WORDS = {"strong", "streak", "consistent", "strong stocks"}


def resolve_text_to_command(text: str) -> str:
    clean = text.strip().lower()

    if clean.startswith('/'):
        return clean

    if clean in ('next', 'prev', 'list', 'help', 'news',
                 'sort_3m', 'sort_score', 'sort_top10', 'noop',
                 'view_today', 'view_new', 'view_exit', 'view_strong') \
       or clean.startswith('page_'):
        return clean

    if clean in GREETINGS:       return '/start'
    if clean.isdigit() and 1 <= int(clean) <= 99:
        return f'/page {clean}'
    if clean.startswith('page ') and clean[5:].isdigit():
        return f'/page {clean[5:]}'
    if clean in NEXT_WORDS:      return '/next'
    if clean in PREV_WORDS:      return '/prev'
    if clean in NEWS_WORDS:      return '/news'
    if clean in TOP_WORDS:       return 'sort_top10'
    if clean in LIST_WORDS:      return '/list'
    if clean in HELP_WORDS:      return '/help'
    if clean in NEW_WORDS:       return 'view_new'
    if clean in EXIT_WORDS:      return 'view_exit'
    if clean in STRONG_WORDS:    return 'view_strong'

    return clean


# ── Per-user state ────────────────────────────────────────────
_user_state: dict = {}

def _state(chat_id: str) -> dict:
    if chat_id not in _user_state:
        _user_state[chat_id] = {'page': 0, 'sort': '3m', 'view': 'today'}
    return _user_state[chat_id]

def get_user_page(chat_id: str) -> int:      return _state(chat_id)['page']
def set_user_page(chat_id: str, v: int):     _state(chat_id)['page'] = v
def get_user_sort(chat_id: str) -> str:      return _state(chat_id).get('sort', '3m')
def set_user_sort(chat_id: str, v: str):     _state(chat_id)['sort'] = v
def get_user_view(chat_id: str) -> str:      return _state(chat_id).get('view', 'today')
def set_user_view(chat_id: str, v: str):     _state(chat_id)['view'] = v


# ── Telegram API helpers ──────────────────────────────────────

def send_message(chat_id, text: str, reply_markup: dict = None) -> bool:
    url  = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage"
    data = {
        'chat_id':    str(chat_id),
        'text':       text,
        'parse_mode': PARSE_MODE,
    }
    if reply_markup:
        data['reply_markup'] = json.dumps(reply_markup)
    try:
        r = requests.post(url, data=data, timeout=10)
        if r.status_code != 200:
            print(f"[WARN] send_message FAILED — HTTP {r.status_code}")
            try:
                print(f"[WARN] {r.json().get('description', r.text[:300])}")
            except Exception:
                print(f"[WARN] {r.text[:300]}")
            return False
        return True
    except Exception as e:
        print(f"[ERROR] send_message: {e}")
        return False


def answer_callback_query(cq_id: str, text: str = ""):
    url  = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/answerCallbackQuery"
    data = {'callback_query_id': cq_id}
    if text:
        data['text'] = text
    try:
        requests.post(url, data=data, timeout=5)
    except Exception as e:
        print(f"[ERROR] answerCallbackQuery: {e}")


def get_updates(offset=None):
    url    = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/getUpdates"
    params = {
        'timeout':         30,
        'allowed_updates': json.dumps(['message', 'callback_query']),
    }
    if offset is not None:
        params['offset'] = offset
    try:
        r = requests.get(url, params=params, timeout=35)
        return r.json()
    except Exception as e:
        print(f"[ERROR] get_updates: {e}")
        return None


# ── Inline keyboard ───────────────────────────────────────────

def create_inline_keyboard(current_page: int, total_pages: int,
                            active_sort: str = '3m',
                            active_view: str = 'today') -> dict:
    kb = []

    # Row 1 — view toggles (NEW)
    kb.append([
        {"text": f"{'●' if active_view == 'today'  else '○'} 📊 Today",
         "callback_data": "view_today"},
        {"text": f"{'●' if active_view == 'new'    else '○'} 🆕 New",
         "callback_data": "view_new"},
        {"text": f"{'●' if active_view == 'exit'   else '○'} ⚠️ Exit",
         "callback_data": "view_exit"},
        {"text": f"{'●' if active_view == 'strong' else '○'} 🔥 Strong",
         "callback_data": "view_strong"},
    ])

    # Row 2 — sort toggles (only shown in today view)
    if active_view == 'today':
        kb.append([
            {"text": f"{'●' if active_sort == '3m'    else '○'} 📈 3M Return",
             "callback_data": "sort_3m"},
            {"text": f"{'●' if active_sort == 'score' else '○'} ⭐ Score",
             "callback_data": "sort_score"},
            {"text": f"{'●' if active_sort == 'top10' else '○'} 🔝 Top 10",
             "callback_data": "sort_top10"},
        ])

    # Row 3 — prev / counter / next (only in today view with pagination)
    if active_view == 'today' and total_pages > 1:
        nav = []
        if current_page > 0:
            nav.append({"text": "⬅️ Prev", "callback_data": "prev"})
        nav.append({"text": f"📄 {current_page + 1}/{total_pages}",
                    "callback_data": "noop"})
        if current_page < total_pages - 1:
            nav.append({"text": "Next ➡️", "callback_data": "next"})
        kb.append(nav)

        # Row 4 — page pills
        start_p = max(0, min(current_page - 2, total_pages - 5))
        end_p   = min(total_pages, start_p + 5)
        kb.append([
            {"text": f"●{p+1}" if p == current_page else str(p+1),
             "callback_data": f"page_{p}"}
            for p in range(start_p, end_p)
        ])

    # Last row — actions
    kb.append([
        {"text": "📰 With News", "callback_data": "news"},
        {"text": "📋 Summary",   "callback_data": "list"},
        {"text": "❓ Help",      "callback_data": "help"},
    ])

    return {"inline_keyboard": kb}


# ── History not ready message ─────────────────────────────────

def _history_not_ready(view_name: str, scan_date: str) -> str:
    return (
        f"⏳ {_b('History Building...')}\n\n"
        f"The {_b(view_name)} view needs at least "
        f"2 days of scan history.\n\n"
        f"Current data: {_h(scan_date)}\n\n"
        f"Check back tomorrow after the 6:00 AM scan runs.\n\n"
        f"💡 Use {_b('📊 Today')} to see today's stocks."
    )


# ── Command / callback router ─────────────────────────────────

def handle_command(chat_id: str, text: str, is_callback: bool = False):
    cmd = (text or '').strip().lower()
    if '@' in cmd:
        cmd = cmd.split('@')[0]

    print(f"[CMD] chat={chat_id}  cmd={cmd!r}  callback={is_callback}")

    # ── Load data ─────────────────────────────────────────────
    results = load_scan_results()
    if not results:
        msg = (
            "❌ No scan results found.\n\n"
            f"Expected: <code>{RESULTS_FILE}</code>\n\n"
            "Pipeline runs at 6:00 AM IST daily."
        )
        if is_callback:
            return {"message": msg, "keyboard": None}
        send_message(chat_id, msg)
        return None

    all_stocks = results['stocks']
    page_size  = results['page_size']
    scan_date  = results['scan_date']
    history    = load_history()

    cur_sort = get_user_sort(chat_id)
    cur_page = get_user_page(chat_id)
    cur_view = get_user_view(chat_id)

    # ── Helper: deliver today view ────────────────────────────
    def respond_today(page: int, sort_mode: str):
        sorted_stocks = sort_stocks(all_stocks, sort_mode)
        tot_pages     = max(1, (len(sorted_stocks) + page_size - 1) // page_size)
        safe_page     = max(0, min(page, tot_pages - 1))

        set_user_page(chat_id, safe_page)
        set_user_sort(chat_id, sort_mode)
        set_user_view(chat_id, 'today')

        msg      = format_stock_list(sorted_stocks, safe_page * page_size,
                                     page_size, scan_date)
        keyboard = create_inline_keyboard(safe_page, tot_pages,
                                          sort_mode, 'today')
        if is_callback:
            return {"message": msg, "keyboard": keyboard}
        send_message(chat_id, msg, reply_markup=keyboard)
        return None

    # ── Helper: deliver non-paginated view ────────────────────
    def respond_view(view_name: str, msg: str):
        set_user_view(chat_id, view_name)
        keyboard = create_inline_keyboard(0, 1, cur_sort, view_name)
        if is_callback:
            return {"message": msg, "keyboard": keyboard}
        send_message(chat_id, msg, reply_markup=keyboard)
        return None

    # ── Route ─────────────────────────────────────────────────

    # /start
    if cmd == '/start':
        set_user_sort(chat_id, '3m')
        return respond_today(0, '3m')

    # /next
    elif cmd in ('/next', '/continue', 'next'):
        if cur_view != 'today':
            return respond_today(0, cur_sort)
        ss        = sort_stocks(all_stocks, cur_sort)
        tot_pages = max(1, (len(ss) + page_size - 1) // page_size)
        if cur_page + 1 >= tot_pages:
            msg = "📊 You've reached the last page!"
            if is_callback:
                return {"message": msg, "keyboard": None}
            send_message(chat_id, msg)
            return None
        return respond_today(cur_page + 1, cur_sort)

    # /prev
    elif cmd in ('/prev', 'prev'):
        if cur_view != 'today':
            return respond_today(0, cur_sort)
        if cur_page == 0:
            msg = "📄 Already on the first page!"
            if is_callback:
                return {"message": msg, "keyboard": None}
            send_message(chat_id, msg)
            return None
        return respond_today(cur_page - 1, cur_sort)

    # /page N
    elif cmd.startswith('/page') or cmd.startswith('page_'):
        try:
            if cmd.startswith('/page'):
                page_num = int(cmd.split()[1]) - 1
            else:
                page_num = int(cmd.split('_')[1])
            return respond_today(page_num, cur_sort)
        except (IndexError, ValueError):
            msg = "❌ Usage: /page N  (e.g. /page 2)"
            if is_callback:
                return {"message": msg, "keyboard": None}
            send_message(chat_id, msg)
            return None

    # Sort buttons
    elif cmd == 'sort_3m':
        return respond_today(0, '3m')
    elif cmd == 'sort_score':
        return respond_today(0, 'score')
    elif cmd == 'sort_top10':
        return respond_today(0, 'top10')

    # noop
    elif cmd == 'noop':
        return {"message": None, "keyboard": None} if is_callback else None

    # ── View buttons ──────────────────────────────────────────

    elif cmd == 'view_today':
        return respond_today(0, cur_sort)

    elif cmd == 'view_new':
        if len(history) < 2:
            return respond_view('new',
                _history_not_ready('🆕 New Entries', scan_date))
        new_stocks = get_new_stocks(history)
        msg        = format_new_stocks(new_stocks, scan_date)
        return respond_view('new', msg)

    elif cmd == 'view_exit':
        if len(history) < 2:
            return respond_view('exit',
                _history_not_ready('⚠️ Exit Signals', scan_date))
        exit_stocks = get_exit_stocks(history)
        msg         = format_exit_stocks(exit_stocks, scan_date)
        return respond_view('exit', msg)

    elif cmd == 'view_strong':
        if len(history) < 5:
            days_left = 5 - len(history)
            msg = (
                f"🔥 {_b('Strong Signals')}\n\n"
                f"Needs 5 days of history.\n"
                f"Currently have: {len(history)} day(s)\n"
                f"Ready in: {days_left} more trading day(s)\n\n"
                f"💡 Check back in {days_left} days!"
            )
            return respond_view('strong', msg)
        strong_stocks = get_strong_stocks(history)
        msg           = format_strong_stocks(strong_stocks, scan_date)
        return respond_view('strong', msg)

    # /news
    elif cmd in ('/news', 'news'):
        sorted_stocks = sort_stocks(all_stocks, cur_sort)
        tot_pages     = max(1, (len(sorted_stocks) + page_size - 1) // page_size)
        safe_page     = max(0, min(cur_page, tot_pages - 1))
        msg           = format_stock_list(sorted_stocks, safe_page * page_size,
                                          page_size, scan_date,
                                          include_news=True)
        keyboard      = create_inline_keyboard(safe_page, tot_pages,
                                               cur_sort, 'today')
        if is_callback:
            return {"message": msg, "keyboard": keyboard}
        send_message(chat_id, msg, reply_markup=keyboard)
        return None

    # /list
    elif cmd in ('/list', 'list'):
        top10         = sort_stocks(all_stocks, 'top10')
        sorted_stocks = sort_stocks(all_stocks, cur_sort)
        tot_pages     = max(1, (len(sorted_stocks) + page_size - 1) // page_size)

        # History summary
        history_line = ""
        if len(history) >= 2:
            new_count    = len(get_new_stocks(history))
            exit_count   = len(get_exit_stocks(history))
            strong_count = len(get_strong_stocks(history))
            history_line = (
                f"\n{_b('Today:')}\n"
                f"🆕 {new_count} new  |  "
                f"⚠️ {exit_count} exited  |  "
                f"🔥 {strong_count} strong\n"
            )

        msg  = f"📊 {_b('All Scanned Stocks Summary')}\n\n"
        msg += f"Total: {len(all_stocks)} stocks  |  Scan: {_h(scan_date)}\n"
        msg += history_line
        msg += f"\n{_b('Top 10 by 3M Return:')}\n"
        for j, s in enumerate(top10, 1):
            r3m = float(s.get('return_3m_pct', 0))
            msg += (f"{j}. {_code(s['symbol'])} "
                    f"— {int(s.get('score',0))}/10 "
                    f"| 3M: {_fmt_return(r3m)}\n")
        remaining = len(all_stocks) - 10
        if remaining > 0:
            msg += f"\n... and {remaining} more\n"
        msg += f"\nTotal pages: {tot_pages}  (5 per page)"

        keyboard = create_inline_keyboard(cur_page, tot_pages,
                                          cur_sort, cur_view)
        if is_callback:
            return {"message": msg, "keyboard": keyboard}
        send_message(chat_id, msg, reply_markup=keyboard)
        return None

    # /help
    elif cmd in ('/help', 'help'):
        ss        = sort_stocks(all_stocks, cur_sort)
        tot_pages = max(1, (len(ss) + page_size - 1) // page_size)
        keyboard  = create_inline_keyboard(cur_page, tot_pages,
                                           cur_sort, cur_view)
        msg       = format_help()
        if is_callback:
            return {"message": msg, "keyboard": keyboard}
        send_message(chat_id, msg, reply_markup=keyboard)
        return None

    # Unknown
    else:
        ss        = sort_stocks(all_stocks, cur_sort)
        tot_pages = max(1, (len(ss) + page_size - 1) // page_size)
        keyboard  = create_inline_keyboard(cur_page, tot_pages,
                                           cur_sort, cur_view)
        msg = (
            f"❓ Didn't understand: {_code(cmd)}\n\n"
            f"Try:\n"
            f"• <b>hi</b> — top stocks\n"
            f"• <b>new</b> — new entries today\n"
            f"• <b>exit</b> — stocks that left\n"
            f"• <b>strong</b> — 5+ day streak\n"
            f"• <b>next</b> — next page\n"
            f"• <b>help</b> — all commands"
        )
        if is_callback:
            return {"message": msg, "keyboard": keyboard}
        send_message(chat_id, msg, reply_markup=keyboard)
        return None


# ── Update processor ──────────────────────────────────────────

def process_update(update: dict):
    try:
        if 'callback_query' in update:
            cq      = update['callback_query']
            cq_id   = cq['id']
            chat_id = str(cq['message']['chat']['id'])
            cb_data = cq.get('data', '')
            print(f"[CB]  chat={chat_id}  data={cb_data!r}")
            answer_callback_query(cq_id)
            result = handle_command(chat_id, cb_data, is_callback=True)
            if isinstance(result, dict):
                msg      = result.get('message')
                keyboard = result.get('keyboard')
                if msg:
                    send_message(chat_id, msg,
                                 reply_markup=keyboard if keyboard else None)
            return

        if 'message' in update:
            msg_obj = update['message']
            chat_id = str(msg_obj['chat']['id'])
            text    = msg_obj.get('text', '').strip()
            if not text:
                return
            print(f"[MSG] chat={chat_id}  text={text!r}")
            resolved = resolve_text_to_command(text)
            print(f"[RES] resolved → {resolved!r}")
            handle_command(chat_id, resolved, is_callback=False)

    except Exception as e:
        import traceback
        print(f"[ERROR] process_update: {e}")
        traceback.print_exc()


# ── Startup checks ────────────────────────────────────────────

def startup_checks() -> bool:
    ok = True
    print("[CHECK] Validating bot token...")
    try:
        r    = requests.get(
            f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/getMe",
            timeout=5)
        data = r.json()
        if data.get('ok'):
            bot = data['result']
            print(f"[OK]   Bot: @{bot['username']}  ({bot['first_name']})")
        else:
            print(f"[FAIL] Token invalid: {data.get('description')}")
            ok = False
    except Exception as e:
        print(f"[FAIL] getMe: {e}")
        ok = False

    print("[CHECK] Checking for webhook...")
    try:
        r  = requests.get(
            f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/getWebhookInfo",
            timeout=5)
        wh = r.json().get('result', {}).get('url', '')
        if wh:
            print(f"[WARN] Webhook registered — polling blocked")
            ok = False
        else:
            print("[OK]   No webhook — polling will work")
    except Exception as e:
        print(f"[WARN] Webhook check failed: {e}")

    print(f"[CHECK] Scan results: {RESULTS_FILE}")
    results = load_scan_results()
    if results:
        print(f"[OK]   {len(results['stocks'])} stocks "
              f"(date: {results['scan_date']})")
    else:
        print("[FAIL] No scan results")
        ok = False

    history = load_history()
    print(f"[CHECK] History: {len(history)} day(s) stored")
    if len(history) == 0:
        print("[INFO] No history yet — New/Exit/Strong views will show "
              "'building' message until tomorrow")
    elif len(history) < 5:
        print(f"[INFO] {5 - len(history)} more day(s) until Strong view works")

    return ok

# ══════════════════════════════════════════════════════════════
# EDIT B: ADD these functions (paste above your main() function)
# ══════════════════════════════════════════════════════════════

def get_main_keyboard():
    """Primary navigation keyboard with all views."""
    return {"inline_keyboard": [
        [{"text": "📊 Today",   "callback_data": "view_today"},
         {"text": "🆕 New",     "callback_data": "view_new"},
         {"text": "📉 Exit",    "callback_data": "view_exit"}],
        [{"text": "⚠️ Caution", "callback_data": "view_caution"},
         {"text": "🔥 Strong",  "callback_data": "view_strong"},
         {"text": "❓ Help",     "callback_data": "help"}],
    ]}


def get_list_keyboard():
    """Navigation keyboard for paginated list view."""
    return {"inline_keyboard": [
        [{"text": "⬅️ Prev", "callback_data": "prev"},
         {"text": "➡️ Next", "callback_data": "next"}],
        [{"text": "📈 3M",   "callback_data": "sort_3m"},
         {"text": "⭐ Score", "callback_data": "sort_score"},
         {"text": "🔝 Top10", "callback_data": "sort_top10"}],
        [{"text": "📊 Back", "callback_data": "view_today"},
         {"text": "❓ Help",  "callback_data": "help"}],
    ]}


def handle_new_views(callback_data, chat_id=None):
    """
    Handle new view callbacks. Returns (message, keyboard) or (None, None).

    Call this from your existing handle_callback():
        msg, kb = handle_new_views(data)
        if msg:
            # send msg with kb
            return
        # ... existing callback handling ...
    """
    res = load_scan_results()
    if not res:
        return ("No scan data yet. Pipeline hasn't run today.",
                get_main_keyboard())

    stocks    = res['stocks']
    scan_date = res.get('scan_date', '')
    history   = load_history()
    msg, kb = handle_new_views(callback_data)
     if msg:
         answer_callback(callback_query_id)
         edit_message(chat_id, message_id, msg, kb)
         return
  
    if callback_data == "view_today":
        return format_today_scan(stocks, scan_date), get_main_keyboard()

    elif callback_data == "view_new":
        return format_new_stocks(get_new_stocks(history), scan_date), get_main_keyboard()

    elif callback_data == "view_exit":
        return format_exit_stocks(get_exit_stocks(history), scan_date), get_main_keyboard()

    elif callback_data == "view_caution":
        return format_caution_stocks(stocks, scan_date), get_main_keyboard()

    elif callback_data == "view_strong":
        return format_strong_stocks(get_strong_stocks(history), scan_date), get_main_keyboard()

    return None, None


def handle_new_commands(text, chat_id=None, user_name=None):
    """
    Handle new slash commands. Returns (message, keyboard) or (None, None).

    Call this from your existing command handler:
        msg, kb = handle_new_commands(text, chat_id, first_name)
        if msg:
            # send msg with kb
            return
        # ... existing command handling ...
    """
    res = load_scan_results()
    msg, kb = handle_new_commands(text, chat_id, first_name)
     if msg:
         send_message(chat_id, msg, kb)
         return

    if text in ("/start", "hi", "hello", "Hi", "Hello"):
        return format_welcome(user_name), get_main_keyboard()

    if not res:
        return ("No scan data yet.", get_main_keyboard())

    stocks    = res['stocks']
    scan_date = res.get('scan_date', '')
    history   = load_history()

    if text == "/today":
        return format_today_scan(stocks, scan_date), get_main_keyboard()
    elif text == "/new":
        return format_new_stocks(get_new_stocks(history), scan_date), get_main_keyboard()
    elif text == "/exit":
        return format_exit_stocks(get_exit_stocks(history), scan_date), get_main_keyboard()
    elif text == "/caution":
        return format_caution_stocks(stocks, scan_date), get_main_keyboard()
    elif text == "/strong":
        return format_strong_stocks(get_strong_stocks(history), scan_date), get_main_keyboard()

    return None, None

# ── Main polling loop ─────────────────────────────────────────

def main():
    print("=" * 55)
    print("  NSE Momentum Scanner — Telegram Polling Bot")
    print("  Phase 2: Today / New / Exit / Strong views")
    print("=" * 55 + "\n")

    if not startup_checks():
        print("\n[BOT] Fix issues above then restart")
        return

    print(f"\n[BOT] Ready!")
    print(f"       Commands : /start /next /prev /page N /list /help /news")
    print(f"       Greetings: hi, hello, hey, namaste")
    print(f"       Views    : new, exit, strong")
    print(f"       Numbers  : 1-9 (jump to page)")
    print(f"\n[BOT] Listening... (Ctrl+C to stop)\n")

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
