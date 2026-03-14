"""
nse_daily_runner.py — Master Automation Script (v2)
=====================================================
Runs the complete NSE scanner pipeline in one command.

Pipeline:
    Step 1  Download today's NSE files
    Step 2  Load new files into SQLite DB
    Step 3  Run scanner + technical filters  → shortlist
    Step 4  Collect news for shortlist only  → NO re-scan
    Step 5  Enrich results with news flags
    Step 6  Generate Excel + Send Telegram

Key fix v2:
    News collector receives scan results directly.
    Does NOT call scan_stocks() again internally.

Usage:
    python nse_daily_runner.py
    python nse_daily_runner.py --date 05-03-2026
    python nse_daily_runner.py --dry-run
    python nse_daily_runner.py --skip-download
    python nse_daily_runner.py --skip-news

Windows Task Scheduler:
    Program : C:\\Users\\ratho\\nse-scanner\\venv\\Scripts\\python.exe
    Args    : C:\\Users\\ratho\\nse-scanner\\nse_daily_runner.py
    Start in: C:\\Users\\ratho\\nse-scanner
    Trigger : Weekdays 6:45 PM
"""

import os
import sys
import argparse
import logging
import traceback
from datetime import date, datetime, timedelta
from time import time

try:
    import config
except ImportError:
    print("ERROR: config.py not found.")
    sys.exit(1)

# Configuration for auto-cleanup
KEEP_HISTORICAL_DAYS = 180  # Keep 180 days (6 months) of historical data

# ── Logging ───────────────────────────────────────────────────
os.makedirs(config.LOG_DIR, exist_ok=True)
log_file = os.path.join(config.LOG_DIR, "daily_runner.log")

logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s  %(levelname)s  %(message)s",
    handlers= [
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# STEP RUNNER
# ─────────────────────────────────────────────────────────────

def run_step(step_num: int, name: str, fn, *args, **kwargs):
    """
    Run one pipeline step with timing and error handling.
    Returns (success, result, elapsed_seconds)
    """
    print(f"\n{'='*56}")
    print(f"  Step {step_num}: {name}")
    print(f"{'='*56}")
    log.info(f"Starting Step {step_num}: {name}")

    t0 = time()
    try:
        result  = fn(*args, **kwargs)
        elapsed = round(time() - t0, 1)
        print(f"  Done in {elapsed}s")
        log.info(f"Step {step_num} OK ({elapsed}s)")
        return True, result, elapsed
    except Exception as e:
        elapsed = round(time() - t0, 1)
        print(f"  FAILED: {e}")
        log.error(f"Step {step_num} FAILED: {name} — {e}")
        log.error(traceback.format_exc())
        return False, None, elapsed


# STEP 1 — AUTO-CLEANUP OLD DATA
# ─────────────────────────────────────────────────────────────

def step_cleanup() -> dict:
    """Auto-cleanup NSE data older than 180 days."""
    from auto_cleanup_nse_data import cleanup_old_data
    deleted, freed, remaining = cleanup_old_data(keep_days=KEEP_HISTORICAL_DAYS, dry_run=False)
    print(f"  Deleted: {deleted} month(s) | Freed: {freed:.2f} MB | Remaining: {remaining} files")
    return {
        "deleted": deleted,
        "freed_mb": freed,
        "remaining_files": remaining
    }


# ─────────────────────────────────────────────────────────────
# STEP 2 — DOWNLOAD
# ─────────────────────────────────────────────────────────────

def step_download(scan_date: date) -> bool:
    """Download today's NSE files."""
    from nse_historical_downloader import download_direct
    result = download_direct(scan_date)
    print(f"  Files downloaded for {scan_date.strftime('%d-%b-%Y')}")
    return True


# ─────────────────────────────────────────────────────────────
# STEP 3 — LOAD
# ─────────────────────────────────────────────────────────────

def step_load(scan_date: date) -> dict:
    """Load downloaded files into SQLite DB."""
    from nse_loader import init_database, load_day
    init_database()
    result = load_day(scan_date, do_cleanup=False)
    print(f"  Loaded: {sum(result['rows'].values())} rows | status={result['status']}")
    return result


# ─────────────────────────────────────────────────────────────
# STEP 4 — SCAN
# ─────────────────────────────────────────────────────────────

def step_scan(scan_date: date):
    """
    Run momentum + technical scanner.
    Returns ranked DataFrame — passed directly to later steps.
    """
    from nse_scanner import scan_stocks
    results = scan_stocks(scan_date=scan_date)

    if results.empty:
        raise ValueError("Scanner returned no results")

    hc = 0
    wl = 0
    if 'conviction' in results.columns:
        hc = (results['conviction'] == 'HIGH CONVICTION').sum()
        wl = (results['conviction'] == 'Watchlist').sum()

    print(f"  Total : {len(results)} stocks")
    print(f"  HC    : {hc} HIGH CONVICTION")
    print(f"  WL    : {wl} Watchlist")

    return results


# ─────────────────────────────────────────────────────────────
# STEP 5 — COLLECT NEWS (uses scan results — NO re-scan)
# ─────────────────────────────────────────────────────────────

def step_news(scan_results, scan_date: date) -> dict:
    """
    Collect news for HC + Watchlist stocks ONLY.

    Receives scan results from Step 3 directly.
    Does NOT call scan_stocks() again.
    Caps at 15 stocks to avoid rate limiting.
    """
    from nse_news_collector import get_news_for_stocks, save_news

    # Build shortlist from already-scanned results
    if 'conviction' in scan_results.columns:
        shortlist_df = scan_results[
            scan_results['conviction'].isin(['HIGH CONVICTION', 'Watchlist'])
        ]
        shortlist = shortlist_df['symbol'].tolist()
    else:
        # No conviction column — take top 10 by momentum
        shortlist = scan_results.head(10)['symbol'].tolist()

    # Cap to avoid rate limiting
    shortlist = shortlist[:15]

    if not shortlist:
        print("  No HC/Watchlist stocks to collect news for")
        return {}

    print(f"  Collecting news for {len(shortlist)} stocks (HC + Watchlist only)")
    print(f"  Symbols: {', '.join(shortlist)}")
    print(f"  Full universe scan already done in Step 3 — NOT repeating")

    # Collect news — passes symbols directly, no scanning
    news = get_news_for_stocks(shortlist, days=30)

    # Save to output/ folder
    save_news(news, scan_date)

    # Summary
    stocks_with_news = sum(1 for v in news.values() if v.get('has_news'))
    stocks_with_flags = sum(1 for v in news.values() if v.get('flags'))

    print(f"\n  News collected:")
    print(f"    With news  : {stocks_with_news}/{len(shortlist)}")
    print(f"    With flags : {stocks_with_flags}/{len(shortlist)}")

    return news


# ─────────────────────────────────────────────────────────────
# STEP 6 — ENRICH (merge news into scan results)
# ─────────────────────────────────────────────────────────────

def step_enrich(scan_results, news_data: dict):
    """
    Merge news intelligence into scanner DataFrame.
    Adds: news_tone, news_flags, deal_flag, has_risk columns.
    """
    from nse_news_collector import enrich_scanner_results

    if not news_data:
        print("  No news data to merge — skipping enrichment")
        return scan_results

    enriched = enrich_scanner_results(scan_results, news_data)

    # Count enriched stocks
    enriched_count = enriched['news_tone'].notna().sum() if 'news_tone' in enriched.columns else 0
    risk_count     = enriched['has_risk'].sum() if 'has_risk' in enriched.columns else 0

    print(f"  Enriched : {enriched_count} stocks with news context")
    if risk_count:
        print(f"  WARNING  : {risk_count} stocks have risk flags — check before trading")
        risk_stocks = enriched[enriched['has_risk'] == True]['symbol'].tolist()
        print(f"  Risk stocks: {', '.join(risk_stocks)}")

    return enriched


# ─────────────────────────────────────────────────────────────
# STEP 6 — OUTPUT (Excel + Telegram)
# ─────────────────────────────────────────────────────────────

def step_output(results, scan_date: date, dry_run: bool = False) -> dict:
    """Generate Excel and send Telegram."""
    from nse_output import save_excel, send_telegram

    excel_file = save_excel(results, scan_date)
    if excel_file:
        print(f"  Excel: {os.path.basename(excel_file)}")

    if dry_run:
        print("  Telegram: SKIPPED (dry-run mode)")
        tg_sent = False
    else:
        tg_sent = send_telegram(results, scan_date)
        print(f"  Telegram: {'sent' if tg_sent else 'failed'}")

    return {'excel': excel_file, 'telegram': tg_sent}


# ─────────────────────────────────────────────────────────────
# HOLIDAY / TRADING DAY
# ─────────────────────────────────────────────────────────────

NSE_HOLIDAYS = {
    # 2025
    date(2025, 1, 26), date(2025, 2, 26), date(2025, 3, 14),
    date(2025, 4, 10), date(2025, 4, 14), date(2025, 4, 18),
    date(2025, 5, 1),  date(2025, 8, 15), date(2025, 8, 27),
    date(2025, 10, 2), date(2025, 10, 21), date(2025, 10, 22),
    date(2025, 11, 5), date(2025, 12, 25),
    # 2026
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


# ─────────────────────────────────────────────────────────────
# SUMMARY PRINTER
# ─────────────────────────────────────────────────────────────

def print_summary(scan_date: date, steps: list, total_time: float):
    print(f"\n{'#'*56}")
    print(f"  NSE DAILY RUNNER — COMPLETE")
    print(f"  Date  : {scan_date.strftime('%d-%b-%Y')}")
    print(f"  Time  : {total_time:.1f}s")
    print(f"{'─'*56}")

    for num, name, ok, elapsed in steps:
        status = "OK  " if ok else "FAIL"
        print(f"  Step {num}  [{status}]  {name:<30} {elapsed:.1f}s")

    all_ok = all(ok for _, _, ok, _ in steps)
    print(f"{'─'*56}")
    print(f"  Result : {'SUCCESS' if all_ok else 'COMPLETED WITH ERRORS'}")
    print(f"  Log    : {log_file}")
    print(f"{'#'*56}\n")

    log.info(
        f"Pipeline done: {scan_date} "
        f"time={total_time:.1f}s "
        f"status={'OK' if all_ok else 'ERRORS'}"
    )


# ─────────────────────────────────────────────────────────────
# MAIN PIPELINE
# ─────────────────────────────────────────────────────────────

def run_pipeline(scan_date      : date,
                 skip_download  : bool = False,
                 skip_news      : bool = False,
                 dry_run        : bool = False) -> bool:
    """
    Run complete pipeline. Each step receives outputs from
    previous steps — no repeated work.

    Flow:
        cleanup(old data) → download → load → scan → news(scan_results) →
        enrich(scan_results, news) → output(enriched)
    """
    t0        = time()
    steps_log = []

    print(f"\n{'#'*56}")
    print(f"  NSE DAILY RUNNER")
    print(f"  Date    : {scan_date.strftime('%d-%b-%Y (%A)')}")
    print(f"  Mode    : {'DRY RUN — no Telegram' if dry_run else 'LIVE'}")
    print(f"  News    : {'SKIP' if skip_news else 'ON'}")
    print(f"  Keep    : {KEEP_HISTORICAL_DAYS} days of data")
    print(f"  Started : {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'#'*56}")

    # ── Holiday check ──
    if not is_trading_day(scan_date):
        last_td = get_last_trading_day(scan_date - timedelta(days=1))
        print(f"\n  {scan_date.strftime('%d-%b-%Y')} is not a trading day")
        print(f"  Using last trading day: {last_td.strftime('%d-%b-%Y')}")
        scan_date = last_td

    scan_results = None
    news_data    = {}

    # ── Step 0: Auto-cleanup (always run) ──
    ok, _, elapsed = run_step(0, "Auto-cleanup old data", step_cleanup)
    steps_log.append((0, "Auto-cleanup", ok, elapsed))
    if not ok:
        print("  ⚠️  Cleanup failed — continuing anyway")

    # ── Step 1: Download ──
    if not skip_download:
        ok, _, elapsed = run_step(1, "Download NSE files", step_download, scan_date)
        steps_log.append((1, "Download", ok, elapsed))
        if not ok:
            print("  Download failed — continuing with existing files")
    else:
        print(f"\n  Step 1: Download — SKIPPED")
        steps_log.append((1, "Download (skipped)", True, 0.0))

    # ── Step 2: Load ──
    ok, _, elapsed = run_step(2, "Load into database", step_load, scan_date)
    steps_log.append((2, "Load DB", ok, elapsed))
    if not ok:
        print("  DB load failed — cannot continue")
        print_summary(scan_date, steps_log, time() - t0)
        return False

    # ── Step 3: Scan ──
    ok, scan_results, elapsed = run_step(3, "Scan stocks", step_scan, scan_date)
    steps_log.append((3, "Scan", ok, elapsed))
    if not ok or scan_results is None or scan_results.empty:
        print("  Scan failed — cannot continue")
        print_summary(scan_date, steps_log, time() - t0)
        return False

    # ── Step 4: News (uses scan_results — NO re-scan) ──
    if not skip_news:
        ok, news_data, elapsed = run_step(
            4, "Collect news (shortlist only)",
            step_news, scan_results, scan_date
        )
        steps_log.append((4, "News", ok, elapsed))
        if not ok:
            news_data = {}
            print("  News collection failed — continuing without news")
    else:
        print(f"\n  Step 4: News — SKIPPED (--skip-news)")
        steps_log.append((4, "News (skipped)", True, 0.0))

    # ── Step 5: Enrich ──
    ok, enriched, elapsed = run_step(
        5, "Enrich with news flags",
        step_enrich, scan_results, news_data
    )
    steps_log.append((5, "Enrich", ok, elapsed))
    final_results = enriched if (ok and enriched is not None) else scan_results

    # ── Step 6: Output ──
    ok, _, elapsed = run_step(
        6, "Excel + Telegram",
        step_output, final_results, scan_date, dry_run
    )
    steps_log.append((6, "Output", ok, elapsed))

    # ── Summary ──
    print_summary(scan_date, steps_log, time() - t0)
    return True


# ─────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="NSE Daily Runner — full pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python nse_daily_runner.py
  python nse_daily_runner.py --dry-run
  python nse_daily_runner.py --skip-download
  python nse_daily_runner.py --skip-news
  python nse_daily_runner.py --date 05-03-2026
  python nse_daily_runner.py --dry-run --skip-download

Task Scheduler (Windows):
  Program : C:\\Users\\ratho\\nse-scanner\\venv\\Scripts\\python.exe
  Args    : C:\\Users\\ratho\\nse-scanner\\nse_daily_runner.py
  Start in: C:\\Users\\ratho\\nse-scanner
  Trigger : Weekdays 6:45 PM
        """
    )

    parser.add_argument("--date",          type=str,
                        help="Date DD-MM-YYYY (default: today)")
    parser.add_argument("--dry-run",       action="store_true",
                        help="Run all steps but skip Telegram send")
    parser.add_argument("--skip-download", action="store_true",
                        help="Skip download — use existing files")
    parser.add_argument("--skip-news",     action="store_true",
                        help="Skip news collection step")

    args = parser.parse_args()

    # Parse date
    if args.date:
        scan_date = None
        for fmt in ["%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"]:
            try:
                scan_date = datetime.strptime(args.date, fmt).date()
                break
            except ValueError:
                pass
        if not scan_date:
            print(f"Invalid date: {args.date}. Use DD-MM-YYYY")
            sys.exit(1)
    else:
        scan_date = get_last_trading_day()

    success = run_pipeline(
        scan_date      = scan_date,
        skip_download  = args.skip_download,
        skip_news      = args.skip_news,
        dry_run        = args.dry_run,
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
