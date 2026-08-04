from __future__ import annotations

from unittest.mock import Mock, patch

from v2.telegram_delivery import send_admin_messages, send_messages


def _ok_response() -> Mock:
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"ok": True}
    return response


def test_admin_delivery_uses_admin_chat_id(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "user-123")
    monkeypatch.setenv("ADMIN_CHAT_ID", "admin-456")
    with patch("v2.telegram_delivery.requests.post", return_value=_ok_response()) as post:
        result = send_admin_messages(["admin report"], enabled=True)
    assert result.sent is True
    assert result.message_count == 1
    assert post.call_args.kwargs["json"]["chat_id"] == "admin-456"


def test_user_delivery_remains_on_user_chat_id(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "user-123")
    monkeypatch.setenv("ADMIN_CHAT_ID", "admin-456")
    with patch("v2.telegram_delivery.requests.post", return_value=_ok_response()) as post:
        result = send_messages(["user report"], enabled=True)
    assert result.sent is True
    assert post.call_args.kwargs["json"]["chat_id"] == "user-123"


def test_missing_admin_chat_id_does_not_raise(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_TOKEN", "token")
    monkeypatch.delenv("ADMIN_CHAT_ID", raising=False)
    monkeypatch.delenv("V2_ADMIN_CHAT_ID", raising=False)
    result = send_admin_messages(["admin report"], enabled=True)
    assert result.sent is False
    assert result.reason == "admin_telegram_credentials_missing"


def test_admin_delivery_dry_run(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_TOKEN", "token")
    monkeypatch.setenv("ADMIN_CHAT_ID", "admin-456")
    result = send_admin_messages(["admin report"], enabled=False)
    assert result.sent is False
    assert result.reason == "dry_run"
