"""Send one explicit smoke message through each isolated bot/system topic."""
from __future__ import annotations

import os

import requests


ROUTES = {
    "V3": ("V3_TELEGRAM_BOT_TOKEN", "V3_TELEGRAM_CHAT_ID", "V3_SYSTEM_TOPIC_ID"),
    "LADDER": ("LADDER_TELEGRAM_BOT_TOKEN", "LADDER_TELEGRAM_CHAT_ID", "LADDER_SYSTEM_TOPIC_ID"),
    "HULL": ("HULL_TELEGRAM_BOT_TOKEN", "HULL_TELEGRAM_CHAT_ID", "HULL_SYSTEM_TOPIC_ID"),
}


def main() -> int:
    failures: list[str] = []
    for route, (token_name, chat_name, topic_name) in ROUTES.items():
        token = os.getenv(token_name, "").strip()
        chat_id = os.getenv(chat_name, "").strip()
        topic = os.getenv(topic_name, "").strip()
        if not token or not chat_id or not topic.isdigit() or int(topic) <= 0:
            failures.append(f"{route}: missing credentials or valid system topic")
            continue
        payload = {
            "chat_id": chat_id,
            "message_thread_id": int(topic),
            "text": f"✅ <b>{route} BOT ROUTE VERIFIED</b>\nDedicated token, chat and system topic are working.",
            "parse_mode": "HTML",
        }
        try:
            response = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage", json=payload, timeout=20,
            )
            body = response.json()
            if response.status_code != 200 or not body.get("ok"):
                failures.append(f"{route}: Telegram rejected route (HTTP {response.status_code})")
            else:
                print(f"{route}: route verified")
        except (requests.RequestException, ValueError) as exc:
            failures.append(f"{route}: {type(exc).__name__}")
    if failures:
        print("ROUTE SMOKE FAILED")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("ALL THREE TELEGRAM ROUTES VERIFIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
