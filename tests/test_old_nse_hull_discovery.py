import pandas as pd
from unittest.mock import Mock, patch

from old_nse_hull.delivery import send_radar, send_trades
from old_nse_hull.discovery import discover
from old_nse_hull.engine import render_paper_trades, render_radar


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


def test_old_hull_delivery_uses_its_own_optional_topic(monkeypatch):
    monkeypatch.setenv("TELEGRAM_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "group-123")
    monkeypatch.setenv("TELEGRAM_OLD_HULL_DAILY_TOPIC_ID", "88")
    response = Mock()
    response.raise_for_status.return_value = None
    with patch("old_nse_hull.delivery.requests.post", return_value=response) as post:
        result = send_radar("<b>PAPER SYSTEM</b>")
    assert result.sent
    assert post.call_args.kwargs["json"]["message_thread_id"] == 88


def test_replacement_uses_retired_pine_portfolio_topic(monkeypatch):
    monkeypatch.setenv("TELEGRAM_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "group-123")
    monkeypatch.setenv("TELEGRAM_PINE_PORTFOLIO_TOPIC_ID", "99")
    response = Mock()
    response.raise_for_status.return_value = None
    with patch("old_nse_hull.delivery.requests.post", return_value=response) as post:
        result = send_trades("<b>PAPER</b>")
    assert result.sent
    assert post.call_args.kwargs["json"]["message_thread_id"] == 99


def test_paper_trade_topic_never_treats_ready_as_entered():
    report = {"as_of_date": "2026-08-18", "shortlist": [{"symbol": "AAA", "discovery_score": 90.0,
              "discovery_rank": 1, "hull_state": "READY"}]}
    text = render_paper_trades(report)
    assert "READY — NOT ENTERED" in text
    assert "same closing price" in text
