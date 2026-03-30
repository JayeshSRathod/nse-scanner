"""
nse_telegram_polling.py — Telegram Polling Bot (Phase 2)
=========================================================
Views: Today / New / Exit / Strong / Caution
"""

import time
import sys
import json
from datetime import date

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
        load_scan_results,
        load_history,
        sort_stocks,
        format_stock_list,
        format_help,
        format_welcome,
        format_today_scan,
        format_new_stocks,
        format_exit_stocks,
        format_caution_stocks,
        format_strong_stocks,
        get_new_stocks,
        get_exit_stocks,
        get_strong_stocks,
        PARSE_MODE,
        RESULTS_FILE,
        _b, _h, _code, _fmt_return,
    )
    print("[POLL] Handler imports OK")
except ImportError as e:
    print(f"ERROR importing nse_telegram_handler: {e}")
    sys.exit(1)


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
CAUTION_WORDS = {"caution", "risk", "warning", "careful"}
TODAY_WORDS  = {"today", "scan", "aaj"}


def resolve_text_to_command(text):
    clean = text.strip().lower()
    if clean.startswith('/'):
        return clean
    if clean in ('next', 'prev', 'list', 'help', 'news',
                 'sort_3m', 'sort_score', 'sort_top10', 'noop',
                 'view_today', 'view_new', 'view_exit', 'view_caution', 'view_strong') \
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
    if clean in CAUTION_WORDS:   return 'view_caution'
    if clean in TODAY_WORDS:     return 'view_today'
    return clean


_user_state = {}

def _state(chat_id):
    if chat_id not in _user_state:
        _user_state[chat_id] = {'page': 0, 'sort': '3m', 'view': 'today'}
    return _user_state[chat_id]

def get_user_page(chat_id):  return _state(chat_id)['page']
def set_user_page(chat_id, v): _state(chat_id)['page'] = v
def get_user_sort(chat_id):  return _state(chat_id).get('sort', '3m')
def set_user_sort(chat_id, v): _state(chat_id)['sort'] = v
def get_user_view(chat_id):  return _state(chat_id).get('view', 'today')
def set_user_view(chat_id, v): _state(chat_id)['view'] = v


def send_message(chat_id, text, reply_markup=None):
    url  = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage"
    data = {'chat_id': str(chat_id), 'text': text, 'parse_mode': PARSE_MODE}
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


def answer_callback_query(cq_id, text=""):
    url  = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/answerCallbackQuery"
    data = {'callback_query_id': cq_id}
    if text:
        data['text'] = text
    try:
        requests.post(url, data=data, timeout=5)
    except Exception:
        pass


def get_updates(offset=None):
    url    = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/getUpdates"
    params = {'timeout': 30, 'allowed_updates': json.dumps(['message', 'callback_query'])}
    if offset is not None:
        params['offset'] = offset
    try:
        r = requests.get(url, params=params, timeout=35)
        return r.json()
    except Exception as e:
        print(f"[ERROR] get_updates: {e}")
        return None


