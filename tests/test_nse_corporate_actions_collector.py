import sqlite3
from datetime import date

from nse_corporate_actions_collector import collect, normalize_listing


def test_normalize_listing_creates_stable_material_record():
    rows = normalize_listing([{
        "symbol": "ABC", "exDate": "20-Aug-2026", "subject": "Bonus issue 1:1",
        "caBroadcastDate": "15-Aug-2026",
    }], "https://www.nseindia.com/api/corporates-corporateActions")
    assert rows[0]["symbol"] == "ABC"
    assert rows[0]["ex_date"] == "2026-08-20"
    assert rows[0]["available_date"] == "2026-08-15"
    assert rows[0]["material"] is True
    assert len(rows[0]["filing_id"]) == 32


def test_collect_keeps_database_on_listing_failure(tmp_path, monkeypatch):
    db = tmp_path / "actions.db"
    with sqlite3.connect(db) as conn:
        from v2.database import V2Database
        V2Database(db).ensure_v3_schema()
        conn.execute("""INSERT INTO corporate_actions_v3
          (symbol,ex_date,available_date,action_type,source) VALUES
          ('OLD','2026-08-01','2026-07-30','Split','NSE')""")
    monkeypatch.setattr("nse_corporate_actions_collector.fetch_listing", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("blocked")))
    health = collect(db, date(2026, 8, 17))
    assert health.status == "REUSED_LAST_VALID"
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM corporate_actions_v3").fetchone()[0] == 1
