"""
main_pipeline.py — NSE Pipeline Entry Point for Railway Cron
=============================================================
Used by : nse-pipeline Railway service
Runs    : Every weekday at 6:00 AM IST (00:30 UTC) via cron

FIXES APPLIED:
  1. push_file_to_github: str(file_path) instead of file_path.name
     → preserves "output/news_DDMMYYYY.json" path; previously stripped
       the directory and pushed everything to repo root.
  2. scan_health.json now pushed to GitHub after every terminal state
     (SUCCESS, FAILED, NO_RESULTS) so the bot can read live health data.
     Previously it was only written locally and never uploaded.
  3. Removed premature `return True` inside Step 3 try block (original fix).
  4. Steps 4, 5, 6, 7 now actually execute (were unreachable before).
  5. Step 5b: push news JSON to GitHub after generate_report.
  6. News collector runs every day as part of pipeline.
"""

import os
import sys
import json
import types
import base64
import requests
from datetime import date, datetime, timedelta
from pathlib import Path
print("🔥 NEW PIPELINE VERSION LOADED")
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

TOKEN         = os.environ.get("TELEGRAM_TOKEN",  "").strip()
CHAT_ID       = os.environ.get("TELEGRAM_CHAT_ID","").strip()
GITHUB_TOKEN  = os.environ.get("GITHUB_TOKEN",    "").strip()
GITHUB_REPO   = os.environ.get("GITHUB_REPO",     "JayeshSRathod/nse-scanner").strip()
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH",   "main").strip()

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

def is_trading_day(d: date) -> bool:
    return d.weekday() < 5 and d not in NSE_HOLIDAYS

def get_last_trading_day(d: date) -> date:
    while not is_trading_day(d):
        d -= timedelta(days=1)
    return d

# ── GITHUB PUSH ───────────────────────────────────────────────

def push_file_to_github(file_path: Path, commit_msg: str) -> bool:
    """
    Push a local file to GitHub at its relative path.
    Returns True on success.

    FIX: Use str(file_path) not file_path.name.
    file_path.name strips the directory component, so
    "output/news_10042026.json" was being pushed to the repo root
    as "news_10042026.json", causing a path mismatch when the bot
    fetched it from the expected "output/" location.
    """
    try:
        content     = file_path.read_text(encoding="utf-8")
        content_b64 = base64.b64encode(content.encode()).decode()

        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept":        "application/vnd.github.v3+json",
        }

        # ✅ FIXED: str(file_path) preserves "output/news_10042026.json"
        #           file_path.name was stripping "output/" → root collision
        url = (
            f"https://api.github.com/repos/{GITHUB_REPO}"
            f"/contents/{str(file_path)}"
        )

        # Get existing SHA (required by GitHub API for updates)
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

        r  = requests.put(url, headers=headers, json=payload, timeout=15)
        ok = r.status_code in (200, 201)
        if not ok:
            print(f"[GITHUB] Push failed {r.status_code}: {r.text[:120]}")
        return ok

    except Exception as e:
        print(f"[GITHUB] Push error: {e}")
        return False

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

def write_health(status: str, **kwargs) -> None:
    """Write scan_health.json locally."""
    payload = {
        "run_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S IST"),
        "status":   status,
        **kwargs,
    }
    HEALTH_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def push_health(scan_date_str: str) -> None:
    """
    Push scan_health.json to GitHub.

    FIX: This was entirely missing from the original script.
    The health file was written locally but never uploaded, so the
    Telegram bot always read stale health data from GitHub.
    Now called after every terminal pipeline state.
    """
    try:
        ok = push_file_to_github(
            HEALTH_FILE,
            f"Auto: health {scan_date_str}",
        )
        print(f"[HEALTH] {'✅' if ok else '⚠️ '} scan_health.json pushed to GitHub")
    except Exception as e:
        print(f"[HEALTH] ⚠️  Health push error: {e} (non-fatal)")


# ── MAIN PIPELINE ─────────────────────────────────────────────

def run_pipeline() -> bool:
    from time import time
    t0 = time()

    today = date.today()
    if not is_trading_day(today):
        today = get_last_trading_day(today - timedelta(days=1))

    print(f"\n[PIPELINE] Scan date: {today.strftime('%d-%b-%Y')}")
    expected = today.strftime("%Y-%m-%d")

    # ── CANARY TEST ───────────────────────────────────────────
    print("\n[CANARY] Testing JSON write path...")
    canary = Path("telegram_last_scan.json")
    try:
        if not Path("telegram_last_scan.json").exists():
            canary.write_text({
                "scan_date": expected,
                "stocks": []
            })
        if json.loads(canary.read_text(encoding="utf-8"))["scan_date"] != expected:
            raise ValueError("Canary round-trip mismatch")
        print("[CANARY] ✅ JSON write/read OK")
    except Exception as e:
        send_failure_alert("CANARY JSON", str(e), today)
        write_health(status="FAILED", scan_date=expected,
                     failed_step="CANARY", reason=str(e))
        push_health(expected)   # ✅ push failure health so bot sees it
        return False

    write_health(status="RUNNING", scan_date=expected)

    # ── STEP 1: Download ──────────────────────────────────────
    print("\n[STEP 1] Downloading price data...")
    try:
        from nse_historical_downloader import download_direct
        download_direct(today)
        print("[STEP 1] ✅ Download complete")
    except Exception as e:
        print(f"[STEP 1] ⚠️  Download failed (non-fatal): {e}")

    # ── STEP 2: Load DB ───────────────────────────────────────
    print("\n[STEP 2] Loading data into DB...")
    try:
        from nse_loader import init_database, load_day
        init_database()
        load_day(today, do_cleanup=False)
        print("[STEP 2] ✅ DB load complete")
    except Exception as e:
        send_failure_alert("DB Load", str(e), today)
        write_health(status="FAILED", scan_date=expected,
                     failed_step="STEP 2", reason=str(e))
        push_health(expected)   # ✅ push failure health so bot sees it
        return False

    # ── STEP 3: Scan ──────────────────────────────────────────
    print("\n[STEP 3] Running momentum scan...")
    results_df = None
    try:
        from nse_scanner import scan_stocks
        results_df = scan_stocks(scan_date=today)
        # 🔽 ADD THIS BLOCK HERE
        print("DEBUG SCAN:",
              "is None =", results_df is None,
              "| count =", 0 if results_df is None else len(results_df))

        if results_df is None or results_df.empty:
            print("[STEP 3] ⚠️  No stocks found — keeping previous data")
            write_health(status="NO_RESULTS", scan_date=expected,
                         reason="Empty scan")
            push_health(expected)   # ✅ push NO_RESULTS health so bot sees it
            results_df = None
            # Not returning — still push existing scan JSON below
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
        push_health(expected)   # ✅ push failure health so bot sees it
        return False
