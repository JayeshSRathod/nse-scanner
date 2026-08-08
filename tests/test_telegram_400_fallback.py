from __future__ import annotations

from unittest.mock import Mock

from v2.telegram_delivery import send_messages


def _response(status: int, description: str = "") -> Mock:
    response = Mock()
    response.status_code = status
    response.text = description
    response.json.return_value = (
        {"ok": True, "result": {}} if status < 400
        else {"ok": False, "error_code": status, "description": description}
    )
    return response


def test_invalid_topic_retries_main_chat(monkeypatch):
    monkeypatch.setenv("TELEGRAM_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "-100123")
    post = Mock(side_effect=[
        _response(400, "Bad Request: message thread not found"),
        _response(200),
    ])
    monkeypatch.setattr("v2.telegram_delivery.requests.post", post)

    result = send_messages(["hello"], enabled=True, message_thread_id=999)

    assert result.sent
    assert result.message_count == 1
    assert post.call_count == 2
    assert "message_thread_id" in post.call_args_list[0].kwargs["json"]
    assert "message_thread_id" not in post.call_args_list[1].kwargs["json"]


def test_delivery_failure_does_not_raise(monkeypatch):
    monkeypatch.setenv("TELEGRAM_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "-100123")
    monkeypatch.setattr(
        "v2.telegram_delivery.requests.post",
        Mock(return_value=_response(400, "Bad Request: chat not found")),
    )

    result = send_messages(["hello"], enabled=True)

    assert not result.sent
    assert result.message_count == 0
    assert "chat not found" in result.reason


def test_action_keyboard_is_capped_below_telegram_100_button_limit(monkeypatch):
    monkeypatch.setenv("TELEGRAM_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "-100123")
    post = Mock(return_value=_response(200))
    monkeypatch.setattr("v2.telegram_delivery.requests.post", post)
    message = "ALL ACTIONABLE CANDIDATES\n" + "\n".join(
        f"{index}. STOCK{index}" for index in range(1, 61)
    )

    result = send_messages([message], enabled=True)

    assert result.sent
    keyboard = post.call_args.kwargs["json"]["reply_markup"]["inline_keyboard"]
    assert len(keyboard) == 30
    assert sum(len(row) for row in keyboard) == 90
    assert sum(len(row) for row in keyboard) < 100
