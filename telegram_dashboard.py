"""Shared Telegram dashboard links and plain-language status labels."""
from __future__ import annotations

import os
from urllib.parse import urlencode


DEFAULT_DASHBOARD_URL = "https://jayeshsrathod.github.io/nse-scanner/"

STATUS_LABELS = {
    "EARLY": "Early watchlist",
    "EARLY_RADAR": "Early watchlist",
    "CONFIRMING": "Watchlist—wait for confirmation",
    "READY": "Watch for entry",
    "NEW_TRIGGER": "New paper entry",
    "NEWLY_QUALIFIED": "New paper entry",
    "OPEN": "Open paper position",
    "EXTENDED": "Wait for pullback",
    "CIRCUIT_LOCKED": "No entry—circuit risk",
    "WAIT": "No action yet",
    "WEAK": "No action yet",
}


def status_label(state: object, default: str = "No action yet") -> str:
    return STATUS_LABELS.get(str(state or "").upper(), default)


def dashboard_url(scanner: str) -> str:
    base = os.getenv("NSE_MINI_APP_URL", DEFAULT_DASHBOARD_URL).strip() or DEFAULT_DASHBOARD_URL
    separator = "&" if "?" in base else "?"
    return f"{base}{separator}{urlencode({'startapp': scanner})}"


def dashboard_keyboard(scanner: str) -> dict:
    return {"inline_keyboard": [[
        {"text": "📊 Open Scanner Dashboard", "url": dashboard_url(scanner)},
    ]]}
