"""
main.py — NSE Bot Entry Point for Railway (nse-bot service)
============================================================
Used by: nse-bot Railway service (24/7)
Runs   : Always — answers Telegram messages

If telegram_last_scan.json is missing locally,
fetches it from GitHub automatically so bot
always has fresh data even after redeploy.

Required Railway Variables (nse-bot service):
    TELEGRAM_TOKEN   — bot token (nsescanner_live_bot)
    TELEGRAM_CHAT_ID — your chat ID
    GITHUB_TOKEN     — to fetch JSON from GitHub
    GITHUB_REPO      — JayeshSRathod/nse-scanner
"""

import os
import sys
import json
import types
import base64
import requests
from datetime import date
from pathlib import Path

# ── Force UTF-8 ───────────────────────────────────────────────
os.environ['PYTHONIOENCODING'] = 'utf-8'
os.environ['PYTHONUTF8']       = '1'

# ── Load .env locally ─────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── Read environment variables ────────────────────────────────
TOKEN         = os.environ.get("TELEGRAM_TOKEN",   "").strip()
CHAT_ID       = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
GITHUB_TOKEN  = os.environ.get("GITHUB_TOKEN",     "").strip()
GITHUB_REPO   = os.environ.get("GITHUB_REPO",
                "JayeshSRathod/nse-scanner").strip()
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main").strip()

print(f"[MAIN] TELEGRAM_TOKEN   = {'SET (' + TOKEN[:15] + '...)' if TOKEN else 'NOT SET ❌'}")
print(f"[MAIN] TELEGRAM_CHAT_ID = {CHAT_ID or 'NOT SET ❌'}")

if not TOKEN:
    print("[ERROR] TELEGRAM_TOKEN not set — add to Railway Variables")
    sys.exit(1)

if not CHAT_ID:
    print("[ERROR] TELEGRAM_CHAT_ID not set — add to Railway Variables")
    sys.exit(1)

# ── Build config module ───────────────────────────────────────
config                 = types.ModuleType("config")
config.TELEGRAM_TOKEN  = TOKEN
config.TELEGRAM_CHATID = CHAT_ID
config.OUTPUT_DIR      = "output"
config.LOG_DIR         = "logs"
config.DB_PATH         = "nse_scanner.db"
config.NSE_DATA_DIR    = "nse_data"
config.DATA_DIR        = "nse_data"
config.MIN_PRICE       = 50
config.MIN_VOLUME      = 50000
config.MIN_DELIVERY    = 35
config.MAX_ANNVOL      = 1.5
config.MAX_PE          = 80
config.TOP_N_STOCKS    = 25
config.WEIGHT_1M       = 0.20
config.WEIGHT_2M       = 0.30
config.WEIGHT_3M       = 0.50
config.DAYS_1M         = 22
config.DAYS_2M         = 44
config.DAYS_3M         = 66
config.BONUS_52W_HIGH  = 0.05
config.BONUS_TOP25     = 0.03
sys.modules["config"]  = config
print("[MAIN] Config module built")

# ── Create folders ────────────────────────────────────────────
for folder in ["logs", "output", "nse_data"]:
    Path(folder).mkdir(exist_ok=True)


# ══════════════════════════════════════════════════════════════
# FETCH JSON FROM GITHUB IF MISSING
# ══════════════════════════════════════════════════════════════

def fetch_json_from_github() -> bool:
    """
    Download telegram_last_scan.json from GitHub.
    Called on bot startup if local file is missing or stale.
    """
    if not GITHUB_TOKEN:
        print("[GITHUB] No GITHUB_TOKEN — cannot fetch JSON")
        return False

    print(f"[GITHUB] Fetching telegram_last_scan.json from {GITHUB_REPO}...")

    try:
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept":        "application/vnd.github.v3+json",
        }
        url = (f"https://api.github.com/repos/{GITHUB_REPO}"
               f"/contents/telegram_last_scan.json"
               f"?ref={GITHUB_BRANCH}")

        r = requests.get(url, headers=headers, timeout=15)

        if r.status_code == 200:
            data    = r.json()
            content = base64.b64decode(data["content"]).decode("utf-8")
            Path("telegram_last_scan.json").write_text(
                content, encoding="utf-8")

            parsed    = json.loads(content)
            stocks    = parsed.get("total_stocks", 0)
            scan_date = parsed.get("scan_date", "?")
            print(f"[GITHUB] ✅ Fetched: {stocks} stocks (date: {scan_date})")
            return True

        elif r.status_code == 404:
            print("[GITHUB] JSON not found on GitHub yet")
            print("[GITHUB] Run nse-pipeline cron first to generate data")
            return False
        else:
            print(f"[GITHUB] ❌ Fetch failed: {r.status_code}")
            return False

    except Exception as e:
        print(f"[GITHUB] Error: {e}")
        return False


