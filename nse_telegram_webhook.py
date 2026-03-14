"""
nse_telegram_webhook.py — Telegram Webhook Server
===================================================
Flask-based webhook; identical routing logic to the polling bot.

Parse mode : HTML  (robust — avoids MarkdownV2 parse failures)

Commands:
    /start   → Welcome + top stocks sorted by 3M return
    /next    → Next 5 stocks
    /prev    → Previous 5 stocks
    /page N  → Jump to page N
    /list    → Summary of all stocks
    /help    → Show available commands

Installation:
    pip install flask requests

    # Register with Telegram (must be HTTPS):
    python setup_telegram_webhook.py --set-webhook https://YOUR_DOMAIN/webhook

Usage:
    python nse_telegram_webhook.py --port 8080
    python nse_telegram_webhook.py --port 8080 --debug
"""

import json
import sys
import argparse
from datetime import date

try:
    from flask import Flask, request, jsonify
except ImportError:
    print("ERROR: Flask not installed. Run: pip install flask")
    sys.exit(1)

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
        _h,
        _b,
        _code,
        _fmt_return,
        RESULTS_FILE,
        PARSE_MODE,
    )
except ImportError as e:
    print(f"ERROR: nse_telegram_handler.py not found or incomplete: {e}")
    sys.exit(1)

app = Flask(__name__)


# ── Per-user state ────────────────────────────────────────────────────────────
# {'chat_id': {'page': int, 'sort': str}}
_user_state: dict = {}


def _state(chat_id: str) -> dict:
    if chat_id not in _user_state:
        _user_state[chat_id] = {'page': 0, 'sort': '3m'}
    return _user_state[chat_id]

def get_user_page(chat_id: str) -> int:       return _state(chat_id)['page']
def set_user_page(chat_id: str, page: int):   _state(chat_id)['page'] = page
def get_user_sort(chat_id: str) -> str:       return _state(chat_id).get('sort', '3m')
def set_user_sort(chat_id: str, mode: str):   _state(chat_id)['sort'] = mode


# ── Telegram API helpers ──────────────────────────────────────────────────────

def send_message(chat_id, text: str, reply_markup: dict = None) -> bool:
    """Send a Telegram HTML message with optional inline keyboard."""
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
            print(f"[WARN] send_message failed — HTTP {r.status_code}")
            try:
                err = r.json()
                print(f"[WARN] Telegram error: {err.get('description', r.text[:300])}")
            except Exception:
                print(f"[WARN] Raw response: {r.text[:300]}")
            return False
        return True
    except Exception as e:
        print(f"[ERROR] send_message exception: {e}")
        return False


def answer_callback_query(cq_id: str, text: str = ""):
    """Acknowledge inline keyboard tap — removes Telegram's loading spinner."""
    url  = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/answerCallbackQuery"
    data = {'callback_query_id': cq_id}
    if text:
        data['text'] = text
    try:
        requests.post(url, data=data, timeout=5)
    except Exception as e:
        print(f"[ERROR] answerCallbackQuery: {e}")


# ── Inline keyboard ───────────────────────────────────────────────────────────

def create_inline_keyboard(current_page: int, total_pages: int,
                            active_sort: str = '3m') -> dict:
    """
    Build inline keyboard:
      Row 1 — sort toggles (● = active)
      Row 2 — Prev / page counter / Next
      Row 3 — page number pills (max 5)
      Row 4 — Summary + Help
    """
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
    nav.append({"text": f"📄 {current_page + 1}/{total_pages}", "callback_data": "noop"})
    if current_page < total_pages - 1:
        nav.append({"text": "Next ➡️", "callback_data": "next"})
    kb.append(nav)

    # Row 3 — page pills (only when >1 page)
    if total_pages > 1:
        start_p = max(0, min(current_page - 2, total_pages - 5))
        end_p   = min(total_pages, start_p + 5)
        kb.append([
            {
                "text":          f"●{p + 1}" if p == current_page else str(p + 1),
                "callback_data": f"page_{p}",
            }
            for p in range(start_p, end_p)
        ])

    # Row 4 — shortcuts
    kb.append([
        {"text": "📋 Summary", "callback_data": "list"},
        {"text": "❓ Help",    "callback_data": "help"},
    ])

    return {"inline_keyboard": kb}


