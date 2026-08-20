from unittest.mock import Mock, patch

from old_nse_hull.delivery import send_radar
from pine_hull.telegram import send_signals
from v2.telegram_delivery import send_messages


def _response():
    response = Mock()
    response.status_code = 200
    response.json.return_value = {"ok": True}
    response.raise_for_status.return_value = None
    return response


def test_v3_ignores_generic_and_other_bot_credentials(monkeypatch):
    monkeypatch.delenv("V3_TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("V3_TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.setenv("TELEGRAM_TOKEN", "legacy")
    monkeypatch.setenv("LADDER_TELEGRAM_BOT_TOKEN", "ladder")
    assert send_messages(["test"], enabled=True).reason == "telegram_credentials_missing"


def test_ladder_uses_only_ladder_endpoint_and_topic(monkeypatch):
    monkeypatch.setenv("LADDER_TELEGRAM_BOT_TOKEN", "ladder-token")
    monkeypatch.setenv("LADDER_TELEGRAM_CHAT_ID", "ladder-chat")
    monkeypatch.setenv("LADDER_DAILY_TOPIC_ID", "101")
    with patch("old_nse_hull.delivery.requests.post", return_value=_response()) as post:
        result = send_radar("ladder")
    assert result.sent
    assert "botladder-token" in post.call_args.args[0]
    assert post.call_args.kwargs["json"]["message_thread_id"] == 101


def test_hull_uses_only_hull_endpoint_and_topic(monkeypatch):
    monkeypatch.setenv("HULL_TELEGRAM_BOT_TOKEN", "hull-token")
    monkeypatch.setenv("HULL_TELEGRAM_CHAT_ID", "hull-chat")
    monkeypatch.setenv("HULL_DAILY_TOPIC_ID", "202")
    with patch("pine_hull.telegram.requests.post", return_value=_response()) as post:
        result = send_signals(["hull"], enabled=True)
    assert result.sent
    assert "bothull-token" in post.call_args.args[0]
    assert post.call_args.kwargs["json"]["message_thread_id"] == 202
