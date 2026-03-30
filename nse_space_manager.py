"""
nse_space_manager.py — Intelligent Space Manager
=================================================
Keeps your project lean by removing redundant data.

Philosophy:
  SQLite DB   = source of truth  → keep 180 days (managed by auto_cleanup)
  Raw CSVs    = staging only     → delete after 7 days (already loaded into DB)
  Logs        = rolling window   → keep 30 days, trim large files
  Excel       = today only       → keep latest 1 file
  News JSON   = short-lived      → keep 7 days

Usage:
    python nse_space_manager.py           # dry run — shows what WOULD be deleted
    python nse_space_manager.py --clean   # actually delete
    python nse_space_manager.py --status  # disk usage only

Integrated into nse_daily_runner.py Step 0 automatically.
"""

import os
import sys
import argparse
from datetime import datetime, timedelta, date
from pathlib import Path

try:
    import config
except ImportError:
    print("ERROR: config.py not found.")
    sys.exit(1)

_HERE = Path(__file__).parent

# ── Read paths from config — supports both key names ─────────
_DATA_DIR_NAME = (getattr(config, "NSE_DATA_DIR", None) or
                  getattr(config, "DATA_DIR",     "nse_data"))
DATA_DIR   = _HERE / _DATA_DIR_NAME
OUTPUT_DIR = _HERE / getattr(config, "OUTPUT_DIR", "output")
LOG_DIR    = _HERE / getattr(config, "LOG_DIR",    "logs")
DB_PATH    = _HERE / getattr(config, "DB_PATH",    "nse_scanner.db")

# ── Tunable retention settings ────────────────────────────────
KEEP_CSV_DAYS  = 7    # Raw CSVs older than this are deleted (in SQLite already)
KEEP_LOG_DAYS  = 30   # Log files rolling window
KEEP_EXCEL     = 1    # Keep only latest N Excel files
KEEP_NEWS_DAYS = 7    # News JSON files
"""
nse_space_manager.py — 1 EDIT
================================
INSTRUCTION: Find the line:
    KEEP_NEWS_DAYS = 7

ADD these lines RIGHT AFTER it:
"""

# ── Files that must NEVER be cleaned (NEW) ────────────────────
NEVER_DELETE = {
    "scan_history.json",        # streak calculation needs 30 days
    "telegram_last_scan.json",  # bot pagination data
    "scan_health.json",         # pipeline health monitoring
    "nse_scanner.db",           # all historical price data
}

# Then in clean_old_csvs(), ADD this check at the start of the loop:
#
#   for f in sorted(DATA_DIR.rglob("*")):
#       if not f.is_file():
#           continue
#       if f.name in NEVER_DELETE:    # <── ADD THIS LINE
#           continue                   # <── ADD THIS LINE
#       ... rest of existing code ...

# ── Helpers ───────────────────────────────────────────────────

def _size_mb(path: Path) -> float:
    if not path.exists():
        return 0.0
    if path.is_file():
        return path.stat().st_size / 1_048_576
    return sum(f.stat().st_size
               for f in path.rglob("*") if f.is_file()) / 1_048_576


def _age_days(path: Path) -> int:
    return (datetime.now() -
            datetime.fromtimestamp(path.stat().st_mtime)).days


# ══════════════════════════════════════════════════════════════
# STATUS
# ══════════════════════════════════════════════════════════════

def show_status():
    """Print disk usage for all project folders."""
    print("\n" + "="*55)
    print("  NSE SCANNER — DISK USAGE")
    print("="*55)

    items = [
        ("SQLite DB",       DB_PATH),
        (f"Raw CSVs ({_DATA_DIR_NAME}/)", DATA_DIR),
        ("Excel output",    OUTPUT_DIR),
        ("Logs",            LOG_DIR),
        ("Pagination JSON", _HERE / "telegram_last_scan.json"),
    ]

    total = 0.0
    for label, path in items:
        size   = _size_mb(path)
        total += size
        mark   = "✅" if path.exists() else "⚠️ "
        print(f"  {mark}  {label:<28} {size:>7.1f} MB")

    # CSV breakdown
    if DATA_DIR.exists():
        csvs = list(DATA_DIR.rglob("*.csv"))
        print(f"\n  CSV files   : {len(csvs)} files")
        if csvs:
            newest = max(csvs, key=lambda f: f.stat().st_mtime)
            oldest = min(csvs, key=lambda f: f.stat().st_mtime)
            print(f"  Newest CSV  : {newest.name}  ({_age_days(newest)}d old)")
            print(f"  Oldest CSV  : {oldest.name}  ({_age_days(oldest)}d old)")

            old_count = sum(1 for f in csvs if _age_days(f) > KEEP_CSV_DAYS)
            if old_count:
                old_mb = sum(f.stat().st_size for f in csvs
                             if _age_days(f) > KEEP_CSV_DAYS) / 1_048_576
                print(f"\n  ⚠️  {old_count} CSVs older than {KEEP_CSV_DAYS} days "
                      f"({old_mb:.1f}MB) — already in SQLite, safe to delete")
                print(f"     Run: python nse_space_manager.py --clean")

    # Excel breakdown
    if OUTPUT_DIR.exists():
        xlsx = sorted(OUTPUT_DIR.glob("NSE_Scanner_*.xlsx"),
                      key=lambda f: f.stat().st_mtime, reverse=True)
        if xlsx:
            print(f"\n  Excel files : {len(xlsx)} file(s)")
            for xf in xlsx:
                print(f"    {xf.name}  ({_age_days(xf)}d old)")

    print(f"\n  {'─'*40}")
    print(f"  Total project data : {total:>7.1f} MB")
    print("="*55)


