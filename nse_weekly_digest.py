"""
nse_weekly_digest.py — Weekly Performance Digest
==================================================
Always shows LAST COMPLETED week (Mon-Fri).
Called via /digest command or manually.
"""

import os, sys, json, sqlite3, logging, requests
from datetime import date, datetime, timedelta
from pathlib import Path

try: import config
except ImportError: print("ERROR: config.py"); sys.exit(1)

try:
    from nse_telegram_handler import (
        load_history, HISTORY_FILE,
        _b, _i, _h, _code, _fmt_price, _fmt_return,
    )
except ImportError:
    def _h(v): return str(v).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')
    def _b(v): return f"<b>{_h(v)}</b>"
    def _i(v): return f"<i>{_h(v)}</i>"
    def _code(v): return f"<code>{_h(v)}</code>"
    def _fmt_price(p): return f"\u20b9{int(round(float(p))):,}"
    def _fmt_return(pct):
        sign = '+' if float(pct) >= 0 else ''
        return f"{sign}{float(pct):.1f}%"
    def load_history(): return []

os.makedirs(getattr(config,'LOG_DIR','logs'), exist_ok=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(os.path.join(getattr(config,'LOG_DIR','logs'),"weekly_digest.log"),encoding="utf-8"),
              logging.StreamHandler()])
log = logging.getLogger(__name__)

SEP_BOLD = "\u2501" * 17
SEP_THIN = "\u2500" * 18

def _fmt_pl(entry, current):
    entry=float(entry); current=float(current)
    if entry<=0: return "N/A"
    d=current-entry; p=d/entry*100; s="+" if d>=0 else ""
    return f"{s}{p:.1f}%"


def get_week_dates(week_ending=None):
    if week_ending is None:
        week_ending = date.today()
    d = week_ending
    while d.weekday() >= 5: d -= timedelta(days=1)
    friday = d
    monday = friday - timedelta(days=friday.weekday())
    dates = []
    cur = monday
    while cur <= friday:
        if cur.weekday() < 5: dates.append(cur)
        cur += timedelta(days=1)
    return dates


def get_week_history(history, week_dates):
    ws = {str(d) for d in week_dates}
    wh = [h for h in history if h['date'] in ws]
    wh.sort(key=lambda x: x['date'], reverse=True)
    return wh


def get_week_prices(symbols, week_dates, conn):
    if not week_dates: return {}
    sd = min(week_dates); ed = max(week_dates)
    results = {}
    for sym in symbols:
        rows = conn.execute(
            "SELECT date,open,high,low,close FROM daily_prices WHERE symbol=? AND date>=? AND date<=? ORDER BY date",
            [sym, sd.isoformat(), ed.isoformat()]).fetchall()
        if not rows: continue
        mc=float(rows[0][4]); fc=float(rows[-1][4])
        wh=max(float(r[2]) for r in rows); wl=min(float(r[3]) for r in rows)
        wr = (fc-mc)/mc*100 if mc>0 else 0
        results[sym] = {'monday_close':mc,'friday_close':fc,'week_high':wh,
                         'week_low':wl,'week_return_pct':round(wr,1)}
    return results


