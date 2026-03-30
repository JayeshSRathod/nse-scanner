"""
nse_loader.py — SQLite Database Loader
========================================
Scans nse_data/ folder -> validates files -> parses CSVs ->
loads into SQLite database -> optional cleanup of large files.

Database: nse_scanner.db
Tables:
    daily_prices, blacklist, index_perf, volatility, week52, pe_ratios, load_log
"""

import os, sys, glob, argparse, sqlite3, logging, shutil
from datetime import date, datetime, timedelta
import pandas as pd

try:
    from nse_parser import parse_all
except ImportError:
    print("ERROR: nse_parser.py not found. Place it in the same folder.")
    sys.exit(1)

SAVE_ROOT = "nse_data"
DB_PATH   = "nse_scanner.db"
LOG_DIR   = "logs"

DELETE_AFTER_LOAD = [
    "CMVOLT_*.CSV", "CMVOLT_*.csv",
    "MTO_*.DAT", "FCM_INTRM_BC*.DAT",
    "C_VAR1_*.DAT", "*.gz",
    "BhavCopy_*.zip", "Margintrdg_*.zip",
    "sme*.csv", "MF_VAR_*.csv",
    "MA*.csv", "CSQR_M_*.csv",
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
    ]
)
log = logging.getLogger(__name__)


def get_db(path=DB_PATH):
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=10000")
    return conn


def init_database(path=DB_PATH):
    conn = get_db(path)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS daily_prices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL, date DATE NOT NULL,
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
        prices_rows INTEGER DEFAULT 0, blacklist_rows INTEGER DEFAULT 0,
        index_rows INTEGER DEFAULT 0, vol_rows INTEGER DEFAULT 0,
        week52_rows INTEGER DEFAULT 0, pe_rows INTEGER DEFAULT 0,
        status TEXT DEFAULT 'ok', notes TEXT)""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_prices_symbol ON daily_prices(symbol)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_prices_date   ON daily_prices(date)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_bl_date       ON blacklist(date)")
    conn.commit()
    conn.close()
    log.info(f"Database ready: {path}")


def validate(name, data, trade_date):
    if data is None:
        return False, "file not found or parse error"
    count = len(data) if not isinstance(data, set) else len(data)
    if isinstance(data, set):
        return (count >= MIN_ROWS.get(name, 1)), f"{count} symbols"
    if not isinstance(data, pd.DataFrame) or data.empty:
        return False, "empty"
    if count < MIN_ROWS.get(name, 1):
        return False, f"only {count} rows (min {MIN_ROWS.get(name,1)})"
    needs = {"bhavdata":["symbol","close","date"], "ind_close":["index_name","close"],
             "volatility":["symbol","annual_vol"], "week52":["symbol","week52_high"],
             "pe":["symbol","pe_ratio"]}
    if name in needs:
        missing = [c for c in needs[name] if c not in data.columns]
        if missing:
            return False, f"missing columns: {missing}"
    if "close" in data.columns and data["close"].isna().mean() > 0.5:
        return False, "more than 50 percent null close prices"
    return True, f"{count} rows OK"


def _dedup(conn, table, key_cols):
    keys = ", ".join(key_cols)
    conn.execute(f"""DELETE FROM {table} WHERE id NOT IN (
        SELECT MIN(id) FROM {table} GROUP BY {keys})""")
    conn.commit()


def load_prices(conn, df, trade_date):
    df = df.copy()
    df["date"] = trade_date.isoformat()
    cols = [c for c in ["symbol","date","prev_close","open","high","low",
                         "last_price","close","avg_price","volume",
                         "turnover_lacs","trades","delivery_qty","delivery_pct"]
            if c in df.columns]
    before = conn.execute("SELECT COUNT(*) FROM daily_prices").fetchone()[0]
    df[cols].to_sql("daily_prices", conn, if_exists="append", index=False, chunksize=500)
    _dedup(conn, "daily_prices", ["symbol","date"])
    after = conn.execute("SELECT COUNT(*) FROM daily_prices").fetchone()[0]
    return after - before


