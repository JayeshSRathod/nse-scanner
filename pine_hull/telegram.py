"""Telegram delivery facade for the isolated Pine Hull system."""
from __future__ import annotations

from v2.telegram_delivery import DeliveryResult, send_messages, topic_id


def send_signals(messages: list[str], *, enabled: bool) -> DeliveryResult:
    return send_messages(messages, enabled=enabled, message_thread_id=topic_id("PINE_SIGNALS"))


def send_portfolio(message: str, *, enabled: bool) -> DeliveryResult:
    return send_messages([message], enabled=enabled, message_thread_id=topic_id("PINE_PORTFOLIO"))


def send_period(message: str, *, period: str, enabled: bool) -> DeliveryResult:
    kind = "PINE_WEEKLY" if period == "weekly" else "PINE_MONTHLY"
    return send_messages([message], enabled=enabled, message_thread_id=topic_id(kind))
