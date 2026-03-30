"""
nse_bot_admin.py — Admin Health Check + User Tracking
=======================================================
Tracks all bot users, logs their activity, and sends a
daily health check report to admin at 11:30 PM IST.

Features:
    1. User Registry   — tracks every user who interacts with bot
    2. Activity Log     — logs every command/button press per user
    3. Health Check     — daily 11:30 PM report to admin
    4. Admin Commands   — /admin, /users, /health (admin only)

Files:
    bot_users.json      — persistent user registry
    bot_activity.log    — rolling activity log (last 30 days)

Usage:
    # Import in nse_telegram_polling.py:
    from nse_bot_admin import (
        track_user, log_activity, is_admin,
        format_health_report, format_user_list,
        get_user_stats, send_health_check
    )

    # Track user on every interaction:
    track_user(update.effective_user)
    log_activity(user_id, "command", "/start")

    # Health check (called by scheduler at 11:30 PM):
    send_health_check()
"""

import os
import sys
import json
import sqlite3
import logging
import requests
from datetime import date, datetime, timedelta
from pathlib import Path
from collections import Counter

try:
    import config
except ImportError:
    print("ERROR: config.py not found")
    sys.exit(1)

# ── File paths ────────────────────────────────────────────────
_HERE         = Path(__file__).parent
USERS_FILE    = _HERE / "bot_users.json"
ACTIVITY_FILE = _HERE / "logs" / "bot_activity.log"
GUIDE_URL     = None  # Set after deploying the PDF

# ── Admin config ──────────────────────────────────────────────
# Your Telegram chat ID — only this user gets admin commands
ADMIN_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

# ── Logging ───────────────────────────────────────────────────
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[
        logging.FileHandler("logs/bot_admin.log", encoding="utf-8"),
        logging.StreamHandler(),
    ]
)
log = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════
# 1. USER REGISTRY
# ══════════════════════════════════════════════════════════════

def _load_users() -> dict:
    """Load user registry from JSON file."""
    if not USERS_FILE.exists():
        return {}
    try:
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _save_users(users: dict):
    """Save user registry to JSON file."""
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(users, f, indent=2, ensure_ascii=False, default=str)


def track_user(tg_user) -> dict:
    """
    Track a Telegram user. Call on every interaction.
    
    Args:
        tg_user: telegram.User object from update.effective_user
    
    Returns:
        User record dict
    """
    if tg_user is None:
        return {}
    
    user_id  = str(tg_user.id)
    users    = _load_users()
    now      = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    today    = date.today().isoformat()
    
    if user_id in users:
        # Update existing user
        users[user_id]["last_seen"]    = now
        users[user_id]["total_visits"] = users[user_id].get("total_visits", 0) + 1
        users[user_id]["username"]     = tg_user.username or users[user_id].get("username", "")
        users[user_id]["full_name"]    = (
            f"{tg_user.first_name or ''} {tg_user.last_name or ''}".strip()
            or users[user_id].get("full_name", "Unknown")
        )
        
        # Track daily visits
        daily = users[user_id].get("daily_visits", {})
        daily[today] = daily.get(today, 0) + 1
        # Keep only last 30 days
        cutoff = (date.today() - timedelta(days=30)).isoformat()
        daily  = {k: v for k, v in daily.items() if k >= cutoff}
        users[user_id]["daily_visits"] = daily
        
    else:
        # New user
        users[user_id] = {
            "user_id":      user_id,
            "username":     tg_user.username or "",
            "full_name":    f"{tg_user.first_name or ''} {tg_user.last_name or ''}".strip() or "Unknown",
            "first_seen":   now,
            "last_seen":    now,
            "total_visits": 1,
            "daily_visits": {today: 1},
            "is_blocked":   False,
        }
        log.info(f"[NEW USER] {users[user_id]['full_name']} (@{tg_user.username}) id={user_id}")
    
    _save_users(users)
    return users[user_id]


def get_all_users() -> dict:
    """Get all registered users."""
    return _load_users()


