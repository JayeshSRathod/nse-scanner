#!/usr/bin/env python3
"""Build a public-safe, plain-language feed for the Telegram Mini App."""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_json(path: str, default):
    try:
        return json.loads((ROOT / path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def terminal_symbols() -> set[str]:
    path = ROOT / "corporate_data/normalized/security_lifecycle_events.csv"
    if not path.exists():
        return set()
    with path.open(encoding="utf-8", newline="") as handle:
        return {
            row.get("symbol", "").strip().upper()
            for row in csv.DictReader(handle)
            if row.get("terminal", "").strip().lower() in {"1", "true", "yes"}
        }


def number(value):
    return value if isinstance(value, (int, float)) else None


def item(row: dict, scanner: str, stage: str) -> dict:
    metrics = row.get("metrics") or {}
    entry = number(row.get("entry"))
    return {
        "scanner": scanner,
        "symbol": str(row.get("symbol", "")).upper(),
        "stage": stage,
        "score": number(row.get("score")),
        "price": number(row.get("close", row.get("last_price", entry))),
        "entry_low": number(row.get("entry_low", entry)),
        "entry_high": number(row.get("entry_high", entry)),
        "stop": number(row.get("stop", row.get("initial_stop"))),
        "target1": number(row.get("target1")),
        "target2": number(row.get("target2")),
        "five_day_change": number(metrics.get("return_5d_pct")),
        "activity": number(metrics.get("turnover_ratio", row.get("volume_ratio"))),
    }


def penny_items(data: dict) -> list[dict]:
    labels = {
        "READY": "Ready to watch",
        "CONFIRMING": "Strength building",
        "EARLY_RADAR": "Movement starting",
        "CIRCUIT_LOCKED": "Buying may be difficult",
        "EXTENDED": "Price moved too far",
    }
    return [item(row, "penny", labels.get(row.get("state"), "Watch"))
            for row in data.get("candidates", [])]


def hull_items(data: dict) -> list[dict]:
    rows: list[dict] = []
    for row in data.get("created", []):
        rows.append(item(row, "hull", "Paper position opened"))
    labels = {"READY": "Ready to watch", "EARLY": "Movement starting",
              "EXTENDED": "Price moved too far", "WEAK": "Wait"}
    for row in data.get("watch", []):
        rows.append(item(row, "hull", labels.get(row.get("timing_state"), "Watch")))
    return rows


def main() -> int:
    terminal = terminal_symbols()
    penny = read_json("output/penny_microcap/daily.json", {})
    hull = read_json("output/pine_hull_daily_run.json", {})
    items = penny_items(penny) + hull_items(hull)
    items = [row for row in items if row["symbol"] and row["symbol"] not in terminal]
    items.sort(key=lambda row: (row["scanner"], -(row["score"] or 0), row["symbol"]))
    feed = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "market_dates": {"penny": penny.get("as_of_date"), "hull": hull.get("trade_date")},
        "scanners": [
            {"id": "v3", "name": "NSE Scanner V3", "available": False},
            {"id": "ladder", "name": "Momentum Ladder", "available": False},
            {"id": "hull", "name": "Hull Scanner", "available": bool(hull)},
            {"id": "penny", "name": "Penny Scanner", "available": bool(penny)},
        ],
        "items": items,
        "notice": "Paper tracking for research and education only. Not investment advice.",
    }
    target = ROOT / "docs/data/feed.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(feed, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Mini App feed: {len(items)} visible rows; {len(terminal)} terminal symbols excluded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
