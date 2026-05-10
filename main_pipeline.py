"""
main_pipeline.py — NSE Pipeline Entry Point for Railway Cron
=============================================================
Now includes: historical backfill on first run (when DB is empty)
v2: Added Step 5 — Portfolio Manager (nse_portfolio.py)
"""

import os
import sys
import json
import types
import base64
import sqlite3
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
if not TOKEN:   missing.append("TELEGRAM_TOKEN")
if not CHAT_ID: missing.append("TELEGRAM_CHAT_ID")
if missing:
    print(f"[ERROR] Missing vars: {', '.join(missing)}")
    sys.exit(1)

if not GITHUB_TOKEN:
    print(f"[INFO] GITHUB_TOKEN not set — GitHub push disabled (local mode)")

config                  = types.ModuleType("config")
config.TELEGRAM_TOKEN   = TOKEN
config.TELEGRAM_CHATID  = CHAT_ID
config.OUTPUT_DIR       = "output"
config.LOG_DIR          = "logs"
config.DB_PATH          = "nse_scanner.db"
config.DATA_DIR         = "nse_data"
config.NSE_DATA_DIR     = "nse_data"
config.MIN_PRICE        = 50
config.MIN_VOLUME       = 50000
config.MIN_DELIVERY     = 35
config.MAX_ANNVOL       = 1.5
config.MAX_PE           = 80
config.TOP_N_STOCKS     = 25
config.MIN_MARKET_CAP   = 500
config.MIN_TURNOVER     = 200
config.WEIGHT_1M        = 0.20
config.WEIGHT_2M        = 0.30
config.WEIGHT_3M        = 0.50
config.DAYS_1M          = 22
config.DAYS_2M          = 44
config.DAYS_3M          = 66
config.BONUS_52W_HIGH   = 0.05
config.BONUS_TOP25      = 0.03
sys.modules["config"]   = config

for folder in ["logs", "output", "nse_data"]:
    Path(folder).mkdir(exist_ok=True)

