"""
nse_telegram_polling.py — Telegram Polling Bot
===============================================
Long-polling bot. Use when you cannot expose a public HTTPS endpoint.

Parse mode : HTML

Smart message handling:
  - "hi", "hello", "hey" etc  → same as /start
  - "next", "n"               → same as /next
  - "prev", "p"               → same as /prev
  - "1" to "9"                → jump to that page
  - "news"                    → current page with news
  - "top", "best"             → top 10 by 3M return
  - "list", "all"             → summary
  - "help", "?"               → help
  - /commands                 → work as before

Usage:
    python nse_telegram_polling.py
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
    from nse_telegram_handler import (
        load_scan_results,
        sort_stocks,
        format_stock_list,
        format_help,
        fetch_news_for_symbol,
        _h, _b, _code,
        _fmt_return,
        RESULTS_FILE,
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

NEXT_WORDS  = {"next", "n", "aage", "more", "forward"}
PREV_WORDS  = {"prev", "previous", "p", "back", "peeche"}
NEWS_WORDS  = {"news", "headline", "headlines", "khabar"}
TOP_WORDS   = {"top", "best", "top10", "winners", "leader"}
LIST_WORDS  = {"list", "all", "summary", "sab"}
HELP_WORDS  = {"help", "?", "commands", "guide", "menu"}


def resolve_text_to_command(text: str) -> str:
    """
    Convert any plain-text message to an internal command string.

    Returns one of:
        '/start', '/next', '/prev', '/list', '/help',
        '/news', 'sort_top10', 'page_N',
        or the original text (for /commands and unknown inputs)
    """
    clean = text.strip().lower()

    # Already a /command — pass through unchanged
    if clean.startswith('/'):
        return clean

    # Callback data words (from inline buttons) — pass through
    if clean in ('next', 'prev', 'list', 'help', 'news',
                 'sort_3m', 'sort_score', 'sort_top10', 'noop') \
       or clean.startswith('page_'):
        return clean

    # Greeting → /start
    if clean in GREETINGS:
        return '/start'

    # Single digit or "page N" → jump to page
    if clean.isdigit() and 1 <= int(clean) <= 99:
        return f'/page {clean}'

    if clean.startswith('page ') and clean[5:].isdigit():
        return f'/page {clean[5:]}'

    # Navigation shortcuts
    if clean in NEXT_WORDS:
        return '/next'

    if clean in PREV_WORDS:
        return '/prev'

    # News
    if clean in NEWS_WORDS:
        return '/news'

    # Top 10
    if clean in TOP_WORDS:
        return 'sort_top10'

    # List / summary
    if clean in LIST_WORDS:
        return '/list'

    # Help
    if clean in HELP_WORDS:
        return '/help'

    # Unknown plain text — return as-is so handle_command shows "unknown"
    return clean


# ── Per-user state ────────────────────────────────────────────
_user_state: dict = {}

def _state(chat_id: str) -> dict:
    if chat_id not in _user_state:
        _user_state[chat_id] = {'page': 0, 'sort': '3m'}
    return _user_state[chat_id]

def get_user_page(chat_id: str) -> int:      return _state(chat_id)['page']
def set_user_page(chat_id: str, v: int):     _state(chat_id)['page'] = v
def get_user_sort(chat_id: str) -> str:      return _state(chat_id).get('sort', '3m')
def set_user_sort(chat_id: str, v: str):     _state(chat_id)['sort'] = v


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
                print(f"[WARN] Telegram: {r.json().get('description', r.text[:300])}")
            except Exception:
                print(f"[WARN] Raw: {r.text[:300]}")
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
                            active_sort: str = '3m') -> dict:
    kb = []

    # Row 1 — sort toggles
    kb.append([
        {"text": f"{'●' if active_sort == '3m'    else '○'} 📈 3M Return",
         "callback_data": "sort_3m"},
        {"text": f"{'●' if active_sort == 'score' else '○'} ⭐ Score",
         "callback_data": "sort_score"},
        {"text": f"{'●' if active_sort == 'top10' else '○'} 🔝 Top 10",
         "callback_data": "sort_top10"},
    ])

    # Row 2 — prev / counter / next
    nav = []
    if current_page > 0:
        nav.append({"text": "⬅️ Prev", "callback_data": "prev"})
    nav.append({"text": f"📄 {current_page + 1}/{total_pages}",
                "callback_data": "noop"})
    if current_page < total_pages - 1:
        nav.append({"text": "Next ➡️", "callback_data": "next"})
    kb.append(nav)

    # Row 3 — page pills
    if total_pages > 1:
        start_p = max(0, min(current_page - 2, total_pages - 5))
        end_p   = min(total_pages, start_p + 5)
        kb.append([
            {"text": f"●{p+1}" if p == current_page else str(p+1),
             "callback_data": f"page_{p}"}
            for p in range(start_p, end_p)
        ])

    # Row 4 — news + shortcuts
    kb.append([
        {"text": "📰 With News", "callback_data": "news"},
        {"text": "📋 Summary",   "callback_data": "list"},
        {"text": "❓ Help",      "callback_data": "help"},
    ])

    return {"inline_keyboard": kb}


# ── Command / callback router ─────────────────────────────────

def handle_command(chat_id: str, text: str, is_callback: bool = False):
    """
    Route command or callback to the correct response.
    is_callback=True  → returns {"message": str, "keyboard": dict|None}
    is_callback=False → calls send_message directly, returns None
    """
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
            "Run the scanner first:\n"
            "<code>python nse_scanner.py</code>"
        )
        if is_callback:
            return {"message": msg, "keyboard": None}
        send_message(chat_id, msg)
        return None

    all_stocks = results['stocks']
    page_size  = results['page_size']
    scan_date  = results['scan_date']

    # ── Helper ────────────────────────────────────────────────
    def respond(page: int, sort_mode: str, with_news: bool = False):
        sorted_stocks = sort_stocks(all_stocks, sort_mode)
        tot_pages     = max(1, (len(sorted_stocks) + page_size - 1) // page_size)
        safe_page     = max(0, min(page, tot_pages - 1))

        set_user_page(chat_id, safe_page)
        set_user_sort(chat_id, sort_mode)

        msg      = format_stock_list(sorted_stocks, safe_page * page_size,
                                     page_size, scan_date,
                                     include_news=with_news)
        keyboard = create_inline_keyboard(safe_page, tot_pages, sort_mode)

        if is_callback:
            return {"message": msg, "keyboard": keyboard}
        send_message(chat_id, msg, reply_markup=keyboard)
        return None

    cur_sort = get_user_sort(chat_id)
    cur_page = get_user_page(chat_id)

    # ── Route ─────────────────────────────────────────────────

    if cmd == '/start':
        set_user_sort(chat_id, '3m')
        return respond(0, '3m')

    elif cmd in ('/next', '/continue', 'next'):
        ss        = sort_stocks(all_stocks, cur_sort)
        tot_pages = max(1, (len(ss) + page_size - 1) // page_size)
        if cur_page + 1 >= tot_pages:
            msg = "📊 You've reached the last page!"
            if is_callback:
                return {"message": msg, "keyboard": None}
            send_message(chat_id, msg)
            return None
        return respond(cur_page + 1, cur_sort)

    elif cmd in ('/prev', 'prev'):
        if cur_page == 0:
            msg = "📄 Already on the first page!"
            if is_callback:
                return {"message": msg, "keyboard": None}
            send_message(chat_id, msg)
            return None
        return respond(cur_page - 1, cur_sort)

    elif cmd.startswith('/page') or cmd.startswith('page_'):
        try:
            if cmd.startswith('/page'):
                page_num = int(cmd.split()[1]) - 1
            else:
                page_num = int(cmd.split('_')[1])
            return respond(page_num, cur_sort)
        except (IndexError, ValueError):
            msg = "❌ Usage: /page N  (e.g. /page 2)"
            if is_callback:
                return {"message": msg, "keyboard": None}
            send_message(chat_id, msg)
            return None

    elif cmd in ('/news', 'news'):
        return respond(cur_page, cur_sort, with_news=True)

    elif cmd == 'sort_3m':
        return respond(0, '3m')

    elif cmd == 'sort_score':
        return respond(0, 'score')

    elif cmd == 'sort_top10':
        return respond(0, 'top10')

    elif cmd == 'noop':
        return {"message": None, "keyboard": None} if is_callback else None

    elif cmd in ('/list', 'list'):
        top10         = sort_stocks(all_stocks, 'top10')
        sorted_stocks = sort_stocks(all_stocks, cur_sort)
        tot_pages     = max(1, (len(sorted_stocks) + page_size - 1) // page_size)

        msg  = f"📊 {_b('All Scanned Stocks Summary')}\n\n"
        msg += f"Total: {len(all_stocks)} stocks  |  Scan: {_h(scan_date)}\n\n"
        msg += f"{_b('Top 10 by 3M Return:')}\n"
        for j, s in enumerate(top10, 1):
            r3m = float(s.get('return_3m_pct', 0))
            msg += (f"{j}. {_code(s['symbol'])} "
                    f"— {int(s.get('score',0))}/10 "
                    f"| 3M: {_fmt_return(r3m)}\n")
        remaining = len(all_stocks) - 10
        if remaining > 0:
            msg += f"\n... and {remaining} more stocks\n"
        msg += f"\nTotal pages: {tot_pages}  (5 per page)"

        keyboard = create_inline_keyboard(cur_page, tot_pages, cur_sort)
        if is_callback:
            return {"message": msg, "keyboard": keyboard}
        send_message(chat_id, msg, reply_markup=keyboard)
        return None

    elif cmd in ('/help', 'help'):
        ss        = sort_stocks(all_stocks, cur_sort)
        tot_pages = max(1, (len(ss) + page_size - 1) // page_size)
        keyboard  = create_inline_keyboard(cur_page, tot_pages, cur_sort)
        msg       = format_help()
        if is_callback:
            return {"message": msg, "keyboard": keyboard}
        send_message(chat_id, msg, reply_markup=keyboard)
        return None

    else:
        ss        = sort_stocks(all_stocks, cur_sort)
        tot_pages = max(1, (len(ss) + page_size - 1) // page_size)
        keyboard  = create_inline_keyboard(cur_page, tot_pages, cur_sort)
        msg = (
            f"❓ Didn't understand: {_code(cmd)}\n\n"
            f"Try saying:\n"
            f"• <b>hi</b> — show top stocks\n"
            f"• <b>next</b> — next page\n"
            f"• <b>3</b> — jump to page 3\n"
            f"• <b>top</b> — top 10 stocks\n"
            f"• <b>news</b> — with headlines\n"
            f"• <b>help</b> — all commands"
        )
        if is_callback:
            return {"message": msg, "keyboard": keyboard}
        send_message(chat_id, msg, reply_markup=keyboard)
        return None


# ── Update processor ──────────────────────────────────────────

def process_update(update: dict):
    """Process one Telegram update — message or callback_query."""
    try:
        # ── Inline button tap ─────────────────────────────────
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

        # ── Text message ──────────────────────────────────────
        if 'message' in update:
            msg_obj = update['message']
            chat_id = str(msg_obj['chat']['id'])
            text    = msg_obj.get('text', '').strip()

            if not text:
                return   # ignore stickers, photos, etc.

            print(f"[MSG] chat={chat_id}  text={text!r}")

            # ── Smart resolver — converts plain text to command ──
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
        print(f"[FAIL] getMe failed: {e}")
        ok = False

    print("[CHECK] Checking for registered webhook...")
    try:
        r    = requests.get(
            f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/getWebhookInfo",
            timeout=5)
        wh   = r.json().get('result', {}).get('url', '')
        if wh:
            print(f"[WARN] Webhook registered: {wh}")
            print("[WARN] POLLING WILL NOT WORK — run:")
            print("[WARN]   python setup_telegram_webhook.py --delete-webhook")
            ok = False
        else:
            print("[OK]   No webhook — polling will work")
    except Exception as e:
        print(f"[WARN] Could not check webhook: {e}")

    print(f"[CHECK] Looking for scan results: {RESULTS_FILE}")
    results = load_scan_results()
    if results:
        print(f"[OK]   {len(results['stocks'])} stocks  "
              f"(scan date: {results['scan_date']})")
    else:
        print("[FAIL] Scan results not found — run nse_daily_runner.py first")
        ok = False

    return ok


# ── Main polling loop ─────────────────────────────────────────

def main():
    print("=" * 55)
    print("  NSE Momentum Scanner — Telegram Polling Bot")
    print("=" * 55 + "\n")

    if not startup_checks():
        print("\n[BOT] Fix issues above then restart")
        return

    print(f"\n[BOT] Ready! Accepted inputs:")
    print(f"       Commands : /start /next /prev /page N /list /help /news")
    print(f"       Greetings: hi, hello, hey, namaste ...")
    print(f"       Shortcuts: next, prev, top, news, list, help")
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