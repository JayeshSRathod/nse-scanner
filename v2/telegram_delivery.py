"""Minimal Telegram delivery adapter for NSE Scanner V2."""
from __future__ import annotations

import os
from dataclasses import dataclass

import requests


@dataclass(frozen=True)
class DeliveryResult:
    sent: bool
    message_count: int
    reason: str


def _credentials() -> tuple[str | None, str | None]:
    token = os.getenv("V2_TELEGRAM_TOKEN") or os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("V2_TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_CHATID")
    return token, chat_id


def send_messages(messages: list[str], enabled: bool = False, timeout: int = 20) -> DeliveryResult:
    """Send messages only when explicitly enabled; dry-run is the default."""
    clean = [message.strip() for message in messages if message and message.strip()]
    if not enabled:
        return DeliveryResult(False, 0, "dry_run")
    token, chat_id = _credentials()
    if not token or not chat_id:
        return DeliveryResult(False, 0, "telegram_credentials_missing")
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
