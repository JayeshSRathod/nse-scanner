import sqlite3

import pandas as pd

from nse_corporate_collector import (
    calculate_caps_from_shares,
    ingest_equity_master,
    ingest_market_caps,
    refresh_current_market_cap,
)
from v2.database import V2Database


def _db(tmp_path):
    path = tmp_path / "collector.db"
    sqlite3.connect(path).close()
    V2Database(path).ensure_v3_schema()
    with sqlite3.connect(path) as conn:
        conn.execute("""CREATE TABLE daily_prices (
          symbol TEXT,date TEXT,open REAL,high REAL,low REAL,close REAL,volume INTEGER)""")
    return path


def test_universe_and_direct_market_cap(tmp_path):
    path = _db(tmp_path)
    master = pd.DataFrame({"SYMBOL": ["ABC"], "NAME OF COMPANY": ["ABC Ltd"],
                           "SERIES": ["EQ"], "ISIN NUMBER": ["INE000A"],
                           "DATE OF LISTING": ["01-Jan-2000"]})
    caps = pd.DataFrame({"SYMBOL": ["ABC"], "MARKET_CAP_CR": [2500]})
    with sqlite3.connect(path) as conn:
        assert ingest_equity_master(conn, master) == 1
        assert ingest_market_caps(conn, caps, "2026-08-17") == 1
        assert refresh_current_market_cap(conn, "2026-08-17") == 1
        row = conn.execute("SELECT market_cap_cr,market_cap_source FROM symbol_master_v2 WHERE symbol='ABC'").fetchone()
    assert row == (2500.0, "NSE_DIRECT_MARKET_CAP")


def test_calculated_cap_uses_only_available_shares(tmp_path):
    path = _db(tmp_path)
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT INTO symbol_master_v2(symbol,series) VALUES ('ABC','EQ')")
        conn.execute("INSERT INTO daily_prices VALUES ('ABC','2026-08-17',100,101,99,100,200000)")
        conn.execute("""INSERT INTO shares_outstanding_v3
          (symbol,as_of_date,available_date,shares_outstanding,source)
          VALUES ('ABC','2026-06-30','2026-07-20',100000000,'NSE_SHAREHOLDING')""")
        assert calculate_caps_from_shares(conn, "2026-08-17") == 1
        cap = conn.execute("SELECT market_cap_cr FROM market_cap_snapshots_v3 WHERE symbol='ABC'").fetchone()[0]
    assert cap == 1000.0