def analyze_week(week_history, week_prices):
    if not week_history:
        return {"empty": True, "reason": "No scan history for this week"}

    mon = week_history[-1]; fri = week_history[0]
    mon_stocks = {s['symbol']:s for s in mon.get('stocks',[])}
    fri_stocks = {s['symbol']:s for s in fri.get('stocks',[])}
    mon_syms = set(mon_stocks.keys()); fri_syms = set(fri_stocks.keys())

    performers = []; sl_hits = []; t1_hits = []; t2_hits = []

    for sym, sd in mon_stocks.items():
        if sym not in week_prices: continue
        wp = week_prices[sym]
        entry=float(sd.get('close',0)); sl=float(sd.get('sl',entry*0.93))
        t1=float(sd.get('target1',entry+(entry-sl))); t2=float(sd.get('target2',entry+2*(entry-sl)))

        performers.append({'symbol':sym,'entry':entry,'friday_close':wp['friday_close'],
            'week_return_pct':wp['week_return_pct'],'week_high':wp['week_high'],
            'week_low':wp['week_low'],'sl':sl,'target1':t1,'target2':t2,
            'score':float(sd.get('score',0))})

        if wp['week_low'] <= sl:
            sl_hits.append({'symbol':sym,'sl':sl,'week_low':wp['week_low'],'entry':entry})
        if wp['week_high'] >= t1:
            t1_hits.append({'symbol':sym,'target1':t1,'week_high':wp['week_high'],'entry':entry})
        if wp['week_high'] >= t2:
            t2_hits.append({'symbol':sym,'target2':t2,'week_high':wp['week_high'],'entry':entry})

    performers.sort(key=lambda x: x['week_return_pct'], reverse=True)
    total = len(performers)
    winners = sum(1 for p in performers if p['week_return_pct']>0)
    losers = sum(1 for p in performers if p['week_return_pct']<0)
    flat = total - winners - losers
    hit_rate = round(winners/total*100,1) if total else 0
    avg_w = round(sum(p['week_return_pct'] for p in performers if p['week_return_pct']>0)/max(winners,1),1)
    avg_l = round(sum(p['week_return_pct'] for p in performers if p['week_return_pct']<0)/max(losers,1),1)

    consistency = []
    all_syms = set()
    for d in week_history: all_syms.update(d.get('symbols',[]))
    dc = len(week_history)
    for sym in all_syms:
        din = sum(1 for d in week_history if sym in d.get('symbols',[]))
        if din == dc and dc >= 3:
            sd = fri_stocks.get(sym, mon_stocks.get(sym, {}))
            wp = week_prices.get(sym, {})
            consistency.append({'symbol':sym,'days':din,'week_return_pct':wp.get('week_return_pct',0),
                                'score':float(sd.get('score',0))})
    consistency.sort(key=lambda x: x['week_return_pct'], reverse=True)

    return {
        "empty":False,"trading_days":dc,"total_tracked":total,
        "top_performers":performers[:5],"worst_performers":[p for p in performers[-3:] if p['week_return_pct']<0],
        "hit_rate":hit_rate,"winners":winners,"losers":losers,"flat":flat,
        "avg_winner":avg_w,"avg_loser":avg_l,
        "sl_hits":sl_hits,"t1_hits":t1_hits,"t2_hits":t2_hits,
        "consistency":consistency,
        "new_this_week":list(fri_syms-mon_syms),
        "exited_this_week":list(mon_syms-fri_syms),
        "stayed":len(mon_syms&fri_syms),
        "churn_pct":round(len(fri_syms-mon_syms)/max(len(mon_syms),1)*100,1),
    }


