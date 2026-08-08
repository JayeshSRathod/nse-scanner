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


def _rich_enabled() -> bool:
    value = os.getenv("TELEGRAM_RICH_MESSAGES", "true").strip().lower()
    return value not in {"0", "false", "no", "off"}


def topic_id(kind: str) -> int | None:
    """Return an optional forum-topic ID configured in GitHub secrets."""
    value = os.getenv(f"V2_TELEGRAM_{kind}_TOPIC_ID") or os.getenv(f"TELEGRAM_{kind}_TOPIC_ID")
    try:
        parsed = int(value) if value else None
        return parsed if parsed and parsed > 0 else None
    except (TypeError, ValueError):
        return None


def _action_cards(message: str) -> list[tuple[str, str]]:
    """Return (symbol, copy_text) pairs from ACTION cards."""
    starts = list(re.finditer(r"(?m)^(\d+)\. ([A-Z0-9&-]+)\s*$", message))
    cards: list[tuple[str, str]] = []
    for index, match in enumerate(starts[:30]):
        symbol = match.group(2)
        end = starts[index + 1].start() if index + 1 < len(starts) else len(message)
        block = message[match.start():end]
        entry = re.search(r"Entry:\s*(₹[\d,]+(?:\.\d+)?)\s*\|\s*SL:\s*(₹[\d,]+(?:\.\d+)?)", block)
        targets = re.search(r"T1:\s*(₹[\d,]+(?:\.\d+)?)\s*\|\s*T2:\s*(₹[\d,]+(?:\.\d+)?)", block)
        if entry and targets:
            copy_text = (
                f"{symbol} | Entry {entry.group(1)} | SL {entry.group(2)} | "
                f"T1 {targets.group(1)} | T2 {targets.group(2)}"
            )[:256]
        else:
            copy_text = symbol
        cards.append((symbol, copy_text))
    return cards


