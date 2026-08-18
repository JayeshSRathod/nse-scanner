import sqlite3

from scripts.v3_operational_readiness import audit
from v2.database import V2Database


def test_gate_blocks_missing_index_and_market_cap(tmp_path):
    db = tmp_path / "readiness.db"
    sqlite3.connect(db).close()
    V2Database(db).ensure_v3_schema()
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE daily_prices(symbol TEXT,date TEXT)")
        conn.executemany("INSERT INTO daily_prices VALUES ('ABC',?)", [(f"2026-01-{i:02d}",) for i in range(1, 10)])
    report = audit(str(db))
    assert report.status == "BLOCKED"
    assert "official_index_sessions_below_required" in report.blockers
    assert "market_cap_coverage_below_80_percent" in report.blockers


def test_gate_handles_empty_database(tmp_path):
    db = tmp_path / "empty.db"
    sqlite3.connect(db).close()
    report = audit(str(db))
    assert report.status == "BLOCKED"
    assert report.blockers == ("price_table_missing",)