def get_user_count() -> int:
    """Get total number of users."""
    return len(_load_users())


def is_admin(user_id) -> bool:
    """Check if a user is the admin."""
    return str(user_id) == str(ADMIN_CHAT_ID)


def block_user(user_id: str) -> bool:
    """Block a user from using the bot."""
    users = _load_users()
    if user_id in users:
        users[user_id]["is_blocked"] = True
        _save_users(users)
        return True
    return False


def unblock_user(user_id: str) -> bool:
    """Unblock a user."""
    users = _load_users()
    if user_id in users:
        users[user_id]["is_blocked"] = False
        _save_users(users)
        return True
    return False


def is_blocked(user_id) -> bool:
    """Check if a user is blocked."""
    users = _load_users()
    user  = users.get(str(user_id), {})
    return user.get("is_blocked", False)


# ══════════════════════════════════════════════════════════════
# 2. ACTIVITY LOGGING
# ══════════════════════════════════════════════════════════════

def log_activity(user_id, action_type: str, action_detail: str):
    """
    Log a user activity.
    
    Args:
        user_id       : Telegram user ID
        action_type   : "command", "button", "callback", "message"
        action_detail : what they did, e.g. "/start", "next_page", "sort_3m"
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Get username from registry
    users    = _load_users()
    user     = users.get(str(user_id), {})
    username = user.get("username", "") or user.get("full_name", str(user_id))
    
    entry = f"[{now}] user={user_id} @{username} type={action_type} action={action_detail}\n"
    
    os.makedirs("logs", exist_ok=True)
    with open(ACTIVITY_FILE, "a", encoding="utf-8") as f:
        f.write(entry)


def get_today_activity() -> list:
    """Get all activity entries for today."""
    if not ACTIVITY_FILE.exists():
        return []
    
    today_str = date.today().strftime("%Y-%m-%d")
    entries   = []
    
    try:
        with open(ACTIVITY_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                if today_str in line:
                    entries.append(line.strip())
    except Exception:
        pass
    
    return entries


def get_activity_stats(days: int = 1) -> dict:
    """
    Get activity statistics for the last N days.
    
    Returns:
        {
            "total_actions": int,
            "unique_users": int,
            "top_actions": [(action, count), ...],
            "top_users": [(user_id, count), ...],
            "hourly": {hour: count, ...},
        }
    """
    if not ACTIVITY_FILE.exists():
        return {"total_actions": 0, "unique_users": 0}
    
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    
    users_seen = Counter()
    actions    = Counter()
    hourly     = Counter()
    total      = 0
    
    try:
        with open(ACTIVITY_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                # Parse: [2026-03-31 14:30:00] user=123 @name type=command action=/start
                if not line.startswith("["):
                    continue
                
                try:
                    ts_str = line[1:20]
                    if ts_str[:10] < cutoff:
                        continue
                    
                    total += 1
                    
                    # Extract user
                    if "user=" in line:
                        uid = line.split("user=")[1].split(" ")[0]
                        users_seen[uid] += 1
                    
                    # Extract action
                    if "action=" in line:
                        action = line.split("action=")[1].strip()
                        actions[action] += 1
                    
                    # Hour
                    hour = ts_str[11:13]
                    hourly[hour] += 1
                    
                except Exception:
                    continue
    except Exception:
        pass
    
    return {
        "total_actions": total,
        "unique_users":  len(users_seen),
        "top_actions":   actions.most_common(10),
        "top_users":     users_seen.most_common(10),
        "hourly":        dict(sorted(hourly.items())),
    }


def cleanup_old_activity(keep_days: int = 30):
    """Remove activity log entries older than keep_days."""
    if not ACTIVITY_FILE.exists():
        return
    
    cutoff = (datetime.now() - timedelta(days=keep_days)).strftime("%Y-%m-%d")
    
    kept = []
    try:
        with open(ACTIVITY_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith("[") and line[1:11] >= cutoff:
                    kept.append(line)
                elif not line.startswith("["):
                    kept.append(line)
        
        with open(ACTIVITY_FILE, 'w', encoding='utf-8') as f:
            f.writelines(kept)
    except Exception as e:
        log.warning(f"Activity cleanup failed: {e}")


# ══════════════════════════════════════════════════════════════
# 3. HEALTH CHECK REPORT
# ══════════════════════════════════════════════════════════════

def _check_scan_freshness() -> dict:
    """Check if today's scan data is fresh."""
    results_file = _HERE / "telegram_last_scan.json"
    
    if not results_file.exists():
        return {"ok": False, "detail": "telegram_last_scan.json missing"}
    
    try:
        with open(results_file, 'r') as f:
            data = json.load(f)
        
        scan_date = data.get("scan_date", "")
        stocks    = data.get("total_stocks", 0)
        
        try:
            sd = datetime.strptime(scan_date, "%Y-%m-%d").date()
            age = (date.today() - sd).days
        except Exception:
            age = 99
        
        return {
            "ok":       age <= 3,
            "date":     scan_date,
            "stocks":   stocks,
            "age_days": age,
            "detail":   f"{stocks} stocks, {age}d old" if age <= 3 
                       else f"STALE — {age} days old",
        }
    except Exception as e:
        return {"ok": False, "detail": f"JSON read error: {e}"}


