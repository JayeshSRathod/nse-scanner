"""Telegram delivery adapters for user and admin MIS reports."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from urllib.parse import quote

import requests


@dataclass(frozen=True)
class DeliveryResult:
    sent: bool
    message_count: int
    reason: str


def _token() -> str | None:
    value = os.getenv("V2_TELEGRAM_TOKEN") or os.getenv("TELEGRAM_TOKEN")
    return value.strip() if value else None


def _user_chat_id() -> str | None:
    value = (
        os.getenv("V2_TELEGRAM_CHAT_ID")
        or os.getenv("TELEGRAM_CHAT_ID")
        or os.getenv("TELEGRAM_CHATID")
    )
    return value.strip() if value else None


def _admin_chat_id() -> str | None:
    value = os.getenv("V2_ADMIN_CHAT_ID") or os.getenv("ADMIN_CHAT_ID")
    return value.strip() if value else None


def topic_id(kind: str) -> int | None:
    """Return an optional forum-topic ID configured in GitHub secrets."""
    value = os.getenv(f"V2_TELEGRAM_{kind}_TOPIC_ID") or os.getenv(f"TELEGRAM_{kind}_TOPIC_ID")
    try:
        parsed = int(value) if value else None
        return parsed if parsed and parsed > 0 else None
    except (TypeError, ValueError):
        return None


def _action_link_keyboard(message: str) -> dict | None:
    """Build URL buttons for ACTION cards without requiring callback handling.

    Telegram allows at most 100 buttons per inline keyboard. We cap the
    keyboard to 40 symbols (80 buttons) and still include every stock in text.
    """
    if "ALL ACTIONABLE CANDIDATES" not in message:
        return None
    symbols = re.findall(r"(?m)^\d+\. ([A-Z0-9&-]+)$", message)[:40]
    if not symbols:
        return None
    rows = []
    for symbol in symbols:
        encoded = quote(symbol, safe="")
        rows.append([
            {"text": f"📈 {symbol} chart", "url": f"https://www.tradingview.com/chart/?symbol=NSE%3A{encoded}"},
            {"text": "🏛 NSE quote", "url": f"https://www.nseindia.com/get-quotes/equity?symbol={encoded}"},
        ])
    return {"inline_keyboard": rows}


def _telegram_error(response: requests.Response) -> str:
    """Return Telegram's useful error description without exposing the token."""
    try:
        payload = response.json()
        description = payload.get("description")
        if description:
            return str(description)
    except ValueError:
        pass
    text = (response.text or "").strip()
    return text[:300] if text else f"HTTP {response.status_code}"


def _post_message(
    endpoint: str,
    payload: dict,
    *,
    timeout: int,
) -> tuple[bool, str]:
    try:
        response = requests.post(endpoint, json=payload, timeout=timeout)
    except requests.RequestException as exc:
        return False, f"network_error: {exc}"

    if response.status_code >= 400:
        return False, f"HTTP {response.status_code}: {_telegram_error(response)}"

    try:
        body = response.json()
    except ValueError:
        return False, "invalid_json_response"
    if not body.get("ok"):
        return False, f"telegram_rejected: {body.get('description', body)}"
    return True, "sent"


def _send_one(
    endpoint: str,
    *,
    chat_id: str,
    message: str,
    timeout: int,
    message_thread_id: int | None,
) -> tuple[bool, str]:
    base_payload: dict = {
        "chat_id": chat_id,
        "text": message,
        "disable_web_page_preview": True,
    }
    keyboard = _action_link_keyboard(message)
    if keyboard:
        base_payload["reply_markup"] = keyboard
    if message_thread_id is not None:
        base_payload["message_thread_id"] = message_thread_id

    ok, reason = _post_message(endpoint, base_payload, timeout=timeout)
    if ok:
        return True, reason

    # Most 400 failures after topic rollout are caused by a stale/non-forum
    # message_thread_id. Retry once in the main chat so reporting still works.
    if message_thread_id is not None and "HTTP 400" in reason:
        retry_payload = dict(base_payload)
        retry_payload.pop("message_thread_id", None)
        ok, retry_reason = _post_message(endpoint, retry_payload, timeout=timeout)
        if ok:
            return True, "sent_without_topic_fallback"
        reason = f"{reason}; topic_fallback={retry_reason}"

    # Invalid/oversized keyboards also produce HTTP 400. Retry plain text.
    if keyboard and "HTTP 400" in reason:
        retry_payload = dict(base_payload)
        retry_payload.pop("message_thread_id", None)
        retry_payload.pop("reply_markup", None)
        ok, retry_reason = _post_message(endpoint, retry_payload, timeout=timeout)
        if ok:
            return True, "sent_without_keyboard_fallback"
        reason = f"{reason}; keyboard_fallback={retry_reason}"

    return False, reason


def _send_to_chat(
    messages: list[str],
    *,
    chat_id: str | None,
    enabled: bool,
    timeout: int,
    missing_reason: str,
    message_thread_id: int | None = None,
) -> DeliveryResult:
    clean = [message.strip() for message in messages if message and message.strip()]
    if not enabled:
        return DeliveryResult(False, 0, "dry_run")
    token = _token()
    if not token or not chat_id:
        return DeliveryResult(False, 0, missing_reason)
    if not clean:
        return DeliveryResult(False, 0, "no_messages")

    endpoint = f"https://api.telegram.org/bot{token}/sendMessage"
    sent = 0
    errors: list[str] = []
    for index, message in enumerate(clean, start=1):
        ok, reason = _send_one(
            endpoint,
            chat_id=chat_id,
            message=message,
            timeout=timeout,
            message_thread_id=message_thread_id,
        )
        if ok:
            sent += 1
        else:
            errors.append(f"message_{index}: {reason}")
            print(f"[TELEGRAM] WARNING {errors[-1]}")

    if sent == len(clean):
        return DeliveryResult(True, sent, "sent")
    if sent > 0:
        return DeliveryResult(True, sent, "partial_delivery: " + " | ".join(errors))
    return DeliveryResult(False, 0, "delivery_failed: " + " | ".join(errors))


def send_messages(
    messages: list[str], enabled: bool = False, timeout: int = 20,
    message_thread_id: int | None = None,
) -> DeliveryResult:
    """Send end-user scanner and portfolio messages.

    Delivery failures are returned as status instead of terminating the NSE
    pipeline. Invalid topic IDs automatically fall back to the main chat.
    """
    return _send_to_chat(
        messages,
        chat_id=_user_chat_id(),
        enabled=enabled,
        timeout=timeout,
        missing_reason="telegram_credentials_missing",
        message_thread_id=message_thread_id,
    )


def send_admin_messages(
    messages: list[str], enabled: bool = False, timeout: int = 20,
) -> DeliveryResult:
    """Send diagnostics only to ADMIN_CHAT_ID.

    Admin delivery is deliberately isolated from the end-user channel. Missing
    ADMIN_CHAT_ID or a Telegram error never blocks normal scanner delivery.
    """
    return _send_to_chat(
        messages,
        chat_id=_admin_chat_id(),
        enabled=enabled,
        timeout=timeout,
        missing_reason="admin_telegram_credentials_missing",
    )
