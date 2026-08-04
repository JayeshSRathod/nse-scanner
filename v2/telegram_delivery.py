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
    return os.getenv("V2_TELEGRAM_TOKEN") or os.getenv("TELEGRAM_TOKEN")


def _user_chat_id() -> str | None:
    return (
        os.getenv("V2_TELEGRAM_CHAT_ID")
        or os.getenv("TELEGRAM_CHAT_ID")
        or os.getenv("TELEGRAM_CHATID")
    )


def _admin_chat_id() -> str | None:
    return os.getenv("V2_ADMIN_CHAT_ID") or os.getenv("ADMIN_CHAT_ID")


def topic_id(kind: str) -> int | None:
    """Return an optional forum-topic ID configured in GitHub secrets."""
    value = os.getenv(f"V2_TELEGRAM_{kind}_TOPIC_ID") or os.getenv(f"TELEGRAM_{kind}_TOPIC_ID")
    try:
        return int(value) if value else None
    except ValueError:
        return None


def _action_link_keyboard(message: str) -> dict | None:
    """Build URL buttons for ACTION cards without requiring callback handling."""
    if "ALL ACTIONABLE CANDIDATES" not in message:
        return None
    symbols = re.findall(r"(?m)^\d+\. ([A-Z0-9&-]+)$", message)
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
    for message in clean:
        payload = {"chat_id": chat_id, "text": message, "disable_web_page_preview": True}
        if message_thread_id is not None:
            payload["message_thread_id"] = message_thread_id
        keyboard = _action_link_keyboard(message)
        if keyboard:
            payload["reply_markup"] = keyboard
        response = requests.post(
            endpoint,
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if not payload.get("ok"):
            raise RuntimeError(f"Telegram rejected message: {payload}")
        sent += 1
    return DeliveryResult(True, sent, "sent")


def send_messages(
    messages: list[str], enabled: bool = False, timeout: int = 20,
    message_thread_id: int | None = None,
) -> DeliveryResult:
    """Send end-user scanner and portfolio messages."""
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
    ADMIN_CHAT_ID never blocks normal scanner delivery.
    """
    return _send_to_chat(
        messages,
        chat_id=_admin_chat_id(),
        enabled=enabled,
        timeout=timeout,
        missing_reason="admin_telegram_credentials_missing",
    )