def create_inline_keyboard(current_page, total_pages, active_sort='3m', active_view='today'):
    kb = []

    kb.append([
        {"text": f"{'●' if active_view == 'today'   else '○'} 📊 Today",   "callback_data": "view_today"},
        {"text": f"{'●' if active_view == 'new'     else '○'} 🆕 New",     "callback_data": "view_new"},
        {"text": f"{'●' if active_view == 'exit'    else '○'} 📉 Exit",    "callback_data": "view_exit"},
    ])

    kb.append([
        {"text": f"{'●' if active_view == 'caution' else '○'} ⚠️ Caution", "callback_data": "view_caution"},
        {"text": f"{'●' if active_view == 'strong'  else '○'} 🔥 Strong",  "callback_data": "view_strong"},
    ])

    if active_view == 'today':
        kb.append([
            {"text": f"{'●' if active_sort == '3m'    else '○'} 📈 3M",    "callback_data": "sort_3m"},
            {"text": f"{'●' if active_sort == 'score' else '○'} ⭐ Score",  "callback_data": "sort_score"},
            {"text": f"{'●' if active_sort == 'top10' else '○'} 🔝 Top10", "callback_data": "sort_top10"},
        ])

    if active_view == 'today' and total_pages > 1:
        nav = []
        if current_page > 0:
            nav.append({"text": "⬅️ Prev", "callback_data": "prev"})
        nav.append({"text": f"📄 {current_page + 1}/{total_pages}", "callback_data": "noop"})
        if current_page < total_pages - 1:
            nav.append({"text": "Next ➡️", "callback_data": "next"})
        kb.append(nav)

        start_p = max(0, min(current_page - 2, total_pages - 5))
        end_p   = min(total_pages, start_p + 5)
        kb.append([
            {"text": f"●{p+1}" if p == current_page else str(p+1),
             "callback_data": f"page_{p}"}
            for p in range(start_p, end_p)
        ])

    kb.append([
        {"text": "📰 News", "callback_data": "news"},
        {"text": "📋 Summary", "callback_data": "list"},
        {"text": "❓ Help", "callback_data": "help"},
    ])

    return {"inline_keyboard": kb}


