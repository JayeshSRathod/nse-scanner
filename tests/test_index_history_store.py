import sqlite3

from nse_market_store import export_index_history


def test_export_index_history(tmp_path, monkeypatch):
    db = tmp_path / "index.db"
    with sqlite3.connect(db) as conn:
        conn.execute("""CREATE TABLE index_perf (
          id INTEGER PRIMARY KEY,index_name TEXT,date TEXT,open REAL,high REAL,
          low REAL,close REAL,UNIQUE(index_name,date))""")
        conn.execute("INSERT INTO index_perf(index_name,date,open,high,low,close) VALUES ('NIFTY 50','2026-08-17',100,102,99,101)")
    target = tmp_path / "index_history.csv"
    monkeypatch.setattr("nse_market_store.INDEX_HISTORY_PATH", target)
    assert export_index_history(db) == 1
    assert target.exists()
