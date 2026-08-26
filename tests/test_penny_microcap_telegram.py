from unittest.mock import patch

from penny_microcap.telegram import send_messages


class Response:
    def raise_for_status(self):
        return None


def test_dedicated_penny_route(monkeypatch):
    monkeypatch.setenv("PENNY_TELEGRAM_BOT_TOKEN", "penny-token")
    monkeypatch.setenv("PENNY_TELEGRAM_CHAT_ID", "-100444")
    monkeypatch.setenv("PENNY_DAILY_TOPIC_ID", "601")
    with patch("penny_microcap.telegram.requests.post", return_value=Response()) as post:
        result = send_messages(["hello"], "daily", enabled=True)
    assert result.sent
    assert post.call_args.args[0] == "https://api.telegram.org/botpenny-token/sendMessage"
    assert post.call_args.kwargs["json"]["chat_id"] == "-100444"
    assert post.call_args.kwargs["json"]["message_thread_id"] == 601


def test_missing_penny_secrets_fail_closed(monkeypatch):
    for name in ("PENNY_TELEGRAM_BOT_TOKEN", "PENNY_TELEGRAM_CHAT_ID", "PENNY_RISK_TOPIC_ID"):
        monkeypatch.delenv(name, raising=False)
    assert send_messages(["hello"], "risk", enabled=True).reason == "telegram_not_configured"
