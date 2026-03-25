"""
main_pipeline.py — NSE Pipeline Entry Point for Railway Cron
=============================================================
Used by : nse-pipeline Railway service
Runs    : Every weekday at 6:00 AM IST (00:30 UTC) via cron

Pipeline:
    Step 1 → Download today's NSE file
    Step 2 → Load into SQLite database
    Step 3 → Scan stocks for momentum signals
    Step 4 → Generate Excel + send Telegram notification
    Step 5 → Save telegram_last_scan.json + scan_history.json
    Step 6 → Push BOTH JSON files to GitHub
    Step 7 → Trigger nse-bot redeploy

Required Railway Variables:
    TELEGRAM_TOKEN   — live bot token
    TELEGRAM_CHAT_ID — your chat ID
    GITHUB_TOKEN     — personal access token with repo scope
    GITHUB_REPO      — JayeshSRathod/nse-scanner
    GITHUB_BRANCH    — main
"""

import os
import sys
import json
import types
import base64
import requests
from datetime import date, datetime, timedelta
from pathlib import Path

# ── Force UTF-8 ───────────────────────────────────────────────
os.environ['PYTHONIOENCODING'] = 'utf-8'
os.environ['PYTHONUTF8']       = '1'

print("=" * 55)
print("  NSE PIPELINE — DAILY SCAN")
print(f"  {datetime.now().strftime('%d-%b-%Y %H:%M:%S')} IST")
print("=" * 55)

# ── Load .env locally ─────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── Environment variables ─────────────────────────────────────
TOKEN         = os.environ.get("TELEGRAM_TOKEN",   "").strip()
CHAT_ID       = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
GITHUB_TOKEN  = os.environ.get("GITHUB_TOKEN",     "").strip()
GITHUB_REPO   = os.environ.get("GITHUB_REPO",
                "JayeshSRathod/nse-scanner").strip()
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main").strip()

print(f"[ENV] TELEGRAM_TOKEN   = {'SET' if TOKEN       else 'NOT SET ❌'}")
print(f"[ENV] TELEGRAM_CHAT_ID = {'SET' if CHAT_ID     else 'NOT SET ❌'}")
print(f"[ENV] GITHUB_TOKEN     = {'SET' if GITHUB_TOKEN else 'NOT SET ❌'}")
print(f"[ENV] GITHUB_REPO      = {GITHUB_REPO}")

missing = []
if not TOKEN:        missing.append("TELEGRAM_TOKEN")
if not CHAT_ID:      missing.append("TELEGRAM_CHAT_ID")
if not GITHUB_TOKEN: missing.append("GITHUB_TOKEN")

if missing:
    print(f"\n[ERROR] Missing variables: {', '.join(missing)}")
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
print("[ENV] Config module built")

# ── Create folders ────────────────────────────────────────────
for folder in ["logs", "output", "nse_data"]:
    Path(folder).mkdir(exist_ok=True)


# ══════════════════════════════════════════════════════════════
# HOLIDAY CHECK
# ══════════════════════════════════════════════════════════════

NSE_HOLIDAYS = {
    date(2026, 1, 26), date(2026, 3, 25), date(2026, 4, 2),
    date(2026, 4, 10), date(2026, 4, 14), date(2026, 5, 1),
    date(2026, 8, 15), date(2026, 10, 2), date(2026, 10, 22),
    date(2026, 11, 5), date(2026, 12, 25),
}

def is_trading_day(d: date) -> bool:
    if d.weekday() >= 5:
        return False
    if d in NSE_HOLIDAYS:
        return False
    return True

def get_last_trading_day(from_date: date = None) -> date:
    d = from_date or date.today()
    while not is_trading_day(d):
        d -= timedelta(days=1)
    return d


# ══════════════════════════════════════════════════════════════
# GITHUB PUSH
# ══════════════════════════════════════════════════════════════

