import pandas as pd

from old_nse_hull.discovery import discover
from old_nse_hull.engine import render_radar


def test_discovery_uses_momentum_shortlist_without_paper_entry():
    days = pd.bdate_range("2025-01-01", periods=70)
    rows = []
    for symbol, start in (("AAA", 100), ("BBB", 80)):
        for index, day in enumerate(days):
            rows.append({"symbol": symbol, "trade_date": day, "close": start + index * (2 if symbol == "AAA" else 1), "volume": 100_000})
    result = discover(pd.DataFrame(rows))
    assert result.shortlist.iloc[0]["symbol"] == "AAA"


def test_paper_radar_identifies_the_active_python_hull_rules():
    report = {"generated_at": "2026-08-19T06:00:00+05:30", "as_of_date": "2026-08-18", "eligible": 2,
              "discovery_qualified": 1, "ready": 0, "watch": 1, "shortlist": [{"symbol": "AAA", "discovery_score": 90.0}]}
    text = render_radar(report)
    assert "PAPER SYSTEM" in text
    assert "PYTHON EOD ACTIVE" in text
    assert "live-trading instruction" in text
    assert "Hull READY: 0" in text
