from telegram_dashboard import dashboard_keyboard, dashboard_url, status_label


def test_plain_language_status_contract():
    assert status_label("EARLY_RADAR") == "Early watchlist"
    assert status_label("CONFIRMING") == "Watchlist—wait for confirmation"
    assert status_label("READY") == "Watch for entry"
    assert status_label("NEW_TRIGGER") == "New paper entry"
    assert status_label("EXTENDED") == "Wait for pullback"
    assert status_label("CIRCUIT_LOCKED") == "No entry—circuit risk"
    assert status_label("WAIT") == "No action yet"


def test_dashboard_link_selects_scanner(monkeypatch):
    monkeypatch.delenv("NSE_MINI_APP_URL", raising=False)
    assert dashboard_url("ladder").endswith("?startapp=ladder")
    button = dashboard_keyboard("penny")["inline_keyboard"][0][0]
    assert button["url"].endswith("?startapp=penny")
    assert set(button) == {"text", "url"}
