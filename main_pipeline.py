"""
main_pipeline.py — NSE Pipeline Entry Point for Railway Cron
=============================================================
Used by: nse-pipeline Railway service
Runs   : Every weekday at 6:45 PM IST (13:15 UTC) via cron

Pipeline:
    Step 1 → Download today's NSE file
    Step 2 → Load into SQLite database
    Step 3 → Scan stocks for momentum signals
    Step 4 → Generate Excel + send Telegram notification
    Step 5 → Save telegram_last_scan.json
    Step 6 → Push JSON to GitHub (triggers nse-bot redeploy)

Required Railway Variables (nse-pipeline service):
    TELEGRAM_TOKEN   — bot token (nsescanner_live_bot)
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
from datetime import date, datetime
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

# ── Read environment variables ────────────────────────────────
TOKEN        = os.environ.get("TELEGRAM_TOKEN",   "").strip()
CHAT_ID      = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN",     "").strip()
GITHUB_REPO  = os.environ.get("GITHUB_REPO",
               "JayeshSRathod/nse-scanner").strip()
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main").strip()

print(f"[ENV] TELEGRAM_TOKEN   = {'SET' if TOKEN    else 'NOT SET ❌'}")
print(f"[ENV] TELEGRAM_CHAT_ID = {'SET' if CHAT_ID  else 'NOT SET ❌'}")
print(f"[ENV] GITHUB_TOKEN     = {'SET' if GITHUB_TOKEN else 'NOT SET ❌'}")
print(f"[ENV] GITHUB_REPO      = {GITHUB_REPO}")

# Validate
missing = []
if not TOKEN:        missing.append("TELEGRAM_TOKEN")
if not CHAT_ID:      missing.append("TELEGRAM_CHAT_ID")
if not GITHUB_TOKEN: missing.append("GITHUB_TOKEN")

if missing:
    print(f"\n[ERROR] Missing variables: {', '.join(missing)}")
    print("[ERROR] Add them in Railway → nse-pipeline → Variables")
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
# GITHUB PUSH FUNCTION
# ══════════════════════════════════════════════════════════════

def push_json_to_github(json_path: Path) -> bool:
    """
    Push telegram_last_scan.json to GitHub.
    This triggers nse-bot service to redeploy with fresh data.
    """
    print(f"\n[GITHUB] Pushing {json_path.name} to {GITHUB_REPO}...")

    if not json_path.exists():
        print(f"[GITHUB] ERROR: {json_path} not found")
        return False

    content      = json_path.read_text(encoding="utf-8")
    content_b64  = base64.b64encode(content.encode()).decode()

    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept":        "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    api_url = (f"https://api.github.com/repos/{GITHUB_REPO}"
               f"/contents/{json_path.name}")

    # ── Get current SHA (needed for update) ──────────────────
    sha = None
    try:
        r = requests.get(api_url, headers=headers, timeout=10)
        if r.status_code == 200:
            sha = r.json().get("sha")
            print(f"[GITHUB] Existing file found (sha: {sha[:8]}...)")
        elif r.status_code == 404:
            print("[GITHUB] File not found — will create new")
        else:
            print(f"[GITHUB] GET failed: {r.status_code} {r.text[:100]}")
    except Exception as e:
        print(f"[GITHUB] GET error: {e}")

    # ── Push (create or update) ───────────────────────────────
    today    = date.today().strftime("%d-%b-%Y")
    payload  = {
        "message": f"Auto: scan data {today}",
        "content": content_b64,
        "branch":  GITHUB_BRANCH,
    }
    if sha:
        payload["sha"] = sha

    try:
        r = requests.put(api_url, headers=headers,
                         json=payload, timeout=30)
        if r.status_code in (200, 201):
            print(f"[GITHUB] ✅ Pushed successfully → "
                  f"https://github.com/{GITHUB_REPO}/blob/"
                  f"{GITHUB_BRANCH}/{json_path.name}")
            return True
        else:
            print(f"[GITHUB] ❌ Push failed: {r.status_code}")
            print(f"[GITHUB] Response: {r.text[:200]}")
            return False
    except Exception as e:
        print(f"[GITHUB] Push error: {e}")
        return False


# ══════════════════════════════════════════════════════════════
# TRIGGER BOT REDEPLOY
# ══════════════════════════════════════════════════════════════

def trigger_bot_redeploy():
    """
    Trigger nse-bot Railway service to redeploy.
    Uses Railway API if RAILWAY_TOKEN is set,
    otherwise GitHub push already triggers it via auto-deploy.
    """
    railway_token = os.environ.get("RAILWAY_TOKEN", "").strip()

    if not railway_token:
        print("\n[DEPLOY] No RAILWAY_TOKEN set")
        print("[DEPLOY] GitHub push will trigger auto-redeploy of nse-bot")
        print("[DEPLOY] Make sure nse-bot has 'Deploy on push' enabled in Railway")
        return

    # Railway GraphQL API
    service_id = os.environ.get("BOT_SERVICE_ID", "").strip()
    env_id     = os.environ.get("BOT_ENV_ID", "").strip()

    if not service_id:
        print("[DEPLOY] BOT_SERVICE_ID not set — skipping forced redeploy")
        return

    print(f"\n[DEPLOY] Triggering nse-bot redeploy...")
    try:
        query = """
        mutation serviceInstanceRedeploy($serviceId: String!, $environmentId: String!) {
            serviceInstanceRedeploy(serviceId: $serviceId, environmentId: $environmentId)
        }
        """
        r = requests.post(
            "https://backboard.railway.app/graphql/v2",
            headers={
                "Authorization": f"Bearer {railway_token}",
                "Content-Type":  "application/json",
            },
            json={
                "query":     query,
                "variables": {
                    "serviceId":     service_id,
                    "environmentId": env_id,
                }
            },
            timeout=15,
        )
        if r.status_code == 200:
            print("[DEPLOY] ✅ Bot redeploy triggered")
        else:
            print(f"[DEPLOY] ❌ Failed: {r.status_code} {r.text[:100]}")
    except Exception as e:
        print(f"[DEPLOY] Error: {e}")


# ══════════════════════════════════════════════════════════════
# MAIN PIPELINE
# ══════════════════════════════════════════════════════════════

def run_pipeline():
    from time import time
    t0 = time()

    print("\n[PIPELINE] Starting daily scan pipeline...")

    today = date.today()

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
        print("[STEP 2] Cannot continue without database")
        return False

    # ── Step 3: Scan ──────────────────────────────────────────
    print("\n[STEP 3] Scanning stocks...")
    try:
        from nse_scanner import scan_stocks
        results_df = scan_stocks(scan_date=today)

        if results_df.empty:
            print("[STEP 3] ❌ No results from scanner")
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

    # ── Step 4: Output (Excel + Telegram + JSON) ──────────────
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

    # ── Step 5: Push JSON to GitHub ───────────────────────────
    print("\n[STEP 5] Pushing JSON to GitHub...")
    json_path = Path("telegram_last_scan.json")
    pushed    = push_json_to_github(json_path)

    if pushed:
        print("[STEP 5] ✅ JSON pushed — nse-bot will auto-redeploy")
    else:
        print("[STEP 5] ⚠️ Push failed — bot will use yesterday's data")

    # ── Step 6: Trigger bot redeploy ─────────────────────────
    print("\n[STEP 6] Triggering bot redeploy...")
    trigger_bot_redeploy()

    # ── Summary ───────────────────────────────────────────────
    elapsed = round(time() - t0, 1)
    print(f"\n{'='*55}")
    print(f"  PIPELINE COMPLETE in {elapsed}s")
    print(f"  Stocks scanned : {len(results_df)}")
    print(f"  HC signals     : {hc}")
    print(f"  Watchlist      : {wl}")
    print(f"  JSON pushed    : {'✅' if pushed else '❌'}")
    print(f"  Next run       : Tomorrow 6:45 PM IST")
    print(f"{'='*55}")

    return True


# ── Entry point ───────────────────────────────────────────────
if __name__ == "__main__":
    success = run_pipeline()
    sys.exit(0 if success else 1)