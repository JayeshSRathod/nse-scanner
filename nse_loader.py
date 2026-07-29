"""
nse_loader.py — SQLite Database Loader (V2 data-foundation baseline)
===================================================================

The V2 scanner preserves a rolling 420-session historical base. This supports
200-day trend references, 252-session returns, weekly indicators, volatility
percentiles, and migration/backtest validation without repeatedly downloading
full history.

Daily operation is incremental: load missing completed sessions, upsert by
(symbol, date), and trim only when history exceeds the configured retention.
"""

import os, sys, glob, argparse, sqlite3, logging, shutil
from datetime import date, datetime, timedelta
import pandas as pd

try:
    from nse_parser import parse_all
except ImportError:
    print("ERROR: nse_parser.py not found.")
    sys.exit(1)

SAVE_ROOT = "nse_data"
DB_PATH = "nse_scanner.db"
LOG_DIR = "logs"
KEEP_DAYS = int(os.environ.get("NSE_HISTORY_RETENTION_DAYS", "420"))

DELETE_AFTER_LOAD = [
    "CMVOLT_*.CSV", "CMVOLT_*.csv", "MTO_*.DAT", "FCM_INTRM_BC*.DAT",
    "C_VAR1_*.DAT", "*.gz", "BhavCopy_*.zip", "Margintrdg_*.zip",
    "sme*.csv", "MF_VAR_*.csv", "MA*.csv", "CSQR_M_*.csv",
]

MIN_ROWS = {
    "bhavdata": 1000, "blacklist": 10, "ind_close": 100,
    "volatility": 100, "week52": 100, "pe": 100,
}

os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "loader.log"), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


def get_db(path=DB_PATH):
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=10000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_database(path=DB_PATH):
    conn = get_db(path)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS daily_prices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        date DATE NOT NULL,
        prev_close REAL, open REAL, high REAL, low REAL,
        last_price REAL, close REAL NOT NULL,
        avg_price REAL, volume INTEGER,
        turnover_lacs REAL, trades INTEGER,
        delivery_qty INTEGER, delivery_pct REAL,
        UNIQUE(symbol, date))""")
    c.execute("""CREATE TABLE IF NOT EXISTS blacklist (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL, date DATE NOT NULL,
        UNIQUE(symbol, date))""")
    c.execute("""CREATE TABLE IF NOT EXISTS index_perf (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        index_name TEXT NOT NULL, date DATE NOT NULL,
        open REAL, high REAL, low REAL, close REAL,
        change_pct REAL, volume INTEGER,
        pe REAL, pb REAL, div_yield REAL,
        UNIQUE(index_name, date))""")
    c.execute("""CREATE TABLE IF NOT EXISTS volatility (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL, date DATE NOT NULL,
        daily_vol REAL, annual_vol REAL,
        UNIQUE(symbol, date))""")
    c.execute("""CREATE TABLE IF NOT EXISTS week52 (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL, date DATE NOT NULL,
        week52_high REAL, week52_low REAL,
        UNIQUE(symbol, date))""")
    c.execute("""CREATE TABLE IF NOT EXISTS pe_ratios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL, date DATE NOT NULL,
        pe_ratio REAL,
        UNIQUE(symbol, date))""")
    c.execute("""CREATE TABLE IF NOT EXISTS load_log (
        date DATE PRIMARY KEY, loaded_at TEXT,
        prices_rows INTEGER DEFAULT 0,
        blacklist_rows INTEGER DEFAULT 0,
        index_rows INTEGER DEFAULT 0,
        vol_rows INTEGER DEFAULT 0,
        week52_rows INTEGER DEFAULT 0,
        pe_rows INTEGER DEFAULT 0,
        status TEXT DEFAULT 'ok', notes TEXT)""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_prices_symbol ON daily_prices(symbol)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_prices_date ON daily_prices(date)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_prices_symbol_date ON daily_prices(symbol, date)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_bl_date ON blacklist(date)")
    conn.commit()
    conn.close()
    log.info("Database ready: %s", path)


def get_loaded_date_range(path=DB_PATH):
    if not os.path.exists(path):
        return None, None, 0
    try:
        conn = get_db(path)
        row = conn.execute(
            "SELECT MIN(date), MAX(date), COUNT(DISTINCT date) FROM daily_prices"
        ).fetchone()
        conn.close()
        return (row[0], row[1], row[2]) if row and row[0] else (None, None, 0)
    except Exception as exc:
        log.error("get_loaded_date_range error: %s", exc)
        return None, None, 0


def delete_oldest_day(path=DB_PATH, dry_run=False):
    oldest, _, _ = get_loaded_date_range(path)
    if not oldest:
        return None
    if dry_run:
        log.info("[DRY RUN] Would delete oldest day: %s", oldest)
        return oldest
    conn = get_db(path)
    tables = [
        "daily_prices", "blacklist", "index_perf", "volatility",
        "week52", "pe_ratios", "load_log",
    ]
    total_deleted = 0
    try:
        for table in tables:
            try:
                cur = conn.execute(f"DELETE FROM {table} WHERE date = ?", [oldest])
                total_deleted += cur.rowcount
            except sqlite3.OperationalError:
                continue
        conn.commit()
    finally:
        conn.close()
    log.info("Deleted oldest day %s (%s rows)", oldest, total_deleted)
    return oldest


def trim_to_retention_days(keep_days=KEEP_DAYS, path=DB_PATH, dry_run=False):
    """Retain the newest `keep_days` distinct sessions and remove older dates."""
    oldest, newest, count = get_loaded_date_range(path)
    log.info("Retention check: %s days (%s to %s), target=%s", count, oldest, newest, keep_days)
    deleted = 0
    while count > keep_days:
        if not delete_oldest_day(path=path, dry_run=dry_run):
            break
        deleted += 1
        if dry_run:
            count -= 1
        else:
            _, _, count = get_loaded_date_range(path)
    return deleted


# Backward-compatible alias while legacy callers are migrated.
def trim_to_180_days(keep_days=KEEP_DAYS, path=DB_PATH, dry_run=False):
    return trim_to_retention_days(keep_days=keep_days, path=path, dry_run=dry_run)
