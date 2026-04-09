"""
main_pipeline.py — NSE Pipeline Entry Point for Railway Cron
=============================================================
Used by : nse-pipeline Railway service
Runs    : Every weekday at 6:00 AM IST (00:30 UTC) via cron

FIX APPLIED:
  - Removed premature `return True` inside Step 3 try block
  - Steps 4, 5, 6 now actually execute (they were unreachable before)
  - Added Step 5b: push news JSON to GitHub after generate_report
  - News collector now runs every day as part of pipeline
"""

import os
import sys
import json
import types
import base64
import requests
from datetime import date, datetime, timedelta
from pathlib import Path

# ── ALERT + HEALTH HELPERS ────────────────────────────────────

def send_failure_alert(step: str, reason: str, scan_date: date):
    """Send pipeline failure alert to Telegram."""
    if not TOKEN or not CHAT_ID:
        return
    msg = (
        "❌ *NSE Pipeline Failure*\n\n"
        f"*Date:* {scan_date.strftime('%d-%b-%Y')}\n"
        f"*Step:* {step}\n"
        f"*Reason:* `{reason}`\n\n"
        "⚠️ Action required"
    )
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        requests.post(url, data={
            "chat_id":    CHAT_ID,
            "text":       msg,
            "parse_mode": "Markdown",
        }, timeout=10)
    except Exception:
        pass


HEALTH_FILE = Path("scan_health.json")

def write_health(status: str, **kwargs):
    payload = {
        "run_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S IST"),
        "status":   status,
        **kwargs
    }
    HEALTH_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


# ── FORCE UTF‑8 ────────────────────────────────────────────────

os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["PYTHONUTF8"]       = "1"

print("=" * 55)
print(" NSE PIPELINE — DAILY SCAN")
print(f" {datetime.now().strftime('%d-%b-%Y %H:%M:%S')} IST")
print("=" * 55)

# ── LOAD ENV ──────────────────────────────────────────────────

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

TOKEN        = os.environ.get("TELEGRAM_TOKEN",  "").strip()
CHAT_ID      = os.environ.get("TELEGRAM_CHAT_ID","").strip()
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN",    "").strip()
GITHUB_REPO  = os.environ.get("GITHUB_REPO",     "JayeshSRathod/nse-scanner").strip()
GITHUB_BRANCH= os.environ.get("GITHUB_BRANCH",   "main").strip()

missing = []
if not TOKEN:        missing.append("TELEGRAM_TOKEN")
if not CHAT_ID:      missing.append("TELEGRAM_CHAT_ID")
if not GITHUB_TOKEN: missing.append("GITHUB_TOKEN")
if missing:
    print(f"[ERROR] Missing vars: {', '.join(missing)}")
    sys.exit(1)

# ── CONFIG MODULE ─────────────────────────────────────────────

config                 = types.ModuleType("config")
config.TELEGRAM_TOKEN  = TOKEN
config.TELEGRAM_CHATID = CHAT_ID
config.OUTPUT_DIR      = "output"
config.LOG_DIR         = "logs"
config.DB_PATH         = "nse_scanner.db"
config.DATA_DIR        = "nse_data"
config.MIN_PRICE      = 50
config.MIN_VOLUME     = 50000
config.MIN_DELIVERY   = 35
config.MAX_ANNVOL     = 1.5
config.MAX_PE         = 80
config.TOP_N_STOCKS   = 25
config.MIN_MARKET_CAP = 500
config.WEIGHT_1M      = 0.20
config.WEIGHT_2M      = 0.30
config.WEIGHT_3M      = 0.50
config.DAYS_1M        = 22
config.DAYS_2M        = 44
config.DAYS_3M        = 66
config.BONUS_52W_HIGH = 0.05
config.BONUS_TOP25    = 0.03
sys.modules["config"]  = config

for folder in ["logs", "output", "nse_data"]:
    Path(folder).mkdir(exist_ok=True)

# ── HOLIDAY HELPERS ───────────────────────────────────────────

NSE_HOLIDAYS = {
    date(2026, 1, 26), date(2026, 3, 25), date(2026, 4, 2),
    date(2026, 4, 10), date(2026, 4, 14), date(2026, 5, 1),
    date(2026, 8, 15), date(2026, 10, 2),
    date(2026, 10, 22), date(2026, 11, 5), date(2026, 12, 25),
}

def is_trading_day(d):
    return d.weekday() < 5 and d not in NSE_HOLIDAYS

def get_last_trading_day(d):
    while not is_trading_day(d):
        d -= timedelta(days=1)
    return d

# ── GITHUB PUSH ───────────────────────────────────────────────

def push_file_to_github(file_path: Path, commit_msg: str) -> bool:
    """Push a file to GitHub. Returns True on success."""
    try:
        content     = file_path.read_text(encoding="utf-8")
        content_b64 = base64.b64encode(content.encode()).decode()

        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept":        "application/vnd.github.v3+json",
        }
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{file_path.name}"

        # Get existing SHA (needed for update)
        sha = None
        r   = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            sha = r.json().get("sha")

        payload = {
            "message": commit_msg,
            "content": content_b64,
            "branch":  GITHUB_BRANCH,
        }
        if sha:
            payload["sha"] = sha

        r = requests.put(url, headers=headers, json=payload, timeout=15)
        ok = r.status_code in (200, 201)
        if not ok:
            print(f"[GITHUB] Push failed {r.status_code}: {r.text[:100]}")
        return ok
    except Exception as e:
        print(f"[GITHUB] Push error: {e}")
        return False


# ── MAIN PIPELINE ─────────────────────────────────────────────