def _check_database() -> dict:
    """Check SQLite database health."""
    db_path = _HERE / getattr(config, "DB_PATH", "nse_scanner.db")
    
    if not db_path.exists():
        return {"ok": False, "detail": "Database not found"}
    
    try:
        conn   = sqlite3.connect(str(db_path))
        row    = conn.execute(
            "SELECT COUNT(*), MAX(date) FROM daily_prices"
        ).fetchone()
        conn.close()
        
        total_rows = row[0]
        latest     = row[1] or "none"
        size_mb    = db_path.stat().st_size / 1_048_576
        
        return {
            "ok":     total_rows > 0,
            "rows":   total_rows,
            "latest": latest,
            "size_mb": round(size_mb, 1),
            "detail": f"{total_rows:,} rows, latest={latest}, {size_mb:.1f}MB",
        }
    except Exception as e:
        return {"ok": False, "detail": f"DB error: {e}"}


def _check_history() -> dict:
    """Check scan history file."""
    hist_file = _HERE / "scan_history.json"
    
    if not hist_file.exists():
        return {"ok": False, "detail": "scan_history.json missing"}
    
    try:
        with open(hist_file, 'r') as f:
            data = json.load(f)
        
        days = data.get("days_stored", 0)
        return {
            "ok":     days >= 2,
            "days":   days,
            "detail": f"{days} days stored",
        }
    except Exception as e:
        return {"ok": False, "detail": f"History read error: {e}"}


def _check_disk() -> dict:
    """Check disk usage."""
    data_dir = _HERE / getattr(config, "NSE_DATA_DIR",
                               getattr(config, "DATA_DIR", "nse_data"))
    
    total_mb = 0
    for folder in [data_dir, _HERE / "output", _HERE / "logs"]:
        if folder.exists():
            total_mb += sum(
                f.stat().st_size for f in folder.rglob("*") if f.is_file()
            ) / 1_048_576
    
    db_path = _HERE / getattr(config, "DB_PATH", "nse_scanner.db")
    if db_path.exists():
        total_mb += db_path.stat().st_size / 1_048_576
    
    return {
        "ok":       total_mb < 500,
        "total_mb": round(total_mb, 1),
        "detail":   f"{total_mb:.1f} MB total",
    }


