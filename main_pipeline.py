"""
main_pipeline.py — NSE Pipeline Entry Point for Railway Cron
=============================================================
Used by : nse-pipeline Railway service
Runs : Every weekday at 6:00 AM IST (00:30 UTC) via cron
"""

import os
import sys
import json
import types
import base64
import requests
from datetime import date, datetime, timedelta
from pathlib import Path


def send_failure_alert(step, reason, scan_date):
    if not TOKEN or not CHAT_ID:
        return
    msg = (f"❌ *NSE Pipeline Failure*\n\n*Date:* {scan_date.strftime('%d-%b-%Y')}\n"
           f"*Step:* {step}\n*Reason:* `{reason}`\n\n⚠️ Action required")
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)
    except Exception:
        pass


HEALTH_FILE = Path("scan_health.json")

def write_health(status, **kwargs):
    payload = {"run_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S IST"), "status": status, **kwargs}
    HEALTH_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["PYTHONUTF8"] = "1"

print("=" * 55)
print(" NSE PIPELINE — DAILY SCAN")
print(f" {datetime.now().strftime('%d-%b-%Y %H:%M:%S')} IST")
print("=" * 55)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

TOKEN         = os.environ.get("TELEGRAM_TOKEN", "").strip()
CHAT_ID       = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
GITHUB_TOKEN  = os.environ.get("GITHUB_TOKEN", "").strip()
GITHUB_REPO   = os.environ.get("GITHUB_REPO", "JayeshSRathod/nse-scanner").strip()
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main").strip()

missing = []
if not TOKEN:        missing.append("TELEGRAM_TOKEN")
if not CHAT_ID:      missing.append("TELEGRAM_CHAT_ID")
if not GITHUB_TOKEN: missing.append("GITHUB_TOKEN")
if missing:
    print(f"[ERROR] Missing vars: {', '.join(missing)}")
    sys.exit(1)

config                 = types.ModuleType("config")
config.TELEGRAM_TOKEN  = TOKEN
config.TELEGRAM_CHATID = CHAT_ID
config.OUTPUT_DIR      = "output"
config.LOG_DIR         = "logs"
config.DB_PATH         = "nse_scanner.db"
config.DATA_DIR        = "nse_data"
sys.modules["config"]  = config

for folder in ["logs", "output", "nse_data"]:
    Path(folder).mkdir(exist_ok=True)

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


def push_file_to_github(file_path, commit_msg):
    content     = file_path.read_text(encoding="utf-8")
    content_b64 = base64.b64encode(content.encode()).decode()
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{file_path.name}"
    sha = None
    r = requests.get(url, headers=headers)
    if r.status_code == 200:
        sha = r.json().get("sha")
    payload = {"message": commit_msg, "content": content_b64, "branch": GITHUB_BRANCH}
    if sha:
        payload["sha"] = sha
    r = requests.put(url, headers=headers, json=payload)
    return r.status_code in (200, 201)


def run_pipeline():
    from time import time
    t0 = time()

    today = date.today()
    if not is_trading_day(today):
        today = get_last_trading_day(today - timedelta(days=1))

    print(f"\n[PIPELINE] Scan date: {today.strftime('%d-%b-%Y')}")

    # ── CANARY TEST ──
    print("\n[CANARY] Testing pagination JSON write path...")
    canary = Path("telegram_last_scan.json")
    try:
        canary.write_text(json.dumps({"scan_date": today.strftime("%Y-%m-%d"), "canary": True}), encoding="utf-8")
        if json.loads(canary.read_text())["scan_date"] != today.strftime("%Y-%m-%d"):
            raise ValueError("Canary mismatch")
        print("[CANARY] ✅ OK")
    except Exception as e:
        send_failure_alert("CANARY JSON", str(e), today)
        write_health(status="FAILED", scan_date=today.strftime("%Y-%m-%d"), failed_step="CANARY", reason=str(e))
        return False

    write_health(status="RUNNING", scan_date=today.strftime("%Y-%m-%d"))

    # ── STEP 1: Download ──
    try:
        from nse_historical_downloader import download_direct
        download_direct(today)
    except Exception:
        pass

    # ── STEP 2: Load DB ──
    try:
        from nse_loader import init_database, load_day
        init_database()
        load_day(today, do_cleanup=False)
    except Exception as e:
        send_failure_alert("DB Load", str(e), today)
        write_health(status="FAILED", scan_date=today.strftime("%Y-%m-%d"), failed_step="STEP 2", reason=str(e))
        return False

    # ── STEP 3: Scan ──
    try:
        from nse_scanner import scan_stocks
        results_df = scan_stocks(scan_date=today)

        if results_df.empty:
            print("⚠️ No stocks found — keeping previous data")
            write_health(status="NO_RESULTS", scan_date=today.strftime("%Y-%m-%d"), reason="Empty scan")
            return True
    except Exception as e:
        send_failure_alert("STEP 3 Scan", str(e), today)
        write_health(status="FAILED", scan_date=today.strftime("%Y-%m-%d"), failed_step="STEP 3", reason=str(e))
        return False

    hc = (results_df["conviction"] == "HIGH CONVICTION").sum()
    wl = (results_df["conviction"] == "Watchlist").sum()

    # ── STEP 4: Output ──
    try:
        from nse_output import generate_report
        generate_report(results_df, today)
    except Exception as e:
        send_failure_alert("STEP 4 Output", str(e), today)
        write_health(status="FAILED", scan_date=today.strftime("%Y-%m-%d"), failed_step="STEP 4", reason=str(e))
        return False

    # ── STEP 5: Freshness check ──
    json_path = Path("telegram_last_scan.json")
    d = json.loads(json_path.read_text())
    expected = today.strftime("%Y-%m-%d")
    if d.get("scan_date") != expected:
        send_failure_alert("JSON Freshness", f"Expected {expected}, found {d.get('scan_date')}", today)
        write_health(status="FAILED", scan_date=expected, failed_step="STEP 5", reason="STALE JSON")
        return False

    # ── STEP 6: Push to GitHub ──
    push_file_to_github(json_path, f"Auto: scan {expected}")

    history_path = Path("scan_history.json")
    if history_path.exists():
        if push_file_to_github(history_path, f"Auto: history {expected}"):
            print(f"  ✅ scan_history.json pushed to GitHub")
        else:
            print(f"  ⚠️  scan_history.json push failed (non-fatal)")

    write_health(
        status="SUCCESS", scan_date=expected,
        stocks_scanned=len(results_df), high_conviction=int(hc), watchlist=int(wl),
        json_fresh=True
    )

    elapsed = round(time() - t0, 1)
    print(f"\nPIPELINE COMPLETE in {elapsed}s")
    return True


if __name__ == "__main__":
    sys.exit(0 if run_pipeline() else 1)
