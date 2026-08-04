"""Telegram delivery adapters for user and admin MIS reports."""
from __future__ import annotations

import os
from dataclasses import dataclass

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


def _send_to_chat(
    messages: list[str],
    *,
    chat_id: str | None,
    enabled: bool,
    timeout: int,
    missing_reason: str,
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
        response = requests.post(
            endpoint,
            json={"chat_id": chat_id, "text": message, "disable_web_page_preview": True},
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if not payload.get("ok"):
            raise RuntimeError(f"Telegram rejected message: {payload}")
        sent += 1
    return DeliveryResult(True, sent, "sent")


def send_messages(messages: list[str], enabled: bool = False, timeout: int = 20) -> DeliveryResult:
    """Send end-user scanner and portfolio messages."""
    return _send_to_chat(
        messages,
        chat_id=_user_chat_id(),
        enabled=enabled,
        timeout=timeout,
        missing_reason="telegram_credentials_missing",
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