def load_blacklist(conn, symbols, trade_date):
    rows = [(s, trade_date.isoformat()) for s in symbols]
    c = conn.cursor()
    c.executemany("INSERT OR IGNORE INTO blacklist(symbol,date) VALUES(?,?)", rows)
    conn.commit()
    return c.rowcount


def load_index(conn, df, trade_date):
    df = df.copy()
    if "date" not in df.columns or df["date"].isna().all():
        df["date"] = trade_date.isoformat()
    else:
        df["date"] = pd.to_datetime(df["date"]).dt.date.astype(str)
    cols = [c for c in ["index_name","date","open","high","low","close",
                         "change_pct","volume","pe","pb","div_yield"]
            if c in df.columns]
    before = conn.execute("SELECT COUNT(*) FROM index_perf").fetchone()[0]
    df[cols].to_sql("index_perf", conn, if_exists="append", index=False, chunksize=500)
    _dedup(conn, "index_perf", ["index_name","date"])
    after = conn.execute("SELECT COUNT(*) FROM index_perf").fetchone()[0]
    return after - before


def load_vol(conn, df, trade_date):
    df = df.copy()
    df["date"] = trade_date.isoformat()
    cols = [c for c in ["symbol","date","daily_vol","annual_vol"] if c in df.columns]
    before = conn.execute("SELECT COUNT(*) FROM volatility").fetchone()[0]
    df[cols].to_sql("volatility", conn, if_exists="append", index=False, chunksize=500)
    _dedup(conn, "volatility", ["symbol","date"])
    after = conn.execute("SELECT COUNT(*) FROM volatility").fetchone()[0]
    return after - before


def load_w52(conn, df, trade_date):
    df = df.copy()
    df["date"] = trade_date.isoformat()
    cols = [c for c in ["symbol","date","week52_high","week52_low"] if c in df.columns]
    before = conn.execute("SELECT COUNT(*) FROM week52").fetchone()[0]
    df[cols].to_sql("week52", conn, if_exists="append", index=False, chunksize=500)
    _dedup(conn, "week52", ["symbol","date"])
    after = conn.execute("SELECT COUNT(*) FROM week52").fetchone()[0]
    return after - before


def load_pe(conn, df, trade_date):
    df = df.copy()
    df["date"] = trade_date.isoformat()
    cols = [c for c in ["symbol","date","pe_ratio"] if c in df.columns]
    before = conn.execute("SELECT COUNT(*) FROM pe_ratios").fetchone()[0]
    df[cols].to_sql("pe_ratios", conn, if_exists="append", index=False, chunksize=500)
    _dedup(conn, "pe_ratios", ["symbol","date"])
    after = conn.execute("SELECT COUNT(*) FROM pe_ratios").fetchone()[0]
    return after - before


def cleanup_day(day_folder, dry_run=False):
    deleted = []
    for pattern in DELETE_AFTER_LOAD:
        for f in glob.glob(os.path.join(day_folder, pattern)):
            size_kb = os.path.getsize(f) / 1024
            if dry_run:
                print(f"   WOULD DELETE: {os.path.basename(f)}  ({size_kb:.0f} KB)")
            else:
                os.remove(f)
                deleted.append(f)
                log.info(f"Cleaned: {os.path.basename(f)} ({size_kb:.0f} KB)")
    return deleted