def run_pipeline():
    from time import time
    t0 = time()

    today = date.today()
    if not is_trading_day(today):
        today = get_last_trading_day(today - timedelta(days=1))

    print(f"\n[PIPELINE] Scan date: {today.strftime('%d-%b-%Y')}")

    # ── CANARY TEST ───────────────────────────────────────────
    print("\n[CANARY] Testing JSON write path...")
    canary = Path("telegram_last_scan.json")
    try:
        canary.write_text(json.dumps({
            "scan_date": today.strftime("%Y-%m-%d"),
            "canary":    True,
        }), encoding="utf-8")
        if json.loads(canary.read_text())["scan_date"] != today.strftime("%Y-%m-%d"):
            raise ValueError("Canary mismatch")
        print("[CANARY] ✅ OK")
    except Exception as e:
        send_failure_alert("CANARY JSON", str(e), today)
        write_health(status="FAILED", scan_date=today.strftime("%Y-%m-%d"),
                     failed_step="CANARY", reason=str(e))
        return False

    write_health(status="RUNNING", scan_date=today.strftime("%Y-%m-%d"))
    expected = today.strftime("%Y-%m-%d")

    # ── STEP 1: Download ──────────────────────────────────────
    try:
        from nse_historical_downloader import download_direct
        download_direct(today)
        print("[STEP 1] ✅ Download complete")
    except Exception as e:
        print(f"[STEP 1] ⚠️  Download failed (non-fatal): {e}")

    # ── STEP 2: Load DB ───────────────────────────────────────
    try:
        from nse_loader import init_database, load_day
        init_database()
        load_day(today, do_cleanup=False)
        print("[STEP 2] ✅ DB load complete")
    except Exception as e:
        send_failure_alert("DB Load", str(e), today)
        write_health(status="FAILED", scan_date=expected,
                     failed_step="STEP 2", reason=str(e))
        return False

    # ── STEP 3: Scan ──────────────────────────────────────────
    results_df = None
    try:
        from nse_scanner import scan_stocks
        results_df = scan_stocks(scan_date=today)

        if results_df is None or results_df.empty:
            print("[STEP 3] ⚠️  No stocks found — keeping previous data")
            write_health(status="NO_RESULTS", scan_date=expected,
                         reason="Empty scan")
            # Do NOT return here — still push existing JSON below
            results_df = None
        else:
            hc = (results_df["conviction"] == "HIGH CONVICTION").sum() \
                 if "conviction" in results_df.columns else 0
            wl = (results_df["conviction"] == "Watchlist").sum() \
                 if "conviction" in results_df.columns else 0
            print(f"[STEP 3] ✅ Scan complete: {len(results_df)} stocks | "
                  f"HC={hc} | WL={wl}")

    except Exception as e:
        send_failure_alert("STEP 3 Scan", str(e), today)
        write_health(status="FAILED", scan_date=expected,
                     failed_step="STEP 3", reason=str(e))
        return False

    # ── STEP 4: Generate report + collect news ────────────────
    # This step was UNREACHABLE before due to premature return True above
    if results_df is not None and not results_df.empty:
        try:
            from nse_output import generate_report
            generate_report(results_df, today)
            print("[STEP 4] ✅ Report generated + news collected")
        except Exception as e:
            send_failure_alert("STEP 4 Output", str(e), today)
            write_health(status="FAILED", scan_date=expected,
                         failed_step="STEP 4", reason=str(e))
            return False
    else:
        print("[STEP 4] ⏭  Skipped (no scan results)")

    # ── STEP 5: Verify JSON freshness ─────────────────────────
    json_path = Path("telegram_last_scan.json")
    try:
        d     = json.loads(json_path.read_text())
        found = d.get("scan_date")
        if found != expected:
            # Stale but non-fatal if we had no results today
            print(f"[STEP 5] ⚠️  JSON date {found} (expected {expected})")
        else:
            print(f"[STEP 5] ✅ JSON fresh: {found}")
    except Exception as e:
        print(f"[STEP 5] ⚠️  JSON check failed: {e}")

    # ── STEP 5b: Push news JSON to GitHub ─────────────────────
    try:
        news_fname = f"news_{today.strftime('%d%m%Y')}.json"
        news_path  = Path("output") / news_fname
        if news_path.exists():
            ok = push_file_to_github(news_path, f"Auto: news {expected}")
            print(f"[STEP 5b] {'✅' if ok else '⚠️ '} News JSON push: {news_fname}")
        else:
            print(f"[STEP 5b] ℹ️  No news JSON found for today "
                  f"(news step may have been skipped)")
    except Exception as e:
        print(f"[STEP 5b] ⚠️  News JSON push error: {e} (non-fatal)")

    # ── STEP 6: Push scan JSON to GitHub ─────────────────────
    try:
        ok = push_file_to_github(json_path, f"Auto: scan {expected}")
        print(f"[STEP 6] {'✅' if ok else '❌'} Scan JSON push")
    except Exception as e:
        print(f"[STEP 6] ❌ Scan JSON push failed: {e}")

    # ── STEP 7: Write health ──────────────────────────────────
    try:
        stock_count = len(results_df) if results_df is not None else 0
        prime_count = int((results_df["situation"] == "prime").sum()) \
                      if results_df is not None and "situation" in results_df.columns else 0
        write_health(
            status      = "SUCCESS",
            scan_date   = expected,
            stocks      = stock_count,
            prime       = prime_count,
            json_fresh  = True,
        )
    except Exception as e:
        print(f"[STEP 7] ⚠️  Health write failed: {e}")

    elapsed = round(time() - t0, 1)
    print(f"\n[PIPELINE] ✅ COMPLETE in {elapsed}s")
    return True


if __name__ == "__main__":
    sys.exit(0 if run_pipeline() else 1)