NSE_HOLIDAYS = {
    date(2025, 1, 26), date(2025, 2, 26), date(2025, 3, 14),
    date(2025, 4, 10), date(2025, 4, 14), date(2025, 4, 18),
    date(2025, 5, 1),  date(2025, 8, 15), date(2025, 8, 27),
    date(2025, 10, 2), date(2025, 10, 21), date(2025, 10, 22),
    date(2025, 11, 5), date(2025, 12, 25),
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

def get_trading_days(start, end):
    days = []
    d = start
    while d <= end:
        if is_trading_day(d):
            days.append(d)
        d += timedelta(days=1)
    return days


def push_file_to_github(file_path, commit_msg):
    content     = file_path.read_text(encoding="utf-8")
    content_b64 = base64.b64encode(content.encode()).decode()
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{file_path.as_posix()}"
    sha = None
    r = requests.get(url, headers=headers)
    if r.status_code == 200:
        sha = r.json().get("sha")
    payload = {"message": commit_msg, "content": content_b64, "branch": GITHUB_BRANCH}
    if sha:
        payload["sha"] = sha
    r = requests.put(url, headers=headers, json=payload)
    return r.status_code in (200, 201)


def db_has_enough_data(min_days=22):
    """Check if DB has enough trading days for scanner to work."""
    db_path = Path("nse_scanner.db")
    if not db_path.exists() or db_path.stat().st_size < 10000:
        return False, 0
    try:
        conn = sqlite3.connect(str(db_path))
        row = conn.execute("SELECT COUNT(DISTINCT date) FROM daily_prices").fetchone()
        conn.close()
        days = row[0] if row else 0
        return days >= min_days, days
    except Exception:
        return False, 0


def backfill_historical_data(target_date, days_back=90):
    """
    Download and load historical data when DB is empty.
    Downloads 90 trading days of data from NSE archives.
    This runs ONCE on first deploy, then daily cron adds 1 day at a time.
    """
    print(f"\n{'='*55}")
    print(f"  HISTORICAL BACKFILL — Loading {days_back} days")
    print(f"  This runs once. Future runs load 1 day only.")
    print(f"{'='*55}")

    from nse_historical_downloader import download_direct
    from nse_loader import init_database, load_day

    init_database()

    end_date   = target_date
    start_date = target_date - timedelta(days=int(days_back * 1.5))
    trading_days = get_trading_days(start_date, end_date)
    trading_days = trading_days[-days_back:]

    print(f"  Date range: {trading_days[0].strftime('%d-%b-%Y')} to {trading_days[-1].strftime('%d-%b-%Y')}")
    print(f"  Trading days to load: {len(trading_days)}")

    loaded = 0
    failed = 0
    skipped = 0

    for i, d in enumerate(trading_days):
        try:
            download_direct(d)
            result = load_day(d, do_cleanup=False)
            if result["status"] == "ok":
                loaded += 1
            elif result["status"] in ("skip", "already_loaded"):
                skipped += 1
            else:
                failed += 1
        except Exception as e:
            failed += 1
            if i < 3:
                print(f"  ❌ {d.strftime('%d-%b-%Y')}: {e}")

        if (i + 1) % 10 == 0:
            print(f"  Progress: {i+1}/{len(trading_days)} "
                  f"(loaded={loaded} skipped={skipped} failed={failed})")

        import time
        time.sleep(0.5)

    print(f"\n  BACKFILL COMPLETE:")
    print(f"    Loaded : {loaded}")
    print(f"    Skipped: {skipped}")
    print(f"    Failed : {failed}")

    has_enough, total_days = db_has_enough_data()
    print(f"    DB now has {total_days} trading days of data")
    print(f"    Scanner ready: {'YES' if has_enough else 'NO'}")

    return has_enough


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
        canary.write_text(json.dumps({"scan_date": today.strftime("%Y-%m-%d"), "canary": True}), encoding="utf-8")
        if json.loads(canary.read_text())["scan_date"] != today.strftime("%Y-%m-%d"):
            raise ValueError("Canary mismatch")
        print("[CANARY] ✅ OK")
    except Exception as e:
        send_failure_alert("CANARY JSON", str(e), today)
        write_health(status="FAILED", scan_date=today.strftime("%Y-%m-%d"), failed_step="CANARY", reason=str(e))
        return False

    write_health(status="RUNNING", scan_date=today.strftime("%Y-%m-%d"))

    # ── STEP 0: Check if DB needs backfill ────────────────────
    has_enough, current_days = db_has_enough_data(min_days=22)
    print(f"\n[STEP 0] DB check: {current_days} trading days loaded")

    if not has_enough:
        print(f"[STEP 0] Need at least 22 days for scanner. Starting backfill...")
        try:
            backfill_ok = backfill_historical_data(today, days_back=90)
            if not backfill_ok:
                print("[STEP 0] ⚠️  Backfill incomplete but continuing...")
        except Exception as e:
            print(f"[STEP 0] Backfill error: {e}")
            send_failure_alert("Backfill", str(e), today)
    else:
        print(f"[STEP 0] ✅ DB has enough data. Loading today only.")

        # Step 1: Download today
        try:
            from nse_historical_downloader import download_direct
            download_direct(today)
        except Exception:
            pass

        # Step 2: Load today
        try:
            from nse_loader import init_database, load_day
            init_database()
            load_day(today, do_cleanup=False)
        except Exception as e:
            send_failure_alert("DB Load", str(e), today)
            write_health(status="FAILED", scan_date=today.strftime("%Y-%m-%d"), failed_step="STEP 2", reason=str(e))
            return False

    # ── STEP 3: Scan ──────────────────────────────────────────
    print(f"\n{'='*55}\n  Step 3: Scanner\n{'='*55}")
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

    # ── STEP 3.5: News Collection & Enrichment ────────────────
    news_data = {}
    try:
        from nse_news_collector import get_news_for_stocks, enrich_scanner_results, save_news
        shortlist = results_df.head(15)['symbol'].tolist()
        print(f"\n[STEP 3.5] Collecting news for {len(shortlist)} stocks...")
        news_data = get_news_for_stocks(shortlist, days=30)
        save_news(news_data, today)
        results_df = enrich_scanner_results(results_df, news_data)
        print(f"[STEP 3.5] ✅ Enrichment complete")
    except Exception as e:
        print(f"[STEP 3.5] ⚠️ News enrichment failed: {e}")

    hc = (results_df["conviction"] == "HIGH CONVICTION").sum() if "conviction" in results_df.columns else 0
    wl = (results_df["conviction"] == "Watchlist").sum() if "conviction" in results_df.columns else 0

    # ── STEP 4: Output (Excel + Telegram morning scan) ────────
    print(f"\n{'='*55}\n  Step 4: Output\n{'='*55}")
    try:
        from nse_output import generate_report
        generate_report(results_df, today)
    except Exception as e:
        send_failure_alert("STEP 4 Output", str(e), today)
        write_health(status="FAILED", scan_date=today.strftime("%Y-%m-%d"), failed_step="STEP 4", reason=str(e))
        return False

    # ── STEP 5: Portfolio Manager ─────────────────────────────
    print(f"\n{'='*55}\n  Step 5: Portfolio Manager\n{'='*55}")
    try:
        from nse_portfolio import run_portfolio_step

        json_path      = Path("telegram_last_scan.json")
        scan_data      = json.loads(json_path.read_text(encoding="utf-8"))
        scanner_stocks = scan_data.get("stocks", [])
        scan_date_str  = scan_data.get("scan_date", today.strftime("%Y-%m-%d"))

        portfolio_summary = run_portfolio_step(
            scanner_stocks = scanner_stocks,
            scan_date      = scan_date_str,
            news_data      = news_data,   # passed from Step 3.5 (empty dict if news failed)
        )

        print(f"  Open     : {portfolio_summary['open']}")
        print(f"  Added    : {portfolio_summary['added']}")
        print(f"  Exited   : {portfolio_summary['exited']}")
        print(f"  SL trail : {portfolio_summary['sl_updated']}")
        print(f"  [OK] Portfolio message sent to Telegram")

    except ImportError:
        print("  [SKIP] nse_portfolio.py not found — add it to enable portfolio tracking")
    except Exception as e:
        # Non-fatal — pipeline continues even if portfolio step fails
        print(f"  [WARNING] Portfolio step failed (non-fatal): {e}")
        import traceback
        traceback.print_exc()

    # ── STEP 6: Freshness check ───────────────────────────────
    print(f"\n{'='*55}\n  Step 6: Freshness Check\n{'='*55}")
    json_path = Path("telegram_last_scan.json")
    d = json.loads(json_path.read_text())
    expected = today.strftime("%Y-%m-%d")
    if d.get("scan_date") != expected:
        send_failure_alert("JSON Freshness", f"Expected {expected}, found {d.get('scan_date')}", today)
        write_health(status="FAILED", scan_date=expected, failed_step="STEP 6", reason="STALE JSON")
        return False
    print(f"  ✅ JSON date matches: {expected}")

    # ── STEP 6.1: Push news JSON to GitHub ────────────────────
    try:
        _news_fname = f"news_{today.strftime('%d%m%Y')}.json"
        _news_path  = Path("output") / _news_fname
        if _news_path.exists():
            latest_news = Path("output") / "news_latest.json"
            latest_news.write_text(_news_path.read_text(encoding="utf-8"), encoding="utf-8")
            push_file_to_github(latest_news, f"Auto: news latest {expected}")
            ok = push_file_to_github(_news_path, f"Auto: news {expected}")
            if ok:
                print(f"  ✅ News JSON pushed: {_news_fname}")
            else:
                print(f"  ⚠️  News JSON push failed (non-fatal)")
        else:
            print(f"  ℹ️  No news JSON for today (news step may have been skipped)")
    except Exception as e:
        print(f"  ⚠️  News JSON push error: {e} (non-fatal)")

    # ── STEP 7: Push scan JSONs to GitHub ─────────────────────
    print(f"\n{'='*55}\n  Step 7: GitHub Push\n{'='*55}")
    if push_file_to_github(json_path, f"Auto: scan {expected}"):
        print(f"  ✅ telegram_last_scan.json pushed")

    history_path = Path("scan_history.json")
    if history_path.exists():
        if push_file_to_github(history_path, f"Auto: history {expected}"):
            print(f"  ✅ scan_history.json pushed")

    # Push portfolio.json to GitHub (so bot can read it)
    portfolio_path = Path("portfolio.json")
    if portfolio_path.exists():
        if push_file_to_github(portfolio_path, f"Auto: portfolio {expected}"):
            print(f"  ✅ portfolio.json pushed")

    write_health(
        status="SUCCESS", scan_date=expected,
        stocks_scanned=len(results_df), high_conviction=int(hc), watchlist=int(wl),
        json_fresh=True
    )

    elapsed = round(time() - t0, 1)
    print(f"\n{'='*55}")
    print(f"  PIPELINE COMPLETE in {elapsed}s")
    print(f"{'='*55}")
    return True


if __name__ == "__main__":
    sys.exit(0 if run_pipeline() else 1)