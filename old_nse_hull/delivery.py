"""Telegram transport for the independent Old NSE + Hull PAPER system."""
from __future__ import annotations

import os
from dataclasses import dataclass

import requests


@dataclass(frozen=True)
class DeliveryResult:
    sent: bool
    reason: str


def _topic_id(kind: str) -> int | None:
    names = {
        "radar": ("TELEGRAM_OLD_HULL_DAILY_TOPIC_ID", "TELEGRAM_PINE_SIGNALS_TOPIC_ID"),
        "trades": ("TELEGRAM_OLD_HULL_TRADES_TOPIC_ID", "TELEGRAM_PINE_PORTFOLIO_TOPIC_ID"),
        "weekly": ("TELEGRAM_OLD_HULL_WEEKLY_TOPIC_ID", "TELEGRAM_PINE_WEEKLY_TOPIC_ID"),
        "monthly": ("TELEGRAM_OLD_HULL_MONTHLY_TOPIC_ID", "TELEGRAM_PINE_MONTHLY_TOPIC_ID"),
    }
    value = next((os.getenv(name, "").strip() for name in names[kind] if os.getenv(name, "").strip()), "")
    try:
        topic_id = int(value)
    except ValueError:
        return None
    return topic_id if topic_id > 0 else None


def send_message(message: str, kind: str, timeout: int = 20) -> DeliveryResult:
    """Deliver to a dedicated Old+Hull topic, reusing the retired Pine topic IDs."""
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
    if topic_id := _topic_id(kind):
        payload["message_thread_id"] = topic_id
    try:
        response = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json=payload, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        return DeliveryResult(False, f"telegram_failed:{type(exc).__name__}")
    return DeliveryResult(True, "sent")


def send_radar(message: str, timeout: int = 20) -> DeliveryResult:
    return send_message(message, "radar", timeout)


def send_trades(message: str, timeout: int = 20) -> DeliveryResult:
    return send_message(message, "trades", timeout)


def send_period(message: str, period: str, timeout: int = 20) -> DeliveryResult:
    return send_message(message, period, timeout)