# ── Command / callback router ─────────────────────────────────────────────────

def handle_command(chat_id: str, text: str, is_callback: bool = False):
    """
    Route a text command or callback_data to the correct response.

    is_callback=True  → returns dict {"message": str, "keyboard": dict|None}
    is_callback=False → calls send_message directly, returns None
    """
    cmd = (text or '').strip().lower()
    if '@' in cmd:
        cmd = cmd.split('@')[0]

    # ── Load data ─────────────────────────────────────────────
    results = load_scan_results()
    if not results:
        msg = "❌ No scan results available. Run the scanner first."
        if is_callback:
            return {"message": msg, "keyboard": None}
        send_message(chat_id, msg)
        return None

    all_stocks = results['stocks']
    page_size  = results['page_size']
    scan_date  = results['scan_date']

    # ── Shared helper ─────────────────────────────────────────
    def respond(page: int, sort_mode: str):
        sorted_stocks = sort_stocks(all_stocks, sort_mode)
        tot_pages     = max(1, (len(sorted_stocks) + page_size - 1) // page_size)
        safe_page     = max(0, min(page, tot_pages - 1))

        set_user_page(chat_id, safe_page)
        set_user_sort(chat_id, sort_mode)

        msg      = format_stock_list(sorted_stocks, safe_page * page_size,
                                     page_size, scan_date)
        keyboard = create_inline_keyboard(safe_page, tot_pages, sort_mode)

        if is_callback:
            return {"message": msg, "keyboard": keyboard}
        send_message(chat_id, msg, reply_markup=keyboard)
        return None

    cur_sort = get_user_sort(chat_id)
    cur_page = get_user_page(chat_id)

    # /start
    if cmd == '/start':
        set_user_sort(chat_id, '3m')
        return respond(0, '3m')

    # /next
    elif cmd in ('/next', '/continue', 'next'):
        sorted_stocks = sort_stocks(all_stocks, cur_sort)
        tot_pages     = max(1, (len(sorted_stocks) + page_size - 1) // page_size)
        if cur_page + 1 >= tot_pages:
            msg = "📊 You've reached the last page!"
            if is_callback:
                return {"message": msg, "keyboard": None}
            send_message(chat_id, msg)
            return None
        return respond(cur_page + 1, cur_sort)

    # /prev
    elif cmd in ('/prev', 'prev'):
        if cur_page == 0:
            msg = "📄 Already on the first page!"
            if is_callback:
                return {"message": msg, "keyboard": None}
            send_message(chat_id, msg)
            return None
        return respond(cur_page - 1, cur_sort)

    # /page N  or  page_N
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

    # sort buttons
    elif cmd == 'sort_3m':
        return respond(0, '3m')

    elif cmd == 'sort_score':
        return respond(0, 'score')

    elif cmd == 'sort_top10':
        return respond(0, 'top10')

    # noop
    elif cmd == 'noop':
        return {"message": None, "keyboard": None} if is_callback else None

    # /list
    elif cmd in ('/list', 'list'):
        top10         = sort_stocks(all_stocks, 'top10')
        sorted_stocks = sort_stocks(all_stocks, cur_sort)
        tot_pages     = max(1, (len(sorted_stocks) + page_size - 1) // page_size)

        msg  = f"📊 {_b('All Scanned Stocks Summary')}\n\n"
        msg += f"Total: {len(all_stocks)} stocks\n"
        msg += f"Scan Date: {_h(scan_date)}\n\n"
        msg += f"{_b('Top 10 by 3M Return:')}\n"
        for j, stock in enumerate(top10, 1):
            r3m = float(stock.get('return_3m_pct', 0))
            msg += (
                f"{j}. {_code(stock['symbol'])} "
                f"— Score: {int(stock.get('score', 0))} "
                f"| 3M: {_fmt_return(r3m)}\n"
            )
        remaining = len(all_stocks) - 10
        if remaining > 0:
            msg += f"\n... and {remaining} more\n"
        msg += f"\nTotal pages: {tot_pages}  (5 per page)\n"
        msg += "Use the buttons below to navigate"

        keyboard = create_inline_keyboard(cur_page, tot_pages, cur_sort)
        if is_callback:
            return {"message": msg, "keyboard": keyboard}
        send_message(chat_id, msg, reply_markup=keyboard)
        return None

    # /help
    elif cmd in ('/help', 'help'):
        sorted_stocks = sort_stocks(all_stocks, cur_sort)
        tot_pages     = max(1, (len(sorted_stocks) + page_size - 1) // page_size)
        keyboard      = create_inline_keyboard(cur_page, tot_pages, cur_sort)
        msg           = format_help()
        if is_callback:
            return {"message": msg, "keyboard": keyboard}
        send_message(chat_id, msg, reply_markup=keyboard)
        return None

    # unknown
    else:
        sorted_stocks = sort_stocks(all_stocks, cur_sort)
        tot_pages     = max(1, (len(sorted_stocks) + page_size - 1) // page_size)
        keyboard      = create_inline_keyboard(cur_page, tot_pages, cur_sort)
        msg           = f"❌ Unknown command: {_code(cmd)}\n\nUse /help for available commands."
        if is_callback:
            return {"message": msg, "keyboard": keyboard}
        send_message(chat_id, msg, reply_markup=keyboard)
        return None


# ── Flask routes ──────────────────────────────────────────────────────────────

@app.route('/webhook', methods=['POST'])
def webhook():
    """Receive and process Telegram updates via webhook."""
    try:
        data = request.get_json(force=True)

        # Inline keyboard button tap
        if 'callback_query' in data:
            cq      = data['callback_query']
            cq_id   = cq['id']
            chat_id = str(cq['message']['chat']['id'])
            cb_data = cq.get('data', '')

            answer_callback_query(cq_id)

            result = handle_command(chat_id, cb_data, is_callback=True)
            if isinstance(result, dict):
                msg      = result.get('message')
                keyboard = result.get('keyboard')
                if msg:
                    send_message(chat_id, msg,
                                 reply_markup=keyboard if keyboard else None)

            return jsonify({"status": "ok"})

        # Regular text message
        if 'message' in data:
            msg_obj = data['message']
            chat_id = str(msg_obj['chat']['id'])
            text    = msg_obj.get('text', '')
            if text.startswith('/'):
                handle_command(chat_id, text, is_callback=False)

        return jsonify({"status": "ok"})

    except Exception as e:
        import traceback
        print(f"[ERROR] webhook: {e}")
        traceback.print_exc()
        return jsonify({"status": "error", "detail": str(e)}), 500


@app.route('/health', methods=['GET'])
def health():
    """Health check — also shows scan metadata."""
    results = load_scan_results()
    return jsonify({
        "status":      "healthy",
        "date":        str(date.today()),
        "scan_date":   results['scan_date']    if results else None,
        "stock_count": results['total_stocks'] if results else 0,
    })


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="NSE Telegram Webhook Server")
    parser.add_argument("--port",  type=int, default=8080, help="Port to listen on (default 8080)")
    parser.add_argument("--debug", action="store_true",    help="Enable Flask debug mode")
    args = parser.parse_args()

    token_preview = getattr(config, 'TELEGRAM_TOKEN', '')[:20]
    print("=" * 55)
    print("  NSE Momentum Scanner — Telegram Webhook Server")
    print("=" * 55)
    print(f"\n  Port      : {args.port}")
    print(f"  Token     : {token_preview}...")
    print(f"  Endpoints : POST /webhook  |  GET /health")
    print(f"\n  To register webhook:")
    print(f"  python setup_telegram_webhook.py --set-webhook https://YOUR_DOMAIN/webhook\n")

    app.run(host='0.0.0.0', port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()