# ══════════════════════════════════════════════════════════════
# CLEANUP FUNCTIONS
# ══════════════════════════════════════════════════════════════

def clean_old_csvs(dry_run: bool = True):
    """Delete raw NSE CSVs older than KEEP_CSV_DAYS."""
    if not DATA_DIR.exists():
        return 0, 0.0, 0

    cutoff   = datetime.now() - timedelta(days=KEEP_CSV_DAYS)
    deleted  = 0
    freed    = 0.0
    kept     = 0

    for f in sorted(DATA_DIR.rglob("*.csv")):
        mtime = datetime.fromtimestamp(f.stat().st_mtime)
        size  = f.stat().st_size / 1_048_576
        if mtime < cutoff:
            if dry_run:
                print(f"    [WOULD DELETE] {f.name}  {size:.2f}MB  ({_age_days(f)}d old)")
            else:
                f.unlink()
                print(f"    [DELETED] {f.name}  {size:.2f}MB")
            deleted += 1
            freed   += size
        else:
            kept += 1

    # Remove now-empty year/month folders
    if not dry_run:
        for folder in sorted(DATA_DIR.rglob("*"), reverse=True):
            if folder.is_dir():
                try:
                    folder.rmdir()
                except OSError:
                    pass

    return deleted, freed, kept


def clean_old_logs(dry_run: bool = True):
    """Delete old log files and trim large active ones."""
    if not LOG_DIR.exists():
        return 0, 0.0

    cutoff   = datetime.now() - timedelta(days=KEEP_LOG_DAYS)
    deleted  = 0
    freed    = 0.0

    # Delete old log files
    for f in LOG_DIR.rglob("*.log"):
        mtime = datetime.fromtimestamp(f.stat().st_mtime)
        size  = f.stat().st_size / 1_048_576
        if mtime < cutoff:
            if dry_run:
                print(f"    [WOULD DELETE] {f.name}  {size:.2f}MB  ({_age_days(f)}d old)")
            else:
                f.unlink()
                print(f"    [DELETED] {f.name}  {size:.2f}MB")
            deleted += 1
            freed   += size

    # Trim large active log files — keep last 1000 lines
    for f in LOG_DIR.glob("*.log"):
        if not f.exists():
            continue
        size = f.stat().st_size / 1_048_576
        if size > 5:
            if dry_run:
                print(f"    [WOULD TRIM]  {f.name}  {size:.1f}MB → keep last 1000 lines")
            else:
                lines    = f.read_text(encoding="utf-8", errors="ignore").splitlines()
                f.write_text("\n".join(lines[-1000:]) + "\n", encoding="utf-8")
                new_size = f.stat().st_size / 1_048_576
                saved    = size - new_size
                freed   += saved
                print(f"    [TRIMMED] {f.name}  {size:.1f}MB → {new_size:.1f}MB  "
                      f"(saved {saved:.1f}MB)")

    return deleted, freed


def clean_old_excel(dry_run: bool = True):
    """Keep only latest KEEP_EXCEL Excel files."""
    if not OUTPUT_DIR.exists():
        return 0, 0.0

    files    = sorted(OUTPUT_DIR.glob("NSE_Scanner_*.xlsx"),
                      key=lambda f: f.stat().st_mtime, reverse=True)
    to_del   = files[KEEP_EXCEL:]
    deleted  = 0
    freed    = 0.0

    for f in to_del:
        size = f.stat().st_size / 1_048_576
        if dry_run:
            print(f"    [WOULD DELETE] {f.name}  {size:.2f}MB")
        else:
            f.unlink()
            print(f"    [DELETED] {f.name}  {size:.2f}MB")
        deleted += 1
        freed   += size

    return deleted, freed