def load_day(trade_date, do_cleanup=False):
    fmt    = trade_date.strftime("%Y/%m/%d")
    folder = os.path.join(SAVE_ROOT, fmt)
    result = {"date": trade_date, "status": "ok", "rows": {}, "skipped": [], "errors": []}

    print(f"\n{'='*56}")
    print(f"  Loading: {trade_date.strftime('%d-%b-%Y')}  ({trade_date.strftime('%A')})")
    print(f"{'='*56}")

    if not os.path.exists(folder):
        print(f"  SKIP  Folder not found: {folder}")
        result["status"] = "skip"
        return result

    conn = get_db()
    already = conn.execute(
        "SELECT date FROM load_log WHERE date=? AND status='ok'",
        [trade_date.isoformat()]).fetchone()
    if already:
        print(f"  Already loaded -- skipping (use --force to reload)")
        conn.close()
        result["status"] = "already_loaded"
        return result

    parsed  = parse_all(folder, trade_date)
    notes   = []
    log_row = {
        "date": trade_date.isoformat(), "loaded_at": datetime.now().isoformat(),
        "prices_rows": 0, "blacklist_rows": 0, "index_rows": 0,
        "vol_rows": 0, "week52_rows": 0, "pe_rows": 0,
        "status": "ok", "notes": ""
    }

    # 1 -- Prices (REQUIRED)
    ok, reason = validate("bhavdata", parsed["bhavdata"], trade_date)
    if ok:
        n = load_prices(conn, parsed["bhavdata"], trade_date)
        log_row["prices_rows"] = n
        result["rows"]["prices"] = n
        print(f"  OK    daily_prices    : {n} rows inserted")
    else:
        msg = f"Prices FAILED: {reason}"
        print(f"  FAIL  daily_prices    : {reason}")
        result["errors"].append(msg)
        result["status"] = "partial"
        log_row["status"] = "partial"
        notes.append(msg)

    # 2 -- Blacklist (REQUIRED)
    ok, reason = validate("blacklist", parsed["blacklist"], trade_date)
    if ok:
        n = load_blacklist(conn, parsed["blacklist"], trade_date)
        log_row["blacklist_rows"] = len(parsed["blacklist"])
        result["rows"]["blacklist"] = n
        print(f"  OK    blacklist       : {len(parsed['blacklist'])} symbols ({n} new)")
    else:
        print(f"  SKIP  blacklist       : {reason}")
        result["skipped"].append("blacklist")
        notes.append(f"blacklist: {reason}")

    # 3 -- Index (REQUIRED)
    ok, reason = validate("ind_close", parsed["ind_close"], trade_date)
    if ok:
        n = load_index(conn, parsed["ind_close"], trade_date)
        log_row["index_rows"] = n
        result["rows"]["index_perf"] = n
        print(f"  OK    index_perf      : {n} indices inserted")
    else:
        print(f"  SKIP  index_perf      : {reason}")
        result["skipped"].append("index_perf")
        notes.append(f"index: {reason}")

    # 4 -- Volatility (OPTIONAL)
    ok, reason = validate("volatility", parsed["volatility"], trade_date)
    if ok:
        n = load_vol(conn, parsed["volatility"], trade_date)
        log_row["vol_rows"] = n
        result["rows"]["volatility"] = n
        print(f"  OK    volatility      : {n} rows inserted")
    else:
        print(f"  SKIP  volatility      : not available (add bundle ZIP)")

    # 5 -- 52W (OPTIONAL)
    ok, reason = validate("week52", parsed["week52"], trade_date)
    if ok:
        n = load_w52(conn, parsed["week52"], trade_date)
        log_row["week52_rows"] = n
        result["rows"]["week52"] = n
        print(f"  OK    week52          : {n} rows inserted")
    else:
        print(f"  SKIP  week52          : not available (add bundle ZIP)")

    # Week52 health check for category system
    w52_recent = conn.execute(
        "SELECT COUNT(*) FROM week52 WHERE date >= ?",
        [(trade_date - timedelta(days=7)).isoformat()]
    ).fetchone()[0]
    if w52_recent == 0:
        print(f"  ⚠️   week52 EMPTY — 'Close to Peak' category won't work")
        notes.append("week52 empty — peak category disabled")

    # 6 -- PE (OPTIONAL)
    ok, reason = validate("pe", parsed["pe"], trade_date)
    if ok:
        n = load_pe(conn, parsed["pe"], trade_date)
        log_row["pe_rows"] = n
        result["rows"]["pe"] = n
        print(f"  OK    pe_ratios       : {n} rows inserted")
    else:
        print(f"  SKIP  pe_ratios       : not available (add bundle ZIP)")

    log_row["notes"] = " | ".join(notes)
    conn.execute("""INSERT OR REPLACE INTO load_log
        (date,loaded_at,prices_rows,blacklist_rows,index_rows,
         vol_rows,week52_rows,pe_rows,status,notes)
        VALUES (:date,:loaded_at,:prices_rows,:blacklist_rows,:index_rows,
                :vol_rows,:week52_rows,:pe_rows,:status,:notes)""", log_row)
    conn.commit()
    conn.close()

    if do_cleanup and result["status"] != "skip":
        deleted = cleanup_day(folder)
        if deleted:
            print(f"  Cleanup: deleted {len(deleted)} large files")

    total = sum(result["rows"].values())
    print(f"  Summary: {total} rows | {len(result['skipped'])} skipped | status={result['status']}")
    log.info(f"Loaded {trade_date}: {total} rows, status={result['status']}")
    return result