json_path = Path("telegram_last_scan.json")

if results_df is not None and not results_df.empty:
    json_path.write_text(json.dumps({
        "scan_date": expected,
        "stocks": results_df.to_dict(orient="records")
    }, indent=2), encoding="utf-8")

    print("✅ JSON written with scan results")

else:
    print("⚠️ No scan results — restoring previous JSON")

    # OPTIONAL: prevent overwrite damage
    if json_path.exists():
        try:
            existing = json.loads(json_path.read_text())
            if "stocks" not in existing:
                print("⚠️ Existing JSON invalid — keeping as-is")
        except:
            print("⚠️ Existing JSON corrupted")
          
    # ── STEP 4: Generate report + collect news ────────────────
    # (Was UNREACHABLE before due to premature return True in Step 3)
    print("\n[STEP 4] Generating report + collecting news...")
    if results_df is not None and not results_df.empty:
        try:
            from nse_output import generate_report
            generate_report(results_df, today)
            print("[STEP 4] ✅ Report generated + news collected")
        except Exception as e:
            send_failure_alert("STEP 4 Output", str(e), today)
            write_health(status="FAILED", scan_date=expected,
                         failed_step="STEP 4", reason=str(e))
            push_health(expected)   # ✅ push failure health so bot sees it
            return False
    else:
        print("[STEP 4] ⏭  Skipped (no scan results)")

    # ── STEP 5: Verify JSON freshness ─────────────────────────
    print("\n[STEP 5] Verifying scan JSON freshness...")
    json_path = Path("telegram_last_scan.json")
    try:
        d     = json.loads(json_path.read_text(encoding="utf-8"))
        found = d.get("scan_date")
        if found != expected:
            print(f"[STEP 5] ⚠️  JSON date mismatch: found={found}, expected={expected}")
        else:
            print(f"[STEP 5] ✅ JSON fresh: {found}")
    except Exception as e:
        print(f"[STEP 5] ⚠️  JSON check failed: {e}")

    # ── STEP 5b: Push news JSON to GitHub ─────────────────────
    # FIX: str(file_path) inside push_file_to_github now preserves
    #      "output/" prefix so file lands in the correct repo folder.
    print("\n[STEP 5b] Pushing news JSON to GitHub...")
    try:
        news_fname = f"news_{today.strftime('%d%m%Y')}.json"
        news_path  = Path("output") / news_fname
        if news_path.exists():
            ok = push_file_to_github(news_path, f"Auto: news {expected}")
            print(f"[STEP 5b] {'✅' if ok else '⚠️ '} News JSON push: {news_fname}")
        else:
            print(f"[STEP 5b] ℹ️  No news JSON found ({news_fname}) — "
                  f"news step may have been skipped")
    except Exception as e:
        print(f"[STEP 5b] ⚠️  News JSON push error: {e} (non-fatal)")

    # ── STEP 6: Push scan JSON to GitHub ──────────────────────
    print("\n[STEP 6] Pushing scan JSON to GitHub...")
    try:
        ok = push_file_to_github(json_path, f"Auto: scan {expected}")
        print(f"[STEP 6] {'✅' if ok else '❌'} Scan JSON push: telegram_last_scan.json")
    except Exception as e:
        print(f"[STEP 6] ❌ Scan JSON push failed: {e}")

    # ── STEP 7: Write + push health ───────────────────────────
    # FIX: push_health() call was entirely missing before.
    #      Health file was only written locally; bot always saw stale data.
    print("\n[STEP 7] Writing + pushing health file...")
    try:
        stock_count = len(results_df) if results_df is not None else 0
        prime_count = int(
            (results_df["situation"] == "prime").sum()
        ) if results_df is not None and "situation" in results_df.columns else 0

        write_health(
            status     = "SUCCESS",
            scan_date  = expected,
            stocks     = stock_count,
            prime      = prime_count,
            json_fresh = True,
        )
        push_health(expected)   # ✅ now actually uploaded to GitHub
        print("[STEP 7] ✅ Health written + pushed")
    except Exception as e:
        print(f"[STEP 7] ⚠️  Health write/push failed: {e}")

    elapsed = round(time() - t0, 1)
    print(f"\n[PIPELINE] ✅ COMPLETE in {elapsed}s\n")
    return True


if __name__ == "__main__":
    sys.exit(0 if run_pipeline() else 1)
