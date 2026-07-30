"""Aggregate latest validated reviews into a compact portfolio-health snapshot."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from .review_validator import validate_review

_ACTION_PRIORITY = {
    "TECHNICAL_EXIT": 0,
    "REDUCE": 1,
    "REVIEW": 2,
    "WATCH": 3,
    "INSUFFICIENT_DATA": 4,
    "HOLD": 5,
}


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def build_portfolio_health(
    portfolio_path: str | Path = "portfolio.json",
    reports_root: str | Path = "reports/portfolio",
) -> dict[str, Any]:
    portfolio = _read_json(Path(portfolio_path)) or {}
    positions = portfolio.get("positions", {})
    if not isinstance(positions, dict):
        positions = {}

    rows: list[dict[str, Any]] = []
    for raw_symbol, position in positions.items():
        symbol = str(raw_symbol).strip().upper()
        if not symbol or not isinstance(position, dict):
            continue
        if str(position.get("status", "OPEN")).upper() in {"CLOSED", "EXITED", "CANCELLED"}:
            continue

        latest_path = Path(reports_root) / symbol / "latest.json"
        review = _read_json(latest_path)
        if review is None:
            rows.append({
                "symbol": symbol,
                "review_available": False,
                "technical_status": "NOT_REVIEWED",
                "fundamental_status": "NOT_REVIEWED",
                "risk_status": "UNKNOWN",
                "suggested_action": "INSUFFICIENT_DATA",
                "review_date": None,
                "review_period": None,
                "confidence_score": 0,
                "summary": "Monthly AI portfolio review is not yet available.",
            })
            continue

        errors = validate_review(review, expected_symbol=symbol)
        if errors:
            rows.append({
                "symbol": symbol,
                "review_available": False,
                "technical_status": "NOT_REVIEWED",
                "fundamental_status": "NOT_REVIEWED",
                "risk_status": "UNKNOWN",
                "suggested_action": "REVIEW",
                "review_date": None,
                "review_period": None,
                "confidence_score": 0,
                "summary": "Latest stored review failed validation.",
                "validation_errors": errors,
            })
            continue

        rows.append({
            "symbol": symbol,
            "review_available": True,
            "technical_status": review["technical_status"],
            "fundamental_status": review["fundamental_status"],
            "risk_status": review["risk_status"],
            "suggested_action": review["suggested_action"],
            "review_date": review["review_date"],
            "review_period": review["review_period"],
            "confidence_score": review["confidence_score"],
            "summary": review["summary"],
            "key_concerns": review.get("key_concerns", [])[:3],
            "data_limitations": review.get("data_limitations", [])[:3],
        })

    rows.sort(key=lambda row: (_ACTION_PRIORITY.get(row["suggested_action"], 99), row["symbol"]))
    return {
        "generated_date": date.today().isoformat(),
        "position_count": len(rows),
        "reviewed_count": sum(row["review_available"] for row in rows),
        "pending_count": sum(not row["review_available"] for row in rows),
        "action_counts": {
            action: sum(row["suggested_action"] == action for row in rows)
            for action in _ACTION_PRIORITY
        },
        "positions": rows,
    }


def save_portfolio_health(payload: dict[str, Any], output_path: str | Path = "data/portfolio_health.json") -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