def show_status():
    if not os.path.exists(DB_PATH):
        print(f"\n  Database not found: {DB_PATH}")
        return
    conn = get_db()
    size = os.path.getsize(DB_PATH) / 1024 / 1024
    print(f"\n{'='*56}\n  NSE Scanner Database Status\n  File: {os.path.abspath(DB_PATH)}\n  Size: {size:.1f} MB\n{'='*56}")
    for table in ["daily_prices","blacklist","index_perf","volatility","week52","pe_ratios"]:
        try:
            r = conn.execute(f"SELECT COUNT(*) as rows, COUNT(DISTINCT date) as days, MIN(date), MAX(date) FROM {table}").fetchone()
            print(f"  {table:<20} rows={r[0]:>7,}  days={r[1]:>3}  range={r[2] or 'n/a'} to {r[3] or 'n/a'}")
        except Exception:
            print(f"  {table:<20} -- not found")
    ll = conn.execute("SELECT status, COUNT(*) FROM load_log GROUP BY status").fetchall()
    if ll:
        print(f"\n  load_log: " + "  ".join(f"{s}={n}" for s,n in ll))
    conn.close()
    print(f"{'='*56}")


def find_all_day_folders():
    days = []
    for f in glob.glob(os.path.join(SAVE_ROOT, "*", "*", "*", "sec_bhavdata_full_*.csv")):
        parts = f.replace("\\", "/").split("/")
        try:
            days.append(date(int(parts[1]), int(parts[2]), int(parts[3])))
        except (IndexError, ValueError):
            pass
    return sorted(set(days))


def parse_date_arg(s):
    for fmt in ["%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"]:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    print(f"Invalid date: {s}. Use DD-MM-YYYY")
    sys.exit(1)


def main():
    p = argparse.ArgumentParser(description="NSE Loader -- load files into SQLite")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--date", type=str, help="Load one date DD-MM-YYYY")
    g.add_argument("--all", action="store_true", help="Load all downloaded dates")
    g.add_argument("--last", type=int, metavar="N", help="Load last N days")
    g.add_argument("--status", action="store_true", help="Show DB status")
    p.add_argument("--cleanup", action="store_true", help="Delete large files after loading")
    p.add_argument("--force", action="store_true", help="Reload already loaded dates")
    args = p.parse_args()

    init_database()

    if args.status:
        show_status()
        return
    if args.date:
        load_day(parse_date_arg(args.date), do_cleanup=args.cleanup)
        show_status()
        return
    if args.all:
        days = find_all_day_folders()
    else:
        today, days, d = date.today(), [], date.today()
        while len(days) < args.last:
            d -= timedelta(days=1)
            folder = os.path.join(SAVE_ROOT, d.strftime("%Y/%m/%d"))
            if os.path.exists(folder):
                days.append(d)

    if not days:
        print(f"\n  No downloaded data found in {SAVE_ROOT}/")
        return

    print(f"\n  Loading {len(days)} trading days...")
    ok_n = skip_n = fail_n = 0
    for i, d in enumerate(days):
        r = load_day(d, do_cleanup=args.cleanup)
        if r["status"] == "ok": ok_n += 1
        elif r["status"] in ("skip","already_loaded"): skip_n += 1
        else: fail_n += 1
        pct = (i+1) / len(days) * 100
        print(f"  Progress: {i+1}/{len(days)} ({pct:.0f}%) OK={ok_n} SKIP={skip_n} FAIL={fail_n}")

    print(f"\n  Done: OK={ok_n}  SKIP={skip_n}  FAIL={fail_n}")
    show_status()


if __name__ == "__main__":
    main()