# ── Ensure scan data exists ───────────────────────────────────
RESULTS_FILE = Path("telegram_last_scan.json")

if RESULTS_FILE.exists():
    try:
        existing = json.loads(RESULTS_FILE.read_text(encoding="utf-8"))
        stocks   = existing.get("total_stocks", 0)
        scan_date = existing.get("scan_date", "?")
        print(f"[MAIN] Local JSON found: {stocks} stocks (date: {scan_date})")

        # Check if stale (older than 3 days) — fetch fresh from GitHub
        try:
            from datetime import datetime, timedelta
            file_date = datetime.strptime(scan_date, "%Y-%m-%d").date()
            age_days  = (date.today() - file_date).days
            if age_days > 3:
                print(f"[MAIN] Data is {age_days} days old — fetching fresh from GitHub")
                fetch_json_from_github()
        except Exception:
            pass

    except Exception as e:
        print(f"[MAIN] Local JSON unreadable: {e} — fetching from GitHub")
        fetch_json_from_github()
else:
    print("[MAIN] No local JSON — fetching from GitHub...")
    fetched = fetch_json_from_github()

    if not fetched:
        # Write minimal sample so bot has something to show
        print("[MAIN] Writing sample data (5 stocks)")
        sample = {
            "scan_date":    str(date.today()),
            "total_stocks": 5,
            "page_size":    5,
            "stocks": [
                {
                    "rank": 1, "symbol": "RELIANCE", "score": 8,
                    "return_1m_pct": 5.2, "return_2m_pct": 9.1,
                    "return_3m_pct": 18.4, "close": 2450,
                    "volume": 8500000, "delivery_pct": 52.3,
                    "sl": 2278, "target1": 2622, "target2": 2794
                },
                {
                    "rank": 2, "symbol": "HDFCBANK", "score": 7,
                    "return_1m_pct": 4.1, "return_2m_pct": 7.8,
                    "return_3m_pct": 14.2, "close": 1680,
                    "volume": 12000000, "delivery_pct": 61.5,
                    "sl": 1562, "target1": 1798, "target2": 1916
                },
                {
                    "rank": 3, "symbol": "INFY", "score": 7,
                    "return_1m_pct": 3.8, "return_2m_pct": 6.2,
                    "return_3m_pct": 11.5, "close": 1520,
                    "volume": 6200000, "delivery_pct": 55.8,
                    "sl": 1414, "target1": 1626, "target2": 1732
                },
                {
                    "rank": 4, "symbol": "TCS", "score": 6,
                    "return_1m_pct": 2.9, "return_2m_pct": 5.1,
                    "return_3m_pct": 9.8, "close": 3820,
                    "volume": 3100000, "delivery_pct": 67.2,
                    "sl": 3553, "target1": 4087, "target2": 4354
                },
                {
                    "rank": 5, "symbol": "WIPRO", "score": 6,
                    "return_1m_pct": 2.1, "return_2m_pct": 4.3,
                    "return_3m_pct": 8.2, "close": 480,
                    "volume": 9800000, "delivery_pct": 48.6,
                    "sl": 446, "target1": 514, "target2": 548
                },
            ]
        }
        RESULTS_FILE.write_text(
            json.dumps(sample, indent=2), encoding="utf-8")
        print("[MAIN] Sample data written")
        print("[MAIN] Real data arrives after nse-pipeline cron runs at 6:45 PM IST")

# ── Start polling bot ─────────────────────────────────────────
print(f"\n[MAIN] Starting @nsescanner_live_bot...")
print(f"[MAIN] Send 'hi' to get today's stock watchlist\n")

try:
    import nse_telegram_polling as bot
    bot.main()
except KeyboardInterrupt:
    print("\n[MAIN] Stopped")
except Exception as e:
    print(f"\n[MAIN] Bot crashed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)