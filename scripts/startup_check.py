"""Fail-fast CI startup validation without starting the long-running bot."""
from __future__ import annotations

import json
import os
from pathlib import Path

import requests


def main() -> int:
    errors: list[str] = []
    token = os.getenv("TELEGRAM_TOKEN", "").strip()
    chat_id = (os.getenv("TELEGRAM_CHAT_ID") or os.getenv("ADMIN_CHAT_ID") or "").strip()
    if not token:
        errors.append("TELEGRAM_TOKEN missing")
    if not chat_id:
        errors.append("TELEGRAM_CHAT_ID/ADMIN_CHAT_ID missing")
    for filename in ("telegram_last_scan.json", "scan_history.json"):
        path = Path(filename)
        if not path.exists():
            errors.append(f"{filename} missing")
            continue
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{filename} invalid: {exc}")
    if token:
        try:
            response = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=15)
            if response.status_code != 200 or not response.json().get("ok"):
                errors.append(f"Telegram getMe failed: HTTP {response.status_code}")
        except requests.RequestException as exc:
            errors.append(f"Telegram getMe unavailable: {exc}")
    if errors:
        print("STARTUP CHECK FAILED")
        for error in errors:
            print(f"- {error}")
        return 1
    print("STARTUP CHECK PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
