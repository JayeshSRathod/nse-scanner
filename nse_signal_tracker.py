"""
nse_signal_tracker.py — Frozen Entry + Probability + Lifecycle Engine
======================================================================
Tracks stock lifecycle from entry to exit with frozen prices,
live P/L, milestone flags, and probability estimates.

Data file: signal_tracker.json

Lifecycle states:
    ACTIVE      — stock is in top 25, healthy
    T1_HIT      — first target was reached
    WEAKENING   — score dropping, may exit soon
    EXITED      — left top 25, final P/L recorded

Probability model (signal-derived, not backtested):
    Base 40% + score bonus + streak bonus + category bonus

Usage:
    from nse_signal_tracker import (
        update_tracker, get_live_signals, get_exited_signals,
        calculate_probability, get_signal, format_signal_card
    )
"""

import os
import json
from datetime import date, datetime
from pathlib import Path

_HERE = Path(__file__).parent
TRACKER_FILE = _HERE / "signal_tracker.json"

STATE_ACTIVE    = "active"
STATE_T1_HIT    = "t1_hit"
STATE_T2_HIT    = "t2_hit"
STATE_WEAKENING = "weakening"
STATE_EXITED    = "exited"

PROB_BASE        = 40
PROB_SCORE_HIGH  = 20
PROB_SCORE_MED   = 10
PROB_STREAK_5    = 10
PROB_STREAK_10   = 15
PROB_CAT_UPTREND = 8
PROB_CAT_RISING  = 6
PROB_CAT_SAFE    = 4
PROB_T2_DISCOUNT = 16


