import sqlite3

import nse_market_store


def test_blacklist_snapshot_is_exported_for_read_only_downstream_scanners(tmp_path, monkeypatch):
    monkeypatch.setattr(nse_market_store, "STORE_ROOT", tmp_path / "market_data")
    monkeypatch.setattr(nse_market_store, "BLACKLIST_PATH", tmp_path / "market_data" / "blacklist.csv")
    db_path = tmp_path / "scanner.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE blacklist (symbol TEXT, date TEXT, UNIQUE(symbol, date))")
        conn.execute("INSERT INTO blacklist VALUES ('ABC', '2026-08-20')")
    assert nse_market_store.export_blacklist_snapshot(db_path) == 1
    assert nse_market_store.BLACKLIST_PATH.read_text(encoding="utf-8").splitlines() == ["symbol,date", "ABC,2026-08-20"]
