"""
nse_telegram_polling.py — Telegram Polling Bot (Phase 2.2)
============================================================
Views: Today / New / Exit / Caution / Strong / Buckets / Digest / Guide
Admin: /admin, /users, /health
"""

import time, sys, json, os, threading, logging, sqlite3
from datetime import date, datetime, timedelta

try: import requests
except ImportError: print("ERROR: requests"); sys.exit(1)

try: import config
except ImportError: print("ERROR: config.py"); sys.exit(1)

try:
    from nse_telegram_handler import (
        load_scan_results, load_history, sort_stocks,
        format_stock_list, format_help, format_welcome,
        format_today_scan, format_new_stocks, format_exit_stocks,
        format_caution_stocks, format_strong_stocks, format_summary,
        get_new_stocks, get_exit_stocks, get_strong_stocks,
        PARSE_MODE, RESULTS_FILE, _b, _h, _code, _fmt_return,
    )
    print("[POLL] Handler imports OK")
except ImportError as e:
    print(f"ERROR: {e}"); sys.exit(1)

_ADMIN_OK = _BUCKET_OK = _TRACKER_OK = _DIGEST_OK = False

try:
    from nse_bot_admin import (
        track_user, log_activity, is_admin, is_blocked,
        format_health_report, format_user_list,
        generate_health_report, send_health_check,
        format_guide_message, get_user_count,
    )
    _ADMIN_OK = True; print("[POLL] Admin loaded")
except ImportError:
    def track_user(u): pass
    def log_activity(uid, t, d): pass
    def is_admin(uid): return False
    def is_blocked(uid): return False
    def get_user_count(): return 0

try:
    from nse_smart_buckets import (
        classify_current_scan, format_bucketed_message,
        format_bucket_detail, BUCKET_RISING, BUCKET_UPTREND,
        BUCKET_PEAK, BUCKET_RECOVERY, BUCKET_SAFE, BUCKET_CAUTION,
    )
    _BUCKET_OK = True; print("[POLL] Buckets loaded")
except ImportError: pass

try:
    from nse_signal_tracker import (
        get_signal, get_tracker_summary, calculate_probability,
        format_signal_card,
    )
    _TRACKER_OK = True; print("[POLL] Tracker loaded")
except ImportError:
    def get_signal(s): return None
    def get_tracker_summary(): return {}

try:
    from nse_weekly_digest import (
        get_week_dates, get_week_history, get_week_prices,
        analyze_week, format_weekly_digest,
    )
    _DIGEST_OK = True; print("[POLL] Digest loaded")
except ImportError:
    print("[WARN] nse_weekly_digest not found")

os.makedirs("logs", exist_ok=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler("logs/polling_bot.log", encoding="utf-8"), logging.StreamHandler()])
log = logging.getLogger(__name__)

GUIDE_PDF_URL = os.environ.get("GUIDE_PDF_URL",
    "https://htmlpreview.github.io/?https://github.com/JayeshSRathod/nse-scanner/blob/main/docs/NSE_Scanner_Guide.html")

class FakeUser:
    def __init__(self, d):
        d = d or {}
        self.id = d.get("id", 0); self.username = d.get("username", "")
        self.first_name = d.get("first_name", ""); self.last_name = d.get("last_name", "")

# ── NLP ───────────────────────────────────────────────────────
GREETINGS     = {"hi","hii","hiii","hello","hey","helo","hlo","start","begin","go",
                 "good morning","good evening","good afternoon","gm","ge","ga",
                 "namaste","namaskar","jai hind"}
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
DIGEST_WORDS  = {"digest","weekly","week","performance","hafta"}