def clean_old_news(dry_run: bool = True):
    """Delete news JSON files older than KEEP_NEWS_DAYS."""
    if not OUTPUT_DIR.exists():
        return 0, 0.0

    cutoff   = datetime.now() - timedelta(days=KEEP_NEWS_DAYS)
    deleted  = 0
    freed    = 0.0

    for f in OUTPUT_DIR.glob("news_*.json"):
        mtime = datetime.fromtimestamp(f.stat().st_mtime)
        size  = f.stat().st_size / 1_048_576
        if mtime < cutoff:
            if dry_run:
                print(f"    [WOULD DELETE] {f.name}  {size:.2f}MB")
            else:
                f.unlink()
                print(f"    [DELETED] {f.name}  {size:.2f}MB")
            deleted += 1
            freed   += size

    return deleted, freed


# ══════════════════════════════════════════════════════════════
# MAIN RUNNER
# ══════════════════════════════════════════════════════════════

def run_cleanup(dry_run: bool = True) -> dict:
    """
    Run all cleanup tasks.
    Returns summary dict — used when called from nse_daily_runner.py.
    """
    mode = "DRY RUN — nothing deleted" if dry_run else "LIVE CLEANUP"
    print(f"\n{'='*55}")
    print(f"  NSE SPACE MANAGER — {mode}")
    print(f"  {date.today().strftime('%d-%b-%Y')}")
    print(f"{'='*55}")

    before = (_size_mb(DATA_DIR) + _size_mb(OUTPUT_DIR) + _size_mb(LOG_DIR))

    total_del  = 0
    total_free = 0.0

    # 1. Raw CSVs
    print(f"\n[1] Raw NSE CSVs  (keep {KEEP_CSV_DAYS} days — rest already in SQLite)")
    d, f, kept = clean_old_csvs(dry_run)
    print(f"    → {d} files  |  {f:.1f}MB  |  {kept} files kept")
    total_del  += d;  total_free += f

    # 2. Logs
    print(f"\n[2] Logs  (keep {KEEP_LOG_DAYS} days, trim >5MB files)")
    d, f = clean_old_logs(dry_run)
    print(f"    → {d} files deleted  |  {f:.1f}MB freed")
    total_del  += d;  total_free += f

    # 3. Excel
    print(f"\n[3] Excel reports  (keep latest {KEEP_EXCEL})")
    d, f = clean_old_excel(dry_run)
    print(f"    → {d} files deleted  |  {f:.1f}MB freed")
    total_del  += d;  total_free += f

    # 4. News JSON
    print(f"\n[4] News JSON  (keep {KEEP_NEWS_DAYS} days)")
    d, f = clean_old_news(dry_run)
    print(f"    → {d} files deleted  |  {f:.1f}MB freed")
    total_del  += d;  total_free += f

    # Summary
    print(f"\n{'─'*55}")
    print(f"  Total : {total_del} files  |  {total_free:.1f} MB freed")

    if not dry_run and total_del > 0:
        after = (_size_mb(DATA_DIR) + _size_mb(OUTPUT_DIR) + _size_mb(LOG_DIR))
        print(f"  Before: {before:.1f}MB  →  After: {after:.1f}MB  "
              f"(saved {before-after:.1f}MB)")
    elif dry_run and total_del > 0:
        print(f"\n  Run with --clean to actually free {total_free:.1f}MB:")
        print(f"  python nse_space_manager.py --clean")
    else:
        print("  ✅ Nothing to clean — project is already lean")

    print(f"{'='*55}\n")

    return {
        "files_deleted": total_del,
        "mb_freed":      round(total_free, 2),
        "dry_run":       dry_run,
    }


def main():
    parser = argparse.ArgumentParser(
        description="NSE Scanner Space Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python nse_space_manager.py            # dry run preview
  python nse_space_manager.py --clean    # actually delete
  python nse_space_manager.py --status   # disk usage only
        """
    )
    parser.add_argument("--clean",  action="store_true",
                        help="Actually delete files (default: dry run)")
    parser.add_argument("--status", action="store_true",
                        help="Show disk usage only, no cleanup")
    args = parser.parse_args()

    show_status()

    if args.status:
        return
    elif args.clean:
        run_cleanup(dry_run=False)
    else:
        run_cleanup(dry_run=True)


if __name__ == "__main__":
    main()