def _action_link_keyboard(message: str) -> dict | None:
    """Build outbound-only buttons; no callback worker is required.

    Each stock receives TradingView, NSE and Copy Levels buttons. We cap at
    30 symbols (90 buttons), remaining below Telegram's 100-button limit.
    """
    if "ALL ACTIONABLE CANDIDATES" not in message:
        return None
    cards = _action_cards(message)
    if not cards:
        return None
    rows = []
    for symbol, copy_text in cards:
        encoded = quote(symbol, safe="")
        rows.append([
            {"text": f"📈 {symbol}", "url": f"https://www.tradingview.com/chart/?symbol=NSE%3A{encoded}"},
            {"text": "🏛 NSE", "url": f"https://www.nseindia.com/get-quotes/equity?symbol={encoded}"},
            {"text": "📋 Copy", "copy_text": {"text": copy_text}},
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
    text = (getattr(response, "text", "") or "").strip()
    return text[:300] if text else f"HTTP {getattr(response, 'status_code', 'unknown')}"


def _post_message(endpoint: str, payload: dict, *, timeout: int) -> tuple[bool, str]:
    try:
        response = requests.post(endpoint, json=payload, timeout=timeout)
    except requests.RequestException as exc:
        return False, f"network_error: {exc}"

    raw_status = getattr(response, "status_code", 200)
    status_code = raw_status if isinstance(raw_status, int) else 200
    if status_code >= 400:
        return False, f"HTTP {status_code}: {_telegram_error(response)}"

    try:
        body = response.json()
    except ValueError:
        return False, "invalid_json_response"
    if not body.get("ok"):
        return False, f"telegram_rejected: {body.get('description', body)}"
    return True, "sent"


def _plain_payload(chat_id: str, message: str, thread_id: int | None, keyboard: dict | None) -> dict:
    payload: dict = {
        "chat_id": chat_id,
        "text": message,
        "disable_web_page_preview": True,
    }
    if thread_id is not None:
        payload["message_thread_id"] = thread_id
    if keyboard:
        payload["reply_markup"] = keyboard
    return payload


def _rich_payload(chat_id: str, message: str, thread_id: int | None, keyboard: dict | None) -> dict:
    payload: dict = {
        "chat_id": chat_id,
        "rich_message": {"markdown": message},
    }
    if thread_id is not None:
        payload["message_thread_id"] = thread_id
    if keyboard:
        payload["reply_markup"] = keyboard
    return payload


def _send_one(
    plain_endpoint: str,
    rich_endpoint: str,
    *,
    chat_id: str,
    message: str,
    timeout: int,
    message_thread_id: int | None,
    prefer_rich: bool,
) -> tuple[bool, str]:
    keyboard = _action_link_keyboard(message)

    # Bot API 10.1+ Rich Messages are ideal for structured scanner reports.
    # They are outbound-only, so this remains fully compatible with scheduled
    # GitHub Actions. Any rich-format or topic problem falls back safely.
    if prefer_rich:
        rich_payload = _rich_payload(chat_id, message, message_thread_id, keyboard)
        ok, reason = _post_message(rich_endpoint, rich_payload, timeout=timeout)
        if ok:
            return True, "sent_rich_topic" if message_thread_id is not None else "sent_rich_general"

        if message_thread_id is not None and "HTTP 400" in reason:
            retry_payload = _rich_payload(chat_id, message, None, keyboard)
            ok, retry_reason = _post_message(rich_endpoint, retry_payload, timeout=timeout)
            if ok:
                return True, "sent_rich_general_topic_fallback"
            reason = f"{reason}; rich_topic_fallback={retry_reason}"

        # Rich formatting is an enhancement, never a dependency. Continue to
        # standard sendMessage after any rich failure.
        rich_failure = reason
    else:
        rich_failure = "rich_disabled"

    plain_payload = _plain_payload(chat_id, message, message_thread_id, keyboard)
    ok, reason = _post_message(plain_endpoint, plain_payload, timeout=timeout)
    if ok:
        return True, f"sent_plain_fallback({rich_failure})" if prefer_rich else "sent_plain"

    if message_thread_id is not None and "HTTP 400" in reason:
        retry_payload = _plain_payload(chat_id, message, None, keyboard)
        ok, retry_reason = _post_message(plain_endpoint, retry_payload, timeout=timeout)
        if ok:
            return True, "sent_plain_general_topic_fallback"
        reason = f"{reason}; topic_fallback={retry_reason}"

    # Invalid/unsupported keyboards should never prevent the report itself.
    if keyboard and ("HTTP 400" in reason or "HTTP 403" in reason):
        retry_payload = _plain_payload(chat_id, message, None, None)
        ok, retry_reason = _post_message(plain_endpoint, retry_payload, timeout=timeout)
        if ok:
            return True, "sent_plain_without_keyboard_fallback"
        reason = f"{reason}; keyboard_fallback={retry_reason}"

    return False, f"{reason}; rich_attempt={rich_failure}" if prefer_rich else reason


def _send_to_chat(
    messages: list[str],
    *,
    chat_id: str | None,
    enabled: bool,
    timeout: int,
    missing_reason: str,
    message_thread_id: int | None = None,
    prefer_rich: bool = True,
) -> DeliveryResult:
    clean = [message.strip() for message in messages if message and message.strip()]
    if not enabled:
        return DeliveryResult(False, 0, "dry_run")
    token = _token()
    if not token or not chat_id:
        return DeliveryResult(False, 0, missing_reason)
    if not clean:
        return DeliveryResult(False, 0, "no_messages")

    plain_endpoint = f"https://api.telegram.org/bot{token}/sendMessage"
    rich_endpoint = f"https://api.telegram.org/bot{token}/sendRichMessage"
    sent = 0
    errors: list[str] = []
    routes: list[str] = []
    for index, message in enumerate(clean, start=1):
        ok, reason = _send_one(
            plain_endpoint,
            rich_endpoint,
            chat_id=chat_id,
            message=message,
            timeout=timeout,
            message_thread_id=message_thread_id,
            prefer_rich=prefer_rich and _rich_enabled(),
        )
        if ok:
            sent += 1
            routes.append(reason)
        else:
            errors.append(f"message_{index}: {reason}")
            print(f"[TELEGRAM] WARNING {errors[-1]}")

    route_summary = ",".join(sorted(set(routes))) if routes else "none"
    if sent == len(clean):
        return DeliveryResult(True, sent, f"sent; routes={route_summary}")
    if sent > 0:
        return DeliveryResult(True, sent, f"partial_delivery; routes={route_summary}: " + " | ".join(errors))
    return DeliveryResult(False, 0, "delivery_failed: " + " | ".join(errors))


def send_messages(
    messages: list[str], enabled: bool = False, timeout: int = 20,
    message_thread_id: int | None = None,
) -> DeliveryResult:
    """Send end-user scanner and portfolio messages.

    Preferred route: Rich Message -> configured Topic. If either capability
    fails, delivery falls back through Rich General -> standard sendMessage ->
    General chat. No inbound callback listener is required.
    """
    return _send_to_chat(
        messages,
        chat_id=_user_chat_id(),
        enabled=enabled,
        timeout=timeout,
        missing_reason="telegram_credentials_missing",
        message_thread_id=message_thread_id,
        prefer_rich=True,
    )


def send_admin_messages(
    messages: list[str], enabled: bool = False, timeout: int = 20,
) -> DeliveryResult:
    """Send diagnostics only to ADMIN_CHAT_ID without blocking user delivery."""
    return _send_to_chat(
        messages,
        chat_id=_admin_chat_id(),
        enabled=enabled,
        timeout=timeout,
        missing_reason="admin_telegram_credentials_missing",
        prefer_rich=True,
    )