def _load_tracker():
    if not TRACKER_FILE.exists():
        return {"signals": {}, "exited": [], "last_updated": ""}
    try:
        with open(TRACKER_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {"signals": {}, "exited": [], "last_updated": ""}


def _save_tracker(data):
    data["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(TRACKER_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)


def calculate_probability(score=0, streak=0, category="",
                          current_price=0, entry_price=0,
                          sl_price=0, t1_price=0):
    score = float(score or 0)
    t1 = PROB_BASE

    if score >= 8:
        t1 += PROB_SCORE_HIGH
    elif score >= 6:
        t1 += PROB_SCORE_MED

    if streak >= 10:
        t1 += PROB_STREAK_10
    elif streak >= 5:
        t1 += PROB_STREAK_5

    cat = category.lower() if category else ""
    if "uptrend" in cat:
        t1 += PROB_CAT_UPTREND
    elif "rising" in cat or "consistent" in cat:
        t1 += PROB_CAT_RISING
    elif "safer" in cat or "safe" in cat:
        t1 += PROB_CAT_SAFE

    if current_price > 0 and entry_price > 0 and t1_price > 0:
        distance_to_t1 = t1_price - current_price
        total_distance = t1_price - entry_price
        if total_distance > 0:
            progress = 1 - (distance_to_t1 / total_distance)
            if progress > 0.5:
                t1 += int(progress * 10)

    t1 = max(20, min(85, t1))
    t2 = max(15, t1 - PROB_T2_DISCOUNT)
    sl = max(10, min(50, 100 - t1))

    return {"t1_pct": t1, "t2_pct": t2, "sl_pct": sl}


def _determine_state(signal, current_stock=None):
    if current_stock is None:
        return STATE_EXITED

    score = float(current_stock.get("score", 0))
    t1    = float(signal.get("t1_price", 0))
    t2    = float(signal.get("t2_price", 0))
    high  = float(signal.get("highest_price", 0))

    if t2 > 0 and high >= t2:
        return STATE_T2_HIT
    if t1 > 0 and high >= t1:
        return STATE_T1_HIT
    if score <= 5:
        return STATE_WEAKENING

    prev_score = float(signal.get("prev_score", score))
    if prev_score > 0 and score < prev_score - 1.5:
        return STATE_WEAKENING

    return STATE_ACTIVE


def update_tracker(current_stocks, scan_date, history=None):
    tracker = _load_tracker()
    signals = tracker.get("signals", {})
    exited  = tracker.get("exited", [])

    current_symbols = {s["symbol"] for s in current_stocks}
    current_map     = {s["symbol"]: s for s in current_stocks}

    streaks = {}
    if history:
        for symbol in current_symbols:
            count = 0
            for day_entry in history:
                if symbol in day_entry.get("symbols", []):
                    count += 1
                else:
                    break
            streaks[symbol] = count

    new_count = 0
    updated_count = 0
    exited_count = 0

    for symbol, stock in current_map.items():
        close  = float(stock.get("close", 0))
        score  = float(stock.get("score", 0))
        sl     = float(stock.get("sl", round(close * 0.93, 2)))
        t1     = float(stock.get("target1", round(close + (close - sl), 2)))
        t2     = float(stock.get("target2", round(close + 2 * (close - sl), 2)))
        streak = streaks.get(symbol, 1)

        if symbol not in signals:
            signals[symbol] = {
                "symbol":        symbol,
                "entry_price":   close,
                "entry_date":    scan_date,
                "sl_price":      sl,
                "t1_price":      t1,
                "t2_price":      t2,
                "current_price": close,
                "highest_price": close,
                "lowest_price":  close,
                "entry_score":   score,
                "current_score": score,
                "prev_score":    score,
                "streak":        streak,
                "state":         STATE_ACTIVE,
                "milestones":    [
                    {"event": "entered", "date": scan_date, "price": close}
                ],
                "t1_hit_date":   None,
                "t2_hit_date":   None,
                "category":      "",
            }
            new_count += 1
        else:
            sig = signals[symbol]
            sig["prev_score"]    = sig.get("current_score", score)
            sig["current_price"] = close
            sig["current_score"] = score
            sig["streak"]        = streak

            if close > sig.get("highest_price", 0):
                sig["highest_price"] = close
            if close < sig.get("lowest_price", close):
                sig["lowest_price"] = close

            if (sig.get("t1_hit_date") is None and
                    sig["highest_price"] >= sig["t1_price"] > 0):
                sig["t1_hit_date"] = scan_date
                sig["milestones"].append(
                    {"event": "t1_hit", "date": scan_date,
                     "price": sig["highest_price"]})

            if (sig.get("t2_hit_date") is None and
                    sig["highest_price"] >= sig["t2_price"] > 0):
                sig["t2_hit_date"] = scan_date
                sig["milestones"].append(
                    {"event": "t2_hit", "date": scan_date,
                     "price": sig["highest_price"]})

            sig["state"] = _determine_state(sig, stock)
            updated_count += 1

    for symbol in list(signals.keys()):
        if symbol not in current_symbols:
            sig = signals[symbol]
            sig["state"]      = STATE_EXITED
            sig["exit_date"]  = scan_date
            sig["exit_price"] = sig["current_price"]

            entry = sig["entry_price"]
            exit_p = sig["current_price"]
            if entry > 0:
                sig["final_pl"]     = round(exit_p - entry, 2)
                sig["final_pl_pct"] = round((exit_p - entry) / entry * 100, 1)
            else:
                sig["final_pl"]     = 0
                sig["final_pl_pct"] = 0

            try:
                d1 = datetime.strptime(sig["entry_date"], "%Y-%m-%d")
                d2 = datetime.strptime(scan_date, "%Y-%m-%d")
                sig["days_in_list"] = (d2 - d1).days
            except Exception:
                sig["days_in_list"] = sig.get("streak", 0)

            sig["milestones"].append(
                {"event": "exited", "date": scan_date,
                 "price": sig["current_price"]})

            exited.append(sig)
            del signals[symbol]
            exited_count += 1

    exited = sorted(exited, key=lambda x: x.get("exit_date", ""), reverse=True)[:50]

    for symbol, sig in signals.items():
        prob = calculate_probability(
            score=sig["current_score"],
            streak=sig["streak"],
            category=sig.get("category", ""),
            current_price=sig["current_price"],
            entry_price=sig["entry_price"],
            sl_price=sig["sl_price"],
            t1_price=sig["t1_price"],
        )
        sig["t1_prob"] = prob["t1_pct"]
        sig["t2_prob"] = prob["t2_pct"]
        sig["sl_prob"] = prob["sl_pct"]

    tracker["signals"] = signals
    tracker["exited"]  = exited
    _save_tracker(tracker)

    return {
        "new": new_count, "updated": updated_count,
        "exited": exited_count, "active": len(signals),
        "total_exited": len(exited),
    }


def set_category(symbol, category):
    tracker = _load_tracker()
    if symbol in tracker.get("signals", {}):
        tracker["signals"][symbol]["category"] = category
        sig = tracker["signals"][symbol]
        prob = calculate_probability(
            score=sig["current_score"], streak=sig["streak"],
            category=category, current_price=sig["current_price"],
            entry_price=sig["entry_price"], sl_price=sig["sl_price"],
            t1_price=sig["t1_price"],
        )
        sig["t1_prob"] = prob["t1_pct"]
        sig["t2_prob"] = prob["t2_pct"]
        sig["sl_prob"] = prob["sl_pct"]
        _save_tracker(tracker)


def get_live_signals():
    tracker = _load_tracker()
    signals = list(tracker.get("signals", {}).values())
    signals.sort(key=lambda x: x.get("streak", 0), reverse=True)
    return signals


def get_exited_signals(limit=20):
    tracker = _load_tracker()
    return tracker.get("exited", [])[:limit]


def get_signal(symbol):
    tracker = _load_tracker()
    if symbol in tracker.get("signals", {}):
        return tracker["signals"][symbol]
    for sig in tracker.get("exited", []):
        if sig["symbol"] == symbol:
            return sig
    return None


def get_tracker_summary():
    tracker = _load_tracker()
    signals = tracker.get("signals", {})
    all_sigs = list(signals.values())

    active    = [s for s in all_sigs if s["state"] == STATE_ACTIVE]
    t1_hit    = [s for s in all_sigs if s["state"] == STATE_T1_HIT]
    t2_hit    = [s for s in all_sigs if s["state"] == STATE_T2_HIT]
    weakening = [s for s in all_sigs if s["state"] == STATE_WEAKENING]

    avg_t1 = round(sum(s.get("t1_prob", 0) for s in all_sigs) / len(all_sigs)) if all_sigs else 0
    avg_t2 = round(sum(s.get("t2_prob", 0) for s in all_sigs) / len(all_sigs)) if all_sigs else 0
    high_prob = [s for s in all_sigs if s.get("t1_prob", 0) >= 70]

    return {
        "total_active": len(signals), "active": len(active),
        "t1_hit": len(t1_hit), "t2_hit": len(t2_hit),
        "weakening": len(weakening),
        "total_exited": len(tracker.get("exited", [])),
        "avg_t1_prob": avg_t1, "avg_t2_prob": avg_t2,
        "high_prob_count": len(high_prob),
        "last_updated": tracker.get("last_updated", ""),
    }


def _h(v):
    return str(v).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

def _b(v):    return f"<b>{_h(v)}</b>"
def _code(v): return f"<code>{_h(v)}</code>"

def _fmt_price(p):
    return f"{int(round(float(p))):,}"

def _fmt_pl(entry, current):
    entry   = float(entry)
    current = float(current)
    if entry <= 0:
        return "N/A"
    diff = current - entry
    pct  = diff / entry * 100
    sign = "+" if diff >= 0 else ""
    return f"{sign}{int(round(diff)):,} ({sign}{pct:.1f}%)"


def format_stock_with_prob(stock, signal=None, rank=0, show_frozen=False):
    sym   = stock.get("symbol", "?")
    score = int(round(float(stock.get("score", 0))))
    close = float(stock.get("close", 0))
    r3m   = float(stock.get("return_3m_pct", 0))
    sl    = float(stock.get("sl", round(close * 0.93, 2)))
    t1    = float(stock.get("target1", round(close + (close - sl), 2)))
    t2    = float(stock.get("target2", round(close + 2*(close - sl), 2)))

    if signal:
        t1_prob = signal.get("t1_prob", 0)
        t2_prob = signal.get("t2_prob", 0)
        streak  = signal.get("streak", 0)
        entry   = signal.get("entry_price", close)
    else:
        prob = calculate_probability(score=score)
        t1_prob = prob["t1_pct"]
        t2_prob = prob["t2_pct"]
        streak = 0
        entry  = close

    r3m_sign = "+" if r3m >= 0 else ""
    rank_str = f"{_b(str(rank) + '.')} " if rank > 0 else ""
    streak_str = f" | {streak}d" if streak >= 3 else ""

    msg = f"{rank_str}{_code(sym)}  {score}/10{streak_str}\n"
    if show_frozen and signal and signal.get("entry_price"):
        pl_str = _fmt_pl(entry, close)
        msg += f"   Entry(frozen) {_fmt_price(entry)} | Now {_fmt_price(close)} | P/L {pl_str}\n"
    msg += f"   Entry {_fmt_price(close)} | SL {_fmt_price(sl)} | T1 {_fmt_price(t1)} | T2 {_fmt_price(t2)}\n"
    msg += f"   3M {r3m_sign}{r3m:.1f}% | T1 {t1_prob}% | T2 {t2_prob}%\n"
    return msg


def format_signal_card(symbol):
    sig = get_signal(symbol)
    if not sig:
        return f"No signal data found for {_code(symbol)}"

    state = sig.get("state", STATE_ACTIVE)
    state_badges = {
        STATE_ACTIVE: "Active", STATE_T1_HIT: "T1 Hit",
        STATE_T2_HIT: "T2 Hit", STATE_WEAKENING: "Weakening",
        STATE_EXITED: "Exited",
    }
    badge = state_badges.get(state, "Unknown")

    entry   = float(sig.get("entry_price", 0))
    current = float(sig.get("current_price", 0))
    sl      = float(sig.get("sl_price", 0))
    t1      = float(sig.get("t1_price", 0))
    t2      = float(sig.get("t2_price", 0))
    score   = int(round(float(sig.get("current_score", 0))))
    streak  = sig.get("streak", 0)

    msg  = f"{_code(symbol)}  {score}/10  [{badge}]\n"
    msg += "\u2501" * 28 + "\n"
    msg += f"Entry (frozen): \u20b9{_fmt_price(entry)}\n"
    msg += f"Current price:  \u20b9{_fmt_price(current)}\n"
    msg += f"Live P/L:       {_fmt_pl(entry, current)}\n"
    msg += f"Stop-loss:      \u20b9{_fmt_price(sl)}\n"
    msg += f"Target 1:       \u20b9{_fmt_price(t1)}\n"
    msg += f"Target 2:       \u20b9{_fmt_price(t2)}\n"

    t1_prob = sig.get("t1_prob", 0)
    t2_prob = sig.get("t2_prob", 0)
    sl_prob = sig.get("sl_prob", 0)
    msg += f"\nT1 prob: {t1_prob}% | T2 prob: {t2_prob}%"
    if state == STATE_WEAKENING:
        msg += f" | SL risk: {sl_prob}%"
    msg += "\n"

    if streak > 0:
        msg += f"In list: {streak} consecutive days\n"

    milestones = sig.get("milestones", [])
    if milestones:
        msg += f"\n{_b('Milestones')}\n"
        event_labels = {
            "entered": "Entered top 25", "t1_hit": "T1 target hit",
            "t2_hit": "T2 target hit", "exited": "Left top 25",
        }
        for m in milestones:
            label = event_labels.get(m["event"], m["event"])
            price = _fmt_price(m.get("price", 0))
            msg += f"  {m['date'][:10]}  {label}  \u20b9{price}\n"

    if state == STATE_WEAKENING:
        msg += (
            f"\n{_b('Warning')}: Momentum weakening. "
            f"Score dropped. Consider tightening SL or booking profits."
        )

    if state == STATE_EXITED:
        days = sig.get("days_in_list", 0)
        final_pl = sig.get("final_pl_pct", 0)
        sign = "+" if final_pl >= 0 else ""
        msg += f"\nFinal return: {sign}{final_pl}% in {days} days"

    return msg


def format_exit_card(sig):
    symbol   = sig.get("symbol", "?")
    entry    = float(sig.get("entry_price", 0))
    exit_p   = float(sig.get("exit_price", sig.get("current_price", 0)))
    days     = sig.get("days_in_list", 0)
    score    = int(round(float(sig.get("entry_score", 0))))
    final_pl = sig.get("final_pl_pct", 0)
    t1_hit   = sig.get("t1_hit_date") is not None
    pl_sign  = "+" if final_pl >= 0 else ""

    msg  = f"{_code(symbol)}  was {score}/10  [Exited]\n"
    msg += f"   Was in list {days} days\n"
    msg += f"   Entry \u20b9{_fmt_price(entry)} \u2192 Exit \u20b9{_fmt_price(exit_p)}\n"
    msg += f"   Final P/L: {pl_sign}{final_pl}%"
    if t1_hit:
        msg += " | T1 was hit"
    msg += "\n"
    return msg


def format_caution_card(stock, signal=None):
    sym   = stock.get("symbol", "?")
    score = int(round(float(stock.get("score", 0))))
    close = float(stock.get("close", 0))
    r3m   = float(stock.get("return_3m_pct", 0))

    if signal:
        t1_prob = signal.get("t1_prob", 0)
        sl_prob = signal.get("sl_prob", 0)
        state   = signal.get("state", STATE_ACTIVE)
    else:
        prob    = calculate_probability(score=score)
        t1_prob = prob["t1_pct"]
        sl_prob = prob["sl_pct"]
        state   = STATE_WEAKENING if score <= 5 else STATE_ACTIVE

    badge = "Weakening" if state == STATE_WEAKENING else "Risk"
    r3m_sign = "+" if r3m >= 0 else ""

    msg  = f"{_code(sym)}  {score}/10  [{badge}]\n"
    msg += f"   Entry \u20b9{_fmt_price(close)} | 3M {r3m_sign}{r3m:.1f}%\n"
    msg += f"   T1 prob: {t1_prob}% | SL risk: {sl_prob}%\n"

    if r3m > 40:
        msg += f"   Overextended after {r3m:.0f}% run. High correction risk.\n"
    elif score <= 5:
        msg += f"   Score dropping. May exit top 25 soon.\n"
    return msg


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Signal Tracker")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--stock", type=str, help="Show signal card for SYMBOL")
    args = parser.parse_args()

    if args.status:
        s = get_tracker_summary()
        print(f"Active: {s['total_active']} | Exited: {s['total_exited']}")
        print(f"Avg T1 prob: {s['avg_t1_prob']}% | Avg T2 prob: {s['avg_t2_prob']}%")
    elif args.stock:
        import re
        print(re.sub(r'<[^>]+>', '', format_signal_card(args.stock.upper())))
    else:
        parser.print_help()