def push_file_to_github(file_path: Path, commit_msg: str = None) -> bool:
    """Push any file to GitHub."""
    if not file_path.exists():
        print(f"[GITHUB] File not found: {file_path}")
        return False

    content     = file_path.read_text(encoding="utf-8")
    content_b64 = base64.b64encode(content.encode()).decode()
    headers     = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept":        "application/vnd.github.v3+json",
    }
    api_url = (f"https://api.github.com/repos/{GITHUB_REPO}"
               f"/contents/{file_path.name}")

    # Get current SHA
    sha = None
    try:
        r = requests.get(api_url, headers=headers, timeout=10)
        if r.status_code == 200:
            sha = r.json().get("sha")
    except Exception:
        pass

    today    = date.today().strftime("%d-%b-%Y")
    payload  = {
        "message": commit_msg or f"Auto: {file_path.name} {today}",
        "content": content_b64,
        "branch":  GITHUB_BRANCH,
    }
    if sha:
        payload["sha"] = sha

    try:
        r = requests.put(api_url, headers=headers,
                         json=payload, timeout=30)
        if r.status_code in (200, 201):
            print(f"[GITHUB] ✅ Pushed: {file_path.name}")
            return True
        else:
            print(f"[GITHUB] ❌ Failed: {r.status_code} {r.text[:200]}")
            return False
    except Exception as e:
        print(f"[GITHUB] Error: {e}")
        return False


# ══════════════════════════════════════════════════════════════
# MAIN PIPELINE
# ══════════════════════════════════════════════════════════════