def generate_health_report() -> dict:
    """
    Generate full health check report.
    
    Returns dict with all check results + formatted message.
    """
    now = datetime.now()
    
    # Run all checks
    scan_check = _check_scan_freshness()
    db_check   = _check_database()
    hist_check = _check_history()
    disk_check = _check_disk()
    
    # User stats
    users       = _load_users()
    total_users = len(users)
    
    today_str   = date.today().isoformat()
    active_today = sum(
        1 for u in users.values()
        if u.get("daily_visits", {}).get(today_str, 0) > 0
    )
    
    # Activity stats
    activity = get_activity_stats(days=1)
    
    # New users today
    new_today = sum(
        1 for u in users.values()
        if u.get("first_seen", "")[:10] == today_str
    )
    
    # Overall status
    all_ok = scan_check["ok"] and db_check["ok"] and hist_check["ok"]
    
    return {
        "timestamp":    now.strftime("%Y-%m-%d %H:%M:%S"),
        "overall_ok":   all_ok,
        "scan":         scan_check,
        "database":     db_check,
        "history":      hist_check,
        "disk":         disk_check,
        "total_users":  total_users,
        "active_today": active_today,
        "new_today":    new_today,
        "activity":     activity,
    }


def format_health_report(report: dict) -> str:
    """Format health report as HTML for Telegram."""
    
    status_emoji = "✅" if report["overall_ok"] else "❌"
    
    msg  = f"🏥 <b>DAILY HEALTH CHECK — {report['timestamp'][:10]}</b>\n"
    msg += f"Status: {status_emoji} {'ALL OK' if report['overall_ok'] else 'ISSUES FOUND'}\n"
    msg += "━" * 30 + "\n\n"
    
    # System checks
    msg += "<b>System</b>\n"
    
    checks = [
        ("Scan Data", report["scan"]),
        ("Database",  report["database"]),
        ("History",   report["history"]),
        ("Disk",      report["disk"]),
    ]
    
    for name, check in checks:
        icon = "✅" if check["ok"] else "❌"
        msg += f"  {icon} {name}: {check['detail']}\n"
    
    msg += "\n"
    
    # User stats
    msg += "<b>Users</b>\n"
    msg += f"  👥 Total registered: {report['total_users']}\n"
    msg += f"  📱 Active today: {report['active_today']}\n"
    msg += f"  🆕 New today: {report['new_today']}\n"
    msg += "\n"
    
    # Activity stats
    activity = report["activity"]
    msg += "<b>Activity (Today)</b>\n"
    msg += f"  📊 Total actions: {activity['total_actions']}\n"
    msg += f"  👤 Unique users: {activity['unique_users']}\n"
    
    if activity.get("top_actions"):
        msg += "  🔝 Top actions:\n"
        for action, count in activity["top_actions"][:5]:
            msg += f"     <code>{action}</code>: {count}\n"
    
    msg += "\n"
    
    # Active users detail
    if activity.get("top_users"):
        users = _load_users()
        msg += "<b>Most Active Users Today</b>\n"
        for uid, count in activity["top_users"][:8]:
            user = users.get(uid, {})
            name = user.get("full_name", "Unknown")
            uname = user.get("username", "")
            uname_str = f" @{uname}" if uname else ""
            msg += f"  • {name}{uname_str}: {count} actions\n"
    
    msg += "\n━" * 30 + "\n"
    msg += f"<i>Next check: Tomorrow 11:30 PM</i>"
    
    return msg


def format_user_list() -> str:
    """Format full user list for admin /users command."""
    users = _load_users()
    
    if not users:
        return "👥 <b>Bot Users</b>\n\nNo users registered yet."
    
    msg  = f"👥 <b>BOT USERS</b> ({len(users)} total)\n"
    msg += "━" * 30 + "\n\n"
    
    # Sort by last seen, most recent first
    sorted_users = sorted(
        users.values(),
        key=lambda u: u.get("last_seen", ""),
        reverse=True
    )
    
    today_str = date.today().isoformat()
    
    for i, user in enumerate(sorted_users, 1):
        name   = user.get("full_name", "Unknown")
        uname  = user.get("username", "")
        uid    = user.get("user_id", "?")
        visits = user.get("total_visits", 0)
        first  = user.get("first_seen", "?")[:10]
        last   = user.get("last_seen", "?")[:10]
        blocked = " 🚫" if user.get("is_blocked") else ""
        
        today_visits = user.get("daily_visits", {}).get(today_str, 0)
        active_badge = " 🟢" if today_visits > 0 else ""
        
        uname_str = f" @{uname}" if uname else ""
        
        msg += (
            f"<b>{i}.</b> {name}{uname_str}{active_badge}{blocked}\n"
            f"   ID: <code>{uid}</code> | "
            f"Visits: {visits} | "
            f"Since: {first} | "
            f"Last: {last}"
        )
        
        if today_visits > 0:
            msg += f" | Today: {today_visits}"
        
        msg += "\n\n"
    
    # Summary
    active = sum(
        1 for u in users.values()
        if u.get("daily_visits", {}).get(today_str, 0) > 0
    )
    
    msg += "━" * 30 + "\n"
    msg += f"🟢 Active today: {active} | 👥 Total: {len(users)}"
    
    return msg