def handle_command(chat_id, text, is_callback=False):
    cmd = (text or '').strip().lower()
    if '@' in cmd:
        cmd = cmd.split('@')[0]

    print(f"[CMD] chat={chat_id}  cmd={cmd!r}  callback={is_callback}")

    results = load_scan_results()
    if not results:
        msg = "❌ No scan results found.\nPipeline runs at 6:00 AM IST daily."
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

    def respond_today(page, sort_mode):
        sorted_stocks = sort_stocks(all_stocks, sort_mode)
        tot_pages     = max(1, (len(sorted_stocks) + page_size - 1) // page_size)
        safe_page     = max(0, min(page, tot_pages - 1))
        set_user_page(chat_id, safe_page)
        set_user_sort(chat_id, sort_mode)
        set_user_view(chat_id, 'today')
        msg      = format_stock_list(sorted_stocks, safe_page * page_size, page_size, scan_date)
        keyboard = create_inline_keyboard(safe_page, tot_pages, sort_mode, 'today')
        if is_callback:
            return {"message": msg, "keyboard": keyboard}
        send_message(chat_id, msg, reply_markup=keyboard)
        return None

    def respond_view(view_name, msg):
        set_user_view(chat_id, view_name)
        keyboard = create_inline_keyboard(0, 1, cur_sort, view_name)
        if is_callback:
            return {"message": msg, "keyboard": keyboard}
        send_message(chat_id, msg, reply_markup=keyboard)
        return None

    # ── /start ──
    if cmd == '/start':
        msg = format_welcome()
        set_user_view(chat_id, 'today')
        keyboard = create_inline_keyboard(0, 1, '3m', 'today')
        if is_callback:
            return {"message": msg, "keyboard": keyboard}
        send_message(chat_id, msg, reply_markup=keyboard)
        return None

    # ── /today or view_today ──
    elif cmd in ('/today', 'view_today'):
        msg = format_today_scan(all_stocks, scan_date)
        return respond_view('today', msg)

    # ── /next ──
    elif cmd in ('/next', '/continue', 'next'):
        if cur_view != 'today':
            return respond_today(0, cur_sort)
        ss = sort_stocks(all_stocks, cur_sort)
        tot_pages = max(1, (len(ss) + page_size - 1) // page_size)
        if cur_page + 1 >= tot_pages:
            msg = "📊 You've reached the last page!"
            if is_callback: return {"message": msg, "keyboard": None}
            send_message(chat_id, msg)
            return None
        return respond_today(cur_page + 1, cur_sort)

    # ── /prev ──
    elif cmd in ('/prev', 'prev'):
        if cur_view != 'today':
            return respond_today(0, cur_sort)
        if cur_page == 0:
            msg = "📄 Already on the first page!"
            if is_callback: return {"message": msg, "keyboard": None}
            send_message(chat_id, msg)
            return None
        return respond_today(cur_page - 1, cur_sort)

    # ── /page N ──
    elif cmd.startswith('/page') or cmd.startswith('page_'):
        try:
            if cmd.startswith('/page'):
                page_num = int(cmd.split()[1]) - 1
            else:
                page_num = int(cmd.split('_')[1])
            return respond_today(page_num, cur_sort)
        except (IndexError, ValueError):
            msg = "❌ Usage: /page N"
            if is_callback: return {"message": msg, "keyboard": None}
            send_message(chat_id, msg)
            return None

    # ── Sort ──
    elif cmd == 'sort_3m':    return respond_today(0, '3m')
    elif cmd == 'sort_score': return respond_today(0, 'score')
    elif cmd == 'sort_top10': return respond_today(0, 'top10')
    elif cmd == 'noop':
        return {"message": None, "keyboard": None} if is_callback else None

    # ── /new or view_new ──
    elif cmd in ('/new', 'view_new'):
        if len(history) < 2:
            msg = ("⏳ <b>History Building...</b>\n\n"
                   "Need 2+ days of scan history for New Entries.\n"
                   f"Currently have: {len(history)} day(s)\n\n"
                   "Check back tomorrow after 6 AM scan.")
            return respond_view('new', msg)
        new_stocks = get_new_stocks(history)
        msg = format_new_stocks(new_stocks, scan_date)
        return respond_view('new', msg)

    # ── /exit or view_exit ──
    elif cmd in ('/exit', 'view_exit'):
        if len(history) < 2:
            msg = ("⏳ <b>History Building...</b>\n\n"
                   "Need 2+ days of scan history for Exit Watch.\n"
                   f"Currently have: {len(history)} day(s)\n\n"
                   "Check back tomorrow after 6 AM scan.")
            return respond_view('exit', msg)
        exit_stocks = get_exit_stocks(history)
        msg = format_exit_stocks(exit_stocks, scan_date)
        return respond_view('exit', msg)

    # ── /caution or view_caution ──
    elif cmd in ('/caution', 'view_caution'):
        msg = format_caution_stocks(all_stocks, scan_date)
        return respond_view('caution', msg)

    # ── /strong or view_strong ──
    elif cmd in ('/strong', 'view_strong'):
        if len(history) < 5:
            days_left = 5 - len(history)
            msg = (f"🔥 <b>Strong Signals</b>\n\n"
                   f"Needs 5 days of history.\n"
                   f"Currently have: {len(history)} day(s)\n"
                   f"Ready in: {days_left} more trading day(s)")
            return respond_view('strong', msg)
        strong_stocks = get_strong_stocks(history)
        msg = format_strong_stocks(strong_stocks, scan_date)
        return respond_view('strong', msg)

    # ── /news ──
    elif cmd in ('/news', 'news'):
        sorted_stocks = sort_stocks(all_stocks, cur_sort)
        tot_pages = max(1, (len(sorted_stocks) + page_size - 1) // page_size)
        safe_page = max(0, min(cur_page, tot_pages - 1))
        msg = format_stock_list(sorted_stocks, safe_page * page_size,
                                page_size, scan_date, include_news=True)
        keyboard = create_inline_keyboard(safe_page, tot_pages, cur_sort, 'today')
        if is_callback: return {"message": msg, "keyboard": keyboard}
        send_message(chat_id, msg, reply_markup=keyboard)
        return None

    # ── /list ──
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
                           f"🆕 {new_count} new  |  📉 {exit_count} exited  |  🔥 {strong_count} strong\n")

        msg  = f"📊 <b>All Scanned Stocks Summary</b>\n\n"
        msg += f"Total: {len(all_stocks)} stocks  |  Scan: {scan_date}\n"
        msg += history_line
        msg += f"\n<b>Top 10 by 3M Return:</b>\n"
        for j, s in enumerate(top10, 1):
            r3m = float(s.get('return_3m_pct', 0))
            sign = '+' if r3m >= 0 else ''
            msg += f"{j}. <code>{s['symbol']}</code> — {int(s.get('score',0))}/10 | 3M: {sign}{r3m:.1f}%\n"
        remaining = len(all_stocks) - 10
        if remaining > 0:
            msg += f"\n... and {remaining} more\n"

        keyboard = create_inline_keyboard(cur_page, tot_pages, cur_sort, cur_view)
        if is_callback: return {"message": msg, "keyboard": keyboard}
        send_message(chat_id, msg, reply_markup=keyboard)
        return None

    # ── /help ──
    elif cmd in ('/help', 'help'):
        ss = sort_stocks(all_stocks, cur_sort)
        tot_pages = max(1, (len(ss) + page_size - 1) // page_size)
        keyboard = create_inline_keyboard(cur_page, tot_pages, cur_sort, cur_view)
        msg = format_help()
        if is_callback: return {"message": msg, "keyboard": keyboard}
        send_message(chat_id, msg, reply_markup=keyboard)
        return None

    # ── Unknown ──
    else:
        ss = sort_stocks(all_stocks, cur_sort)
        tot_pages = max(1, (len(ss) + page_size - 1) // page_size)
        keyboard = create_inline_keyboard(cur_page, tot_pages, cur_sort, cur_view)
        msg = (f"❓ Didn't understand: <code>{cmd}</code>\n\n"
               f"Try: <b>hi</b>, <b>today</b>, <b>new</b>, <b>exit</b>, "
               f"<b>strong</b>, <b>caution</b>, <b>help</b>")
        if is_callback: return {"message": msg, "keyboard": keyboard}
        send_message(chat_id, msg, reply_markup=keyboard)
        return None


def process_update(update):
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
                    send_message(chat_id, msg, reply_markup=keyboard)
            return

        if 'message' in update:
            msg_obj = update['message']
            chat_id = str(msg_obj['chat']['id'])
            text    = msg_obj.get('text', '').strip()
            if not text:
                return
            print(f"[MSG] chat={chat_id}  text={text!r}")
            resolved = resolve_text_to_command(text)
            print(f"[RES] resolved -> {resolved!r}")
            handle_command(chat_id, resolved, is_callback=False)

    except Exception as e:
        import traceback
        print(f"[ERROR] process_update: {e}")
        traceback.print_exc()


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
        print(f"[FAIL] getMe: {e}")
        ok = False

    print("[CHECK] Checking for webhook...")
    try:
        r  = requests.get(f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/getWebhookInfo", timeout=5)
        wh = r.json().get('result', {}).get('url', '')
        if wh:
            print(f"[WARN] Webhook registered — polling blocked")
            ok = False
        else:
            print("[OK]   No webhook — polling will work")
    except Exception as e:
        print(f"[WARN] Webhook check: {e}")

    print(f"[CHECK] Scan results...")
    results = load_scan_results()
    if results:
        print(f"[OK]   {len(results['stocks'])} stocks (date: {results['scan_date']})")
    else:
        print("[FAIL] No scan results")
        ok = False

    history = load_history()
    print(f"[CHECK] History: {len(history)} day(s)")
    if len(history) < 2:
        print("[INFO] New/Exit views will show 'building' until 2+ days")
    if len(history) < 5:
        print(f"[INFO] Strong view needs {5 - len(history)} more day(s)")

    return ok


def main():
    print("=" * 55)
    print("  NSE Momentum Scanner — Telegram Polling Bot")
    print("  Views: Today / New / Exit / Caution / Strong")
    print("=" * 55 + "\n")

    if not startup_checks():
        print("\n[BOT] Fix issues above then restart")
        return

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
