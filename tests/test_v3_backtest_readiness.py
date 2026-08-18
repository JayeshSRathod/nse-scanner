import sqlite3

from scripts.v3_backtest_readiness import audit


def test_readiness_fails_closed_without_price_table(tmp_path):
    db = tmp_path / "empty.db"
    sqlite3.connect(db).close()
    report = audit(str(db))
    assert report.status == "BLOCKED"
    assert "price_table_missing" in report.blockers