def format_weekly_digest(analysis, week_dates):
    if analysis.get("empty"):
        return (f"\U0001F4C5 {_b('Weekly Digest')}\n\n"
                f"{_i(analysis.get('reason','No data'))}\n\n"
                "History builds automatically \u2014 check back next Saturday.")

    ss = min(week_dates).strftime('%d-%b'); es = max(week_dates).strftime('%d-%b-%Y')

    msg  = f"\U0001F4C5 {_b('Weekly digest ' + chr(8212) + ' ' + ss + ' to ' + es)}\n"
    msg += f"{_i('How did last week' + chr(39) + 's picks perform?')}\n"
    msg += SEP_BOLD + "\n\n"

    # Scorecard
    a = analysis
    msg += f"\U0001F3AF {_b('Scorecard')}\n"
    msg += f"Tracked: {a['total_tracked']} stocks \u00b7 Trading days: {a['trading_days']}\n"
    msg += f"\u2705 Winners: {a['winners']} ({_fmt_return(a['avg_winner'])} avg)\n"
    msg += f"\u274C Losers: {a['losers']} ({_fmt_return(a['avg_loser'])} avg)\n"
    msg += f"Hit rate: {_b(str(a['hit_rate']) + '%')}\n"
    msg += SEP_THIN + "\n\n"

    # Top performers
    top = a.get('top_performers', [])
    if top:
        msg += f"\U0001F3C6 {_b('Top performers')}\n"
        for p in top:
            msg += f"\U0001F7E2 {_code(p['symbol'])} {_fmt_price(p['entry'])} \u2192 {_fmt_price(p['friday_close'])} ({_fmt_return(p['week_return_pct'])})\n"
        msg += SEP_THIN + "\n\n"

    # Worst
    worst = a.get('worst_performers', [])
    if worst:
        msg += f"\U0001F4C9 {_b('Underperformers')}\n"
        for p in worst:
            msg += f"\U0001F534 {_code(p['symbol'])} {_fmt_price(p['entry'])} \u2192 {_fmt_price(p['friday_close'])} ({_fmt_return(p['week_return_pct'])})\n"
        msg += SEP_THIN + "\n\n"

    # Target hits
    t1h = a.get('t1_hits',[]); t2h = a.get('t2_hits',[])
    if t1h or t2h:
        msg += f"\U0001F3AF {_b('Target hits')}\n"
        t2s = {t['symbol'] for t in t2h}
        for t in t2h:
            msg += f"\U0001F3AF\U0001F3AF {_code(t['symbol'])} hit T2 {_fmt_price(t['target2'])} (high: {_fmt_price(t['week_high'])})\n"
        for t in t1h:
            if t['symbol'] not in t2s:
                msg += f"\U0001F3AF {_code(t['symbol'])} hit T1 {_fmt_price(t['target1'])} (high: {_fmt_price(t['week_high'])})\n"
        msg += SEP_THIN + "\n\n"

    # SL hits
    slh = a.get('sl_hits',[])
    if slh:
        msg += f"\U0001F6D1 {_b('SL breached')}\n"
        for s in slh:
            msg += f"\u26A0\ufe0f {_code(s['symbol'])} SL {_fmt_price(s['sl'])} hit (low: {_fmt_price(s['week_low'])})\n"
        msg += SEP_THIN + "\n\n"

    # Champions
    champs = a.get('consistency',[])
    if champs:
        msg += f"\U0001F525 {_b('All week champions')}\n"
        for c in champs[:7]:
            e = "\U0001F7E2" if c['week_return_pct']>0 else "\U0001F534"
            msg += f"{e} {_code(c['symbol'])} {c['days']}/{a['trading_days']} \u00b7 {c['score']:.0f}/10 \u00b7 Week: {_fmt_return(c['week_return_pct'])}\n"
        msg += SEP_THIN + "\n\n"

    # Churn
    msg += f"\U0001F504 {_b('List churn')}\n"
    msg += f"Stayed all week: {a['stayed']}\n"
    msg += f"New entries: {len(a['new_this_week'])}\n"
    msg += f"Exited: {len(a['exited_this_week'])}\n"
    msg += f"Churn rate: {a['churn_pct']}%\n"
    if a['new_this_week']:
        msg += f"\n\U0001F195 New: {', '.join(a['new_this_week'][:8])}\n"
    if a['exited_this_week']:
        msg += f"\U0001F44B Exited: {', '.join(a['exited_this_week'][:8])}\n"

    msg += "\n" + SEP_THIN + "\n"
    msg += f"{_i('Next digest: Next Saturday')}"
    return msg


def generate_weekly_digest(week_ending=None, dry_run=False):
    if week_ending is None:
        today = date.today()
        days_since = (today.weekday()-4)%7
        if days_since==0 and today.weekday()!=4: days_since=7
        week_ending = today - timedelta(days=days_since)

    week_dates = get_week_dates(week_ending)
    if not week_dates: return False

    history = load_history()
    week_hist = get_week_history(history, week_dates)
    if not week_hist: print("No history for this week"); return False

    all_syms = set()
    for d in week_hist: all_syms.update(d.get('symbols',[]))

    week_prices = {}
    try:
        conn = sqlite3.connect(getattr(config,'DB_PATH','nse_scanner.db'))
        week_prices = get_week_prices(list(all_syms), week_dates, conn)
        conn.close()
    except Exception as e: log.warning(f"DB: {e}")

    analysis = analyze_week(week_hist, week_prices)
    message = format_weekly_digest(analysis, week_dates)

    if dry_run:
        import re; print(re.sub(r'<[^>]+>','',message))
    else:
        token = getattr(config,'TELEGRAM_TOKEN','')
        cid = getattr(config,'TELEGRAM_CHATID','')
        if token and cid:
            try:
                r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                    data={'chat_id':cid,'text':message,'parse_mode':'HTML'}, timeout=10)
                return r.status_code == 200
            except: pass
    return True


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--week-ending", type=str)
    a = p.parse_args()
    we = None
    if a.week_ending:
        for f in ["%d-%m-%Y","%Y-%m-%d"]:
            try: we=datetime.strptime(a.week_ending,f).date(); break
            except: pass
    generate_weekly_digest(week_ending=we, dry_run=a.dry_run)