def resolve_text_to_command(text):
    c = text.strip().lower()
    if c.startswith('/'): return c
    if c in ('next','prev','list','help','news','sort_3m','sort_score','sort_top10',
             'noop','view_today','view_new','view_exit','view_caution','view_strong',
             'view_buckets','summary') or c.startswith('page_') or c.startswith('bucket_') \
             or c.startswith('stock_'): return c
    if c in GREETINGS: return '/start'
    if c.isdigit() and 1<=int(c)<=99: return f'/page {c}'
    if c.startswith('page ') and c[5:].isdigit(): return f'/page {c[5:]}'
    if c in NEXT_WORDS: return '/next'
    if c in PREV_WORDS: return '/prev'
    if c in NEWS_WORDS: return '/news'
    if c in TOP_WORDS: return 'sort_top10'
    if c in LIST_WORDS: return 'summary'
    if c in HELP_WORDS: return '/help'
    if c in NEW_WORDS: return 'view_new'
    if c in EXIT_WORDS: return 'view_exit'
    if c in STRONG_WORDS: return 'view_strong'
    if c in CAUTION_WORDS: return 'view_caution'
    if c in TODAY_WORDS: return 'view_today'
    if c in GUIDE_WORDS: return '/guide'
    if c in BUCKET_WORDS: return 'view_buckets'
    if c in ADMIN_WORDS: return '/admin'
    if c in DIGEST_WORDS: return '/digest'
    return c

# ── State ─────────────────────────────────────────────────────
_us = {}
def _st(cid):
    if cid not in _us: _us[cid] = {'page':0,'sort':'3m','view':'today'}
    return _us[cid]

