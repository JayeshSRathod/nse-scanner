"""End-to-end contract tests for Sprint 8 portfolio intelligence."""
from __future__ import annotations

import json
from pathlib import Path

from src.portfolio_review.health_builder import build_portfolio_health
from src.portfolio_review.review_repository import save_review
from src.portfolio_review.telegram_health import render_portfolio_health_message


def _review(symbol: str, period: str = "2026-08") -> dict:
    return {
        "symbol": symbol,
        "review_date": "2026-08-01",
        "review_period": period,
        "technical_status": "BULLISH",
        "fundamental_status": "NOT_REVIEWED",
        "management_status": "UNKNOWN",
        "risk_status": "LOW",
        "suggested_action": "HOLD",
        "material_change": False,
        "confidence_score": 80,
        "summary": "Verified technical evidence remains constructive.",
        "key_positives": ["Daily and weekly trend alignment"],
        "key_concerns": [],
        "evidence_status": "TECHNICAL_ONLY",
        "data_limitations": ["Fundamental evidence was not supplied"],
    }


def test_review_to_health_to_telegram_end_to_end(tmp_path: Path) -> None:
    portfolio = {
        "positions": {
            "TCS": {"symbol": "TCS", "status": "OPEN", "quantity": 5, "entry_price": 3500},
            "INFY": {"symbol": "INFY", "status": "OPEN", "quantity": 4, "entry_price": 1500},
        },
        "closed": [],
    }
    portfolio_path = tmp_path / "portfolio.json"
    portfolio_path.write_text(json.dumps(portfolio), encoding="utf-8")

    reports_root = tmp_path / "reports" / "portfolio"
    save_review(_review("TCS"), reports_root=reports_root)

    health = build_portfolio_health(portfolio_path=portfolio_path, reports_root=reports_root)
    assert health["summary"]["active_positions"] == 2
    assert health["summary"]["reviewed"] == 1
    assert health["summary"]["pending"] == 1

    by_symbol = {item["symbol"]: item for item in health["positions"]}
    assert by_symbol["TCS"]["suggested_action"] == "HOLD"
    assert by_symbol["INFY"]["suggested_action"] in {"REVIEW", "INSUFFICIENT_DATA"}

    message = render_portfolio_health_message(health)
    assert "KJ PORTFOLIO INTELLIGENCE" in message
    assert "TCS" in message
    assert "INFY" in message
    assert "stop-loss" in message.lower()


def test_corrupt_latest_review_is_not_trusted(tmp_path: Path) -> None:
    portfolio_path = tmp_path / "portfolio.json"
    portfolio_path.write_text(
        json.dumps({"positions": {"TCS": {"symbol": "TCS", "status": "OPEN", "quantity": 1}}}),
        encoding="utf-8",
    )
    latest = tmp_path / "reports" / "portfolio" / "TCS" / "latest.json"
    latest.parent.mkdir(parents=True)
    latest.write_text("{not valid json", encoding="utf-8")

    health = build_portfolio_health(portfolio_path=portfolio_path, reports_root=tmp_path / "reports" / "portfolio")
    item = health["positions"][0]
    assert item["review_status"] != "VALID"
    assert item["suggested_action"] in {"REVIEW", "INSUFFICIENT_DATA"}