def run_pipeline():
    from time import time
    t0 = time()

    today = date.today()

    # Holiday check
    if not is_trading_day(today):
        last_td = get_last_trading_day(today - timedelta(days=1))
        print(f"\n[PIPELINE] {today} is not a trading day")
        print(f"[PIPELINE] Using last trading day: {last_td}")
        today = last_td

    print(f"\n[PIPELINE] Scan date: {today.strftime('%d-%b-%Y')}")

    # ── Step 1: Download ──────────────────────────────────────
    print("\n[STEP 1] Downloading NSE data...")
    try:
        from nse_historical_downloader import download_direct
        download_direct(today)
        print("[STEP 1] ✅ Download complete")
    except Exception as e:
        print(f"[STEP 1] ⚠️ Download failed: {e}")
        print("[STEP 1] Continuing with existing data...")

    # ── Step 2: Load ──────────────────────────────────────────
    print("\n[STEP 2] Loading into database...")
    try:
        from nse_loader import init_database, load_day
        init_database()
        result = load_day(today, do_cleanup=False)
        print(f"[STEP 2] ✅ Loaded: {sum(result['rows'].values())} rows")
    except Exception as e:
        print(f"[STEP 2] ❌ Load failed: {e}")
        return False

    # ── Step 3: Scan ──────────────────────────────────────────
    print("\n[STEP 3] Scanning stocks...")
    try:
        from nse_scanner import scan_stocks
        results_df = scan_stocks(scan_date=today)
        if results_df.empty:
            print("[STEP 3] ❌ No results")
            return False
        hc = (results_df['conviction'] == 'HIGH CONVICTION').sum() \
             if 'conviction' in results_df.columns else 0
        wl = (results_df['conviction'] == 'Watchlist').sum() \
             if 'conviction' in results_df.columns else 0
        print(f"[STEP 3] ✅ {len(results_df)} stocks | HC: {hc} | WL: {wl}")
    except Exception as e:
        print(f"[STEP 3] ❌ Scan failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    # ── Step 4: Output ────────────────────────────────────────
    print("\n[STEP 4] Generating output...")
    try:
        from nse_output import generate_report
        generate_report(results_df, today)
        print("[STEP 4] ✅ Excel + Telegram + JSON saved")
    except Exception as e:
        print(f"[STEP 4] ❌ Output failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
# ── Step 5: Verify both JSON files exist AND are fresh ──────────
    print("\n[STEP 5] Verifying JSON files...")

    json_path = Path("telegram_last_scan.json")
    history_path = Path("scan_history.json")

    expected_date = today.strftime("%Y-%m-%d")

    if not json_path.exists():
        print("[STEP 5] ❌ telegram_last_scan.json missing")
        return False

    try:
        d = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[STEP 5] ❌ Failed to read telegram_last_scan.json: {e}")
        return False

    found_date = d.get("scan_date")

    if found_date != expected_date:
        print(
            "[STEP 5] ❌ STALE JSON DETECTED\n"
            f" Expected : {expected_date}\n"
            f" Found    : {found_date}\n"
            " Aborting pipeline to prevent stale GitHub push."
        )
        return False

    print(
        f"[STEP 5] ✅ telegram_last_scan.json OK "
        f"({d.get('total_stocks')} stocks, date={found_date})"
    )

    if history_path.exists():
        h = json.loads(history_path.read_text(encoding="utf-8"))
        print(f"[STEP 5] ✅ scan_history.json: {h.get('days_stored')} days")
    else:
        print("[STEP 5] ⚠️ scan_history.json not present yet (first run)")

    # ── Step 5: Verify both JSON files exist ──────────────────
    #print("\n[STEP 5] Verifying JSON files...")
    #json_path    = Path("telegram_last_scan.json")
    #history_path = Path("scan_history.json")

    #if json_path.exists():
    #    d = json.loads(json_path.read_text(encoding="utf-8"))
    #    print(f"[STEP 5] ✅ telegram_last_scan.json: "
    #          f"{d.get('total_stocks')} stocks, date={d.get('scan_date')}")
    #else:
     #   print("[STEP 5] ❌ telegram_last_scan.json missing")
     #   return False

    #if history_path.exists():
     #   h = json.loads(history_path.read_text(encoding="utf-8"))
      #  print(f"[STEP 5] ✅ scan_history.json: "
       #       f"{h.get('days_stored')} days stored")
    #else:
     #   print("[STEP 5] ⚠️ scan_history.json not yet created "
      #        "(will appear after first save_scan_results call)")
    
# ── Step 6: Push JSON files to GitHub (only if fresh) ─────────
    
    #print("\n[STEP 6] Pushing JSON files to GitHub...")
    print("\n[STEP 6] Pushing JSON files to GitHub...")
    scan_date_in_json = d.get("scan_date")
    if scan_date_in_json != expected_date:
        print(
            "[STEP 6] ❌ REFUSING PUSH — JSON IS STALE\n"
            f" Expected : {expected_date}\n"
            f" Found    : {scan_date_in_json}"
        )
        return False

    pushed_json = push_file_to_github(
        json_path,
        f"Auto: scan data {expected_date}"
    )

    pushed_history = False
    if history_path.exists():
        pushed_history = push_file_to_github(
            history_path,
            f"Auto: history update {expected_date}"
        )

    print(
        f"[STEP 6] JSON pushed: {'✅' if pushed_json else '❌'} | "
        f"History pushed: {'✅' if pushed_history else '⚠️'}"
    )

    # ── Step 6: Push both files to GitHub ─────────────────────
   # print("\n[STEP 6] Pushing JSON files to GitHub...")

    #pushed_json    = push_file_to_github(
     #   json_path,
      #  f"Auto: scan data {today.strftime('%d-%b-%Y')}"
    #)
    #pushed_history = False
    #if history_path.exists():
     #   pushed_history = push_file_to_github(
      #      history_path,
       #     f"Auto: history update {today.strftime('%d-%b-%Y')}"
       # )
    #else:
     #   print("[STEP 6] ⚠️ No history file to push yet")

    # ── Summary ───────────────────────────────────────────────
    elapsed = round(time() - t0, 1)
    print(f"\n{'='*55}")
    print(f"  PIPELINE COMPLETE in {elapsed}s")
    print(f"  Scan date      : {today.strftime('%d-%b-%Y')}")
    print(f"  Stocks scanned : {len(results_df)}")
    print(f"  HC signals     : {hc}")
    print(f"  Watchlist      : {wl}")
    print(f"  JSON pushed    : {'✅' if pushed_json    else '❌'}")
    print(f"  History pushed : {'✅' if pushed_history else '⚠️ first run'}")
    print(f"  Next run       : Tomorrow 6:00 AM IST")
    print(f"{'='*55}")

    return True


# ── Entry point ───────────────────────────────────────────────
if __name__ == "__main__":
    success = run_pipeline()
    sys.exit(0 if success else 1)