def format_user_detail(user_id: str) -> str:
    """Format detailed view of one user for admin."""
    users = _load_users()
    user  = users.get(str(user_id))
    
    if not user:
        return f"User {user_id} not found."
    
    name    = user.get("full_name", "Unknown")
    uname   = user.get("username", "")
    visits  = user.get("total_visits", 0)
    first   = user.get("first_seen", "?")
    last    = user.get("last_seen", "?")
    blocked = user.get("is_blocked", False)
    daily   = user.get("daily_visits", {})
    
    msg  = f"👤 <b>User Detail</b>\n"
    msg += "━" * 30 + "\n\n"
    msg += f"Name: <b>{name}</b>\n"
    msg += f"Username: @{uname}\n" if uname else ""
    msg += f"ID: <code>{user_id}</code>\n"
    msg += f"Status: {'🚫 Blocked' if blocked else '✅ Active'}\n"
    msg += f"First seen: {first}\n"
    msg += f"Last seen: {last}\n"
    msg += f"Total visits: {visits}\n\n"
    
    # Daily activity (last 7 days)
    if daily:
        msg += "<b>Daily Activity (last 7 days)</b>\n"
        sorted_days = sorted(daily.items(), reverse=True)[:7]
        for day, count in sorted_days:
            bar = "█" * min(count, 20)
            msg += f"  {day}: {bar} {count}\n"
    
    # Recent activity from log
    msg += "\n<b>Recent Actions</b>\n"
    if ACTIVITY_FILE.exists():
        recent = []
        try:
            with open(ACTIVITY_FILE, 'r', encoding='utf-8') as f:
                for line in f:
                    if f"user={user_id}" in line:
                        recent.append(line.strip())
            
            for entry in recent[-10:]:
                # Extract timestamp and action
                ts     = entry[1:20] if entry.startswith("[") else ""
                action = entry.split("action=")[-1] if "action=" in entry else "?"
                atype  = ""
                if "type=" in entry:
                    atype = entry.split("type=")[1].split(" ")[0]
                msg += f"  {ts} [{atype}] {action}\n"
        except Exception:
            msg += "  Could not read activity log\n"
    
    return msg


# ══════════════════════════════════════════════════════════════
# 4. SEND HEALTH CHECK TO ADMIN
# ══════════════════════════════════════════════════════════════

def send_health_check() -> bool:
    """
    Generate and send health check to admin via Telegram.
    Called by scheduler at 11:30 PM IST.
    """
    token   = getattr(config, "TELEGRAM_TOKEN", "")
    chat_id = ADMIN_CHAT_ID
    
    if not token or not chat_id:
        log.warning("Cannot send health check — Telegram not configured")
        return False
    
    # Clean up old activity logs
    cleanup_old_activity(keep_days=30)
    
    # Generate report
    report  = generate_health_report()
    message = format_health_report(report)
    
    # Send
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    
    try:
        r = requests.post(url, data={
            "chat_id":    chat_id,
            "text":       message,
            "parse_mode": "HTML",
        }, timeout=10)
        
        if r.status_code == 200:
            log.info("Health check sent to admin")
            return True
        
        log.error(f"Health check send failed: {r.status_code} — {r.text[:200]}")
        
        # Fallback without HTML
        r2 = requests.post(url, data={
            "chat_id": chat_id,
            "text":    message.replace('<b>','').replace('</b>','')
                             .replace('<i>','').replace('</i>','')
                             .replace('<code>','').replace('</code>',''),
        }, timeout=10)
        return r2.status_code == 200
    
    except Exception as e:
        log.error(f"Health check send error: {e}")
        return False


