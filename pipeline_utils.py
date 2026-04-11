# pipeline_utils.py — DB health + backfill helpers

import sqlite3
from pathlib import Path
from datetime import timedelta
from main_pipeline import is_trading_day  # reuse holiday logic

def db_has_enough_data(min_days=180):
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

def backfill_historical_data(target_date, days_back=180):
    """
    Download and load historical data when DB is empty.
    Downloads N trading days of data from NSE archives.
    """
    print(f"[BACKFILL] Loading {days_back} trading days...")
    from nse_historical_downloader import download_direct
    from nse_loader import init_database, load_day

    init_database()
    start_date = target_date - timedelta(days=int(days_back * 1.5))
    trading_days = []
    d = start_date
    while d <= target_date:
        if is_trading_day(d):
            trading_days.append(d)
        d += timedelta(days=1)
    trading_days = trading_days[-days_back:]

    loaded = 0
    for d in trading_days:
        try:
            download_direct(d)
            result = load_day(d, do_cleanup=False)
            if result.get("status") == "ok":
                loaded += 1
        except Exception as e:
            print(f"[BACKFILL] ❌ {d}: {e}")
    print(f"[BACKFILL] Done. Loaded {loaded} days.")
    return loaded >= min_days