# ── Telegram API ──────────────────────────────────────────────
def send_message(chat_id, text, reply_markup=None):
    data = {'chat_id':str(chat_id),'text':text,'parse_mode':PARSE_MODE}
    if reply_markup: data['reply_markup'] = json.dumps(reply_markup)
    try:
        r = requests.post(f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage", data=data, timeout=10)
        if r.status_code != 200:
            print(f"[WARN] send {r.status_code}")
            try: print(f"[WARN] {r.json().get('description','')[:200]}")
            except: pass
            return False
        return True
    except Exception as e: print(f"[ERR] send: {e}"); return False

def answer_cb(cid, text=""):
    try: requests.post(f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/answerCallbackQuery",
                       data={'callback_query_id':cid,'text':text}, timeout=5)
    except: pass

def get_updates(offset=None):
    p = {'timeout':30,'allowed_updates':json.dumps(['message','callback_query'])}
    if offset: p['offset'] = offset
    try: return requests.get(f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/getUpdates",params=p,timeout=35).json()
    except Exception as e: print(f"[ERR] updates: {e}"); return None

# ── Keyboards ─────────────────────────────────────────────────
BUCKET_CB = {
    "bucket_rising": BUCKET_RISING if _BUCKET_OK else "rising",
    "bucket_uptrend": BUCKET_UPTREND if _BUCKET_OK else "uptrend",
    "bucket_peak": BUCKET_PEAK if _BUCKET_OK else "peak",
    "bucket_recovery": BUCKET_RECOVERY if _BUCKET_OK else "recovery",
    "bucket_safe": BUCKET_SAFE if _BUCKET_OK else "safe",
    "bucket_caution": BUCKET_CAUTION if _BUCKET_OK else "caution",
}

def kb_main(cp=0, tp=1, sort='3m', view='today'):
    def dot(v): return '\u25cf' if view == v else '\u25cb'
    def sdot(s): return '\u25cf' if sort == s else '\u25cb'
    kb = [
        [{"text":f"{dot('today')} Today","callback_data":"view_today"},
         {"text":f"{dot('new')} New","callback_data":"view_new"},
         {"text":f"{dot('exit')} Exit","callback_data":"view_exit"}],
        [{"text":f"{dot('caution')} Caution","callback_data":"view_caution"},
         {"text":f"{dot('strong')} Strong","callback_data":"view_strong"},
         {"text":f"{dot('buckets')} Buckets","callback_data":"view_buckets"}],
    ]
    if view == 'today':
        kb.append([{"text":f"{sdot('3m')} 3M","callback_data":"sort_3m"},
                    {"text":f"{sdot('score')} Score","callback_data":"sort_score"},
                    {"text":f"{sdot('top10')} Top10","callback_data":"sort_top10"}])
    if view == 'today' and tp > 1:
        nav = []
        if cp > 0: nav.append({"text":"\u25c0 Prev","callback_data":"prev"})
        nav.append({"text":f"{cp+1}/{tp}","callback_data":"noop"})
        if cp < tp-1: nav.append({"text":"Next \u25b6","callback_data":"next"})
        kb.append(nav)
        s = max(0, min(cp-2, tp-5)); e = min(tp, s+5)
        kb.append([{"text":f"\u25cf{p+1}" if p==cp else str(p+1),"callback_data":f"page_{p}"} for p in range(s,e)])
    kb.append([{"text":"News","callback_data":"news"},{"text":"Summary","callback_data":"summary"},
               {"text":"Digest","callback_data":"/digest"},{"text":"Guide","callback_data":"guide"},
               {"text":"Help","callback_data":"help"}])
    return {"inline_keyboard": kb}

def kb_bucket():
    return {"inline_keyboard":[
        [{"text":"\U0001F4C8 Rising","callback_data":"bucket_rising"},
         {"text":"\U0001F680 Uptrend","callback_data":"bucket_uptrend"},
         {"text":"\U0001F51D Peak","callback_data":"bucket_peak"}],
        [{"text":"\U0001F4C9 Recovery","callback_data":"bucket_recovery"},
         {"text":"\U0001F6E1 Safer","callback_data":"bucket_safe"},
         {"text":"\u26A0 Caution","callback_data":"bucket_caution"}],
        [{"text":"\u25c0\u25c0 Main","callback_data":"view_today"}]]}

def kb_bucket_detail():
    return {"inline_keyboard":[
        [{"text":"\U0001F4C8 Rising","callback_data":"bucket_rising"},
         {"text":"\U0001F680 Uptrend","callback_data":"bucket_uptrend"},
         {"text":"\U0001F51D Peak","callback_data":"bucket_peak"}],
        [{"text":"\U0001F4C9 Recovery","callback_data":"bucket_recovery"},
         {"text":"\U0001F6E1 Safer","callback_data":"bucket_safe"},
         {"text":"\u26A0 Caution","callback_data":"bucket_caution"}],
        [{"text":"\u25c0 Buckets","callback_data":"view_buckets"},
         {"text":"\u25c0\u25c0 Main","callback_data":"view_today"}]]}

def kb_back():
    return {"inline_keyboard":[[{"text":"\u25c0\u25c0 Main","callback_data":"view_today"}]]}

def kb_guide():
    return {"inline_keyboard":[
        [{"text":"\U0001F4D6 Open full guide","url":GUIDE_PDF_URL}],
        [{"text":"\u25c0\u25c0 Main","callback_data":"view_today"}]]}

def kb_admin():
    return {"inline_keyboard":[
        [{"text":"Health","callback_data":"admin_health"},{"text":"Users","callback_data":"admin_users"}],
        [{"text":"Activity","callback_data":"admin_stats"},{"text":"\u25c0\u25c0 Main","callback_data":"view_today"}]]}

def kb_card():
    return {"inline_keyboard":[[{"text":"\u25c0 Back","callback_data":"back_from_card"},
                                 {"text":"\u25c0\u25c0 Main","callback_data":"view_today"}]]}

# ── Handler ───────────────────────────────────────────────────
def handle_command(chat_id, text, is_cb=False, raw_user=None):
    cmd = (text or '').strip().lower()
    if '@' in cmd: cmd = cmd.split('@')[0]
    print(f"[CMD] {chat_id} {cmd!r} cb={is_cb}")

    if raw_user:
        track_user(FakeUser(raw_user))
        log_activity(raw_user.get("id", chat_id), "cb" if is_cb else "cmd", cmd)
    if raw_user and is_blocked(raw_user.get("id", 0)):
        return {"message":None,"keyboard":None} if is_cb else None

    res = load_scan_results()
    if not res:
        m = "No scan results found.\nPipeline runs at 6:00 AM IST daily."
        if is_cb: return {"message":m,"keyboard":None}
        send_message(chat_id, m); return None

    stocks = res['stocks']; ps = res['page_size']; sd = res['scan_date']
    hist = load_history()
    st = _st(chat_id)

    def reply(m, kb=None):
        if is_cb: return {"message":m,"keyboard":kb}
        send_message(chat_id, m, reply_markup=kb); return None

    def today_page(pg, srt):
        ss = sort_stocks(stocks, srt)
        tp = max(1,(len(ss)+ps-1)//ps); pg = max(0,min(pg,tp-1))
        st['page']=pg; st['sort']=srt; st['view']='today'
        return reply(format_stock_list(ss, pg*ps, ps, sd), kb_main(pg,tp,srt,'today'))

    def view(vn, m, kb=None):
        st['view'] = vn
        return reply(m, kb or kb_main(0,1,st['sort'],vn))

    # ── Routes ──
    if cmd == '/start':
        st['view']='today'; st['page']=0
        return reply(format_welcome(), kb_main(0,1,'3m','today'))

    elif cmd in ('/today','view_today'):
        return view('today', format_today_scan(stocks, sd))

    elif cmd in ('/next','next'):
        if st['view']!='today': return today_page(0, st['sort'])
        ss=sort_stocks(stocks,st['sort']); tp=max(1,(len(ss)+ps-1)//ps)
        if st['page']+1>=tp: return reply("Last page!")
        return today_page(st['page']+1, st['sort'])

    elif cmd in ('/prev','prev'):
        if st['view']!='today': return today_page(0, st['sort'])
        if st['page']==0: return reply("First page!")
        return today_page(st['page']-1, st['sort'])

    elif cmd.startswith('/page') or cmd.startswith('page_'):
        try:
            pn = int(cmd.split()[1])-1 if cmd.startswith('/page') else int(cmd.split('_')[1])
            return today_page(pn, st['sort'])
        except: return reply("Usage: /page N")

    elif cmd == 'sort_3m': return today_page(0,'3m')
    elif cmd == 'sort_score': return today_page(0,'score')
    elif cmd == 'sort_top10': return today_page(0,'top10')
    elif cmd == 'noop': return {"message":None,"keyboard":None} if is_cb else None

    elif cmd in ('/new','view_new'):
        if len(hist)<2:
            return view('new', f"{_b('History Building...')}\nNeed 2+ days. Have: {len(hist)} day(s)\nCheck back tomorrow after 6 AM scan.")
        return view('new', format_new_stocks(get_new_stocks(hist), sd))

    elif cmd in ('/exit','view_exit'):
        if len(hist)<2:
            return view('exit', f"{_b('History Building...')}\nNeed 2+ days. Have: {len(hist)} day(s)")
        return view('exit', format_exit_stocks(get_exit_stocks(hist), sd))

    elif cmd in ('/caution','view_caution'):
        return view('caution', format_caution_stocks(stocks, sd))

    elif cmd in ('/strong','view_strong'):
        if len(hist)<5:
            return view('strong', f"\U0001F525 {_b('Strong Signals')}\nNeeds 5 days. Have: {len(hist)}. Ready in: {5-len(hist)} more day(s)")
        return view('strong', format_strong_stocks(get_strong_stocks(hist), sd))

    elif cmd in ('/news','news'):
        ss=sort_stocks(stocks,st['sort']); tp=max(1,(len(ss)+ps-1)//ps)
        pg=max(0,min(st['page'],tp-1))
        return reply(format_stock_list(ss, pg*ps, ps, sd, include_news=True), kb_main(pg,tp,st['sort'],'today'))

    elif cmd in ('/list','list','summary'):
        return view('today', format_summary(stocks, sd, hist))

    elif cmd in ('/help','help'):
        return reply(format_help(), kb_main(st['page'],1,st['sort'],st['view']))

    # ── Guide ──
    elif cmd in ('/guide','guide'):
        m = format_guide_message() if _ADMIN_OK else (f"{_b('NSE Scanner Guide')}\nTap below for the full guide.")
        return reply(m, kb_guide())

    # ── Buckets ──
    elif cmd in ('/buckets','view_buckets'):
        if not _BUCKET_OK: return view('buckets', "Bucket view coming soon.")
        cl, s = classify_current_scan()
        if cl: return view('buckets', format_bucketed_message(cl, s), kb_bucket())
        return view('buckets', "No data for bucketed view.")

    elif cmd in BUCKET_CB and _BUCKET_OK:
        cl, s = classify_current_scan()
        if cl:
            m = format_bucket_detail(BUCKET_CB[cmd], cl, s)
            return reply(m, kb_bucket_detail())
        return reply("No data.")

    # ── Signal card ──
    elif cmd.startswith('stock_') and not cmd.startswith('stock_news_'):
        sym = cmd.replace('stock_','').upper()
        m = format_signal_card(sym) if _TRACKER_OK else f"Tracker not available for {_code(sym)}"
        return reply(m, kb_card())

    elif cmd == 'back_from_card':
        return handle_command(chat_id, f'view_{st["view"]}', is_cb=is_cb, raw_user=raw_user)

    # ── Digest (last completed week) ──
    elif cmd == '/digest':
        if not _DIGEST_OK:
            return reply("Weekly digest module not available.")
        try:
            today = date.today()
            # Find last Friday (end of last completed week)
            days_since_fri = (today.weekday() - 4) % 7
            if days_since_fri == 0 and today.weekday() != 4:
                days_since_fri = 7
            last_friday = today - timedelta(days=days_since_fri)
            last_monday = last_friday - timedelta(days=4)

            week_dates = get_week_dates(last_friday)
            week_hist = get_week_history(hist, week_dates)

            if not week_hist:
                return reply(f"\U0001F4C5 {_b('Weekly Digest')}\n\nNo scan history for last week yet.\nNeed at least 2 trading days of history.\nCurrently have: {len(hist)} day(s)")

            week_prices = {}
            try:
                conn = sqlite3.connect(getattr(config, 'DB_PATH', 'nse_scanner.db'))
                all_syms = set()
                for d in week_hist: all_syms.update(d.get('symbols', []))
                week_prices = get_week_prices(list(all_syms), week_dates, conn)
                conn.close()
            except Exception: pass

            analysis = analyze_week(week_hist, week_prices)
            m = format_weekly_digest(analysis, week_dates)
            return reply(m, kb_back())
        except Exception as e:
            log.error(f"Digest error: {e}")
            return reply(f"Digest error: {e}")

    # ── Admin ──
    elif cmd in ('/admin','admin_health'):
        if not _ADMIN_OK or not (raw_user and is_admin(raw_user.get("id",0))):
            return reply("Admin access only.")
        return reply(format_health_report(generate_health_report()), kb_admin())

    elif cmd in ('/users','admin_users'):
        if not _ADMIN_OK or not (raw_user and is_admin(raw_user.get("id",0))):
            return reply("Admin access only.")
        return reply(format_user_list(), kb_admin())

    elif cmd == '/health':
        if _ADMIN_OK and raw_user and is_admin(raw_user.get("id",0)):
            send_message(chat_id, format_health_report(generate_health_report()), reply_markup=kb_admin())
        else: send_message(chat_id, "Admin access only.")
        return None

    elif cmd == 'admin_stats':
        if _ADMIN_OK and raw_user and is_admin(raw_user.get("id",0)):
            from nse_bot_admin import get_activity_stats
            s = get_activity_stats(days=1)
            m = f"{_b('Activity Stats (Today)')}\n\nTotal actions: {s['total_actions']}\nUnique users: {s['unique_users']}\n"
            if s.get("top_actions"):
                m += f"\n{_b('Top Actions:')}\n"
                for a,c in s["top_actions"][:8]: m += f"  {_code(a)}: {c}\n"
            return reply(m, kb_admin())
        return reply("Admin access only.")

    # ── Unknown ──
    else:
        return reply(f"Didn't understand: {_code(cmd)}\n\nTry: {_b('today')}, {_b('new')}, {_b('exit')}, {_b('strong')}, {_b('caution')}, {_b('buckets')}, {_b('digest')}, {_b('guide')}, {_b('help')}",
                     kb_main(st['page'],1,st['sort'],st['view']))

# ── Process ───────────────────────────────────────────────────
def process_update(upd):
    try:
        if 'callback_query' in upd:
            cq = upd['callback_query']
            cid = str(cq['message']['chat']['id'])
            answer_cb(cq['id'])
            r = handle_command(cid, cq.get('data',''), is_cb=True, raw_user=cq.get('from',{}))
            if isinstance(r,dict) and r.get('message'):
                send_message(cid, r['message'], reply_markup=r.get('keyboard'))
        elif 'message' in upd:
            mo = upd['message']; cid = str(mo['chat']['id']); t = mo.get('text','').strip()
            if not t: return
            print(f"[MSG] {cid} {t!r}")
            rc = resolve_text_to_command(t)
            print(f"[RES] {rc!r}")
            handle_command(cid, rc, is_cb=False, raw_user=mo.get('from',{}))
    except Exception as e:
        import traceback; print(f"[ERR] {e}"); traceback.print_exc()

# ── Health scheduler ──────────────────────────────────────────
def health_scheduler():
    if not _ADMIN_OK: return
    log.info("[SCHED] Health check 11:30 PM daily")
    last = None
    while True:
        try:
            now = datetime.now()
            if now.hour==23 and 30<=now.minute<32 and last!=now.date():
                send_health_check(); last=now.date()
            time.sleep(60)
        except: time.sleep(60)

# ── Startup ───────────────────────────────────────────────────
def startup_checks():
    ok = True
    try:
        r = requests.get(f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/getMe",timeout=5).json()
        if r.get('ok'): print(f"[OK] Bot: @{r['result']['username']}")
        else: print(f"[FAIL] Token"); ok=False
    except: ok=False
    try:
        wh = requests.get(f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/getWebhookInfo",timeout=5).json().get('result',{}).get('url','')
        if wh: print(f"[WARN] Webhook active"); ok=False
        else: print("[OK] No webhook")
    except: pass
    r = load_scan_results()
    if r: print(f"[OK] {len(r['stocks'])} stocks (date: {r['scan_date']})")
    else: print("[FAIL] No scan data"); ok=False
    h = load_history(); print(f"[OK] History: {len(h)} day(s)")
    print(f"[OK] Admin: {_ADMIN_OK} | Buckets: {_BUCKET_OK} | Tracker: {_TRACKER_OK} | Digest: {_DIGEST_OK}")
    if _ADMIN_OK: print(f"[OK] Users: {get_user_count()}")
    if _TRACKER_OK:
        ts = get_tracker_summary()
        print(f"[OK] Signals: {ts.get('total_active',0)} active, {ts.get('total_exited',0)} exited")
    return ok

# ── Main ──────────────────────────────────────────────────────
def main():
    print("="*55)
    print("  NSE Scanner Bot — Phase 2.2")
    print("  Views: Today/New/Exit/Caution/Strong/Buckets/Digest/Guide")
    print("="*55+"\n")
    if not startup_checks(): print("[BOT] Fix issues then restart"); return
    threading.Thread(target=health_scheduler, daemon=True).start()
    if _ADMIN_OK: print("[BOT] Health scheduler running")
    print("\n[BOT] Ready! Listening...\n")
    offset = None
    while True:
        try:
            u = get_updates(offset)
            if u and u.get('ok') and u.get('result'):
                for upd in u['result']:
                    process_update(upd); offset = upd['update_id']+1
            time.sleep(1)
        except KeyboardInterrupt: print("\n[BOT] Stopped"); break
        except Exception as e: print(f"[ERR] {e}"); time.sleep(5)

if __name__ == "__main__": main()
