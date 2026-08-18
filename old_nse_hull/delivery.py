"""Telegram transport for the independent Old NSE + Hull PAPER system."""
from __future__ import annotations

import os
from dataclasses import dataclass

import requests


@dataclass(frozen=True)
class DeliveryResult:
    sent: bool
    reason: str


def _topic_id() -> int | None:
    value = os.getenv("TELEGRAM_OLD_HULL_DAILY_TOPIC_ID", "").strip()
    try:
        topic_id = int(value)
    except ValueError:
        return None
    return topic_id if topic_id > 0 else None


def send_radar(message: str, timeout: int = 20) -> DeliveryResult:
    """Deliver a PAPER radar without importing or mutating V2/V3 delivery state."""
    token = os.getenv("TELEGRAM_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return DeliveryResult(False, "telegram_not_configured")
    payload: dict[str, object] = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if topic_id := _topic_id():
        payload["message_thread_id"] = topic_id
    try:
        response = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json=payload, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        return DeliveryResult(False, f"telegram_failed:{type(exc).__name__}")
    return DeliveryResult(True, "sent")
