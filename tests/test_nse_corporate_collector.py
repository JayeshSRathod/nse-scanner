import sqlite3

import pandas as pd

from nse_corporate_collector import (
    rebuild_caps_from_shares,
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


def test_historical_caps_never_use_future_shares(tmp_path):
    path = _db(tmp_path)
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT INTO daily_prices VALUES ('ABC','2026-07-01',100,101,99,100,200000)")
        conn.execute("INSERT INTO daily_prices VALUES ('ABC','2026-08-01',110,111,109,110,200000)")
        conn.execute("""INSERT INTO shares_outstanding_v3
          (symbol,as_of_date,available_date,shares_outstanding,source,filing_id)
          VALUES ('ABC','2026-06-30','2026-07-15',100000000,'NSE_SHAREHOLDING','OLD'),
                 ('ABC','2026-07-31','2026-08-02',200000000,'NSE_SHAREHOLDING','FUTURE')""")
        assert rebuild_caps_from_shares(conn, end_date="2026-08-01") == 1
        row = conn.execute("SELECT as_of_date,market_cap_cr,filing_id FROM market_cap_snapshots_v3").fetchone()
    assert row == ("2026-08-01", 1100.0, "OLD")