# ══════════════════════════════════════════════════════════════
# 5. GUIDE DELIVERY
# ══════════════════════════════════════════════════════════════

def format_guide_message() -> str:
    """Format the scanner guide intro message."""
    msg  = f"📖 <b>How to Read the NSE Scanner</b>\n"
    msg += "━" * 30 + "\n\n"
    
    msg += "<b>Quick Overview:</b>\n\n"
    
    msg += "🎯 <b>Score (0–10)</b>\n"
    msg += "  Each stock is scored on 7 signals:\n"
    msg += "  HMA trend (+2), Volume (+2), Breakout (+2),\n"
    msg += "  RSI (+1), MACD (+1), 52W High (+1), RR (+1)\n\n"
    
    msg += "🏆 <b>Tiers</b>\n"
    msg += "  8–10 = HIGH CONVICTION (strongest setups)\n"
    msg += "  5–7  = WATCHLIST (monitor, wait for entry)\n"
    msg += "  0–4  = Not shown (no valid signal)\n\n"
    
    msg += "📊 <b>Trade Plan</b>\n"
    msg += "  Entry = Today's close price\n"
    msg += "  SL = Your safety net (exit if price drops here)\n"
    msg += "  T1 = Book 50% profit (~1 month)\n"
    msg += "  T2 = Book remaining 50% (~3 months)\n"
    msg += "  RR = Risk:Reward ratio (always 1:2 minimum)\n\n"
    
    msg += "📈 <b>Returns (1M/2M/3M)</b>\n"
    msg += "  How much the stock moved in last 1/2/3 months\n"
    msg += "  Ideal: all positive and accelerating\n\n"
    
    msg += "📂 <b>Categories</b>\n"
    msg += "  📈 Consistently Rising — in list 5+ days\n"
    msg += "  🚀 Clear Uptrend — fresh breakout confirmed\n"
    msg += "  🔝 Close to Peak — near 52-week high\n"
    msg += "  📉 Recovering — dip in uptrend (buy-the-dip)\n"
    msg += "  🛡️ Safer Bets — tight SL, high delivery\n"
    msg += "  ⚠️ Handle with Care — risk signals present\n\n"
    
    msg += "━" * 30 + "\n"
    msg += "👇 <i>Tap the button below for the full PDF guide</i>"
    
    return msg


# ══════════════════════════════════════════════════════════════
# CLI — Test health check manually
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="NSE Bot Admin Tools")
    parser.add_argument("--health",  action="store_true", help="Show health report")
    parser.add_argument("--users",   action="store_true", help="Show user list")
    parser.add_argument("--send",    action="store_true", help="Send health check to Telegram")
    parser.add_argument("--stats",   action="store_true", help="Show activity stats")
    args = parser.parse_args()
    
    if args.health:
        report = generate_health_report()
        msg    = format_health_report(report)
        import re
        print(re.sub(r'<[^>]+>', '', msg))
    
    elif args.users:
        msg = format_user_list()
        import re
        print(re.sub(r'<[^>]+>', '', msg))
    
    elif args.send:
        ok = send_health_check()
        print(f"Health check sent: {ok}")
    
    elif args.stats:
        stats = get_activity_stats(days=1)
        print(f"Today's stats:")
        print(f"  Actions: {stats['total_actions']}")
        print(f"  Users:   {stats['unique_users']}")
        print(f"  Top actions: {stats['top_actions'][:5]}")
    
    else:
        parser.print_help()
