import json
from pathlib import Path

import pytest

from src.portfolio_review import (
    build_review_prompt,
    collect_evidence,
    load_latest_review,
    save_review,
    validate_review,
)
from src.portfolio_review.review_repository import ReviewAlreadyExistsError


def _valid_review(symbol="TCS", evidence_status="TECHNICAL_ONLY"):
    return {
        "symbol": symbol,
        "review_date": "2026-08-01",
        "review_period": "2026-08",
        "technical_status": "BULLISH",
        "fundamental_status": "NOT_REVIEWED",
        "management_status": "UNKNOWN",
        "risk_status": "MEDIUM",
        "suggested_action": "HOLD",
        "material_change": False,
        "confidence_score": 70,
        "summary": "The technical position remains valid based on supplied evidence.",
        "key_positives": ["Trend remains aligned"],
        "key_concerns": ["Fundamentals were not verified"],
        "evidence_status": evidence_status,
        "data_limitations": ["Quarterly statements were not supplied"],
    }


def test_collect_evidence_is_explicit_when_scanner_data_missing(tmp_path):
    item = {"symbol": "TCS", "position": {"entry_price": 100}}
    evidence = collect_evidence(item, tmp_path / "missing.json")
    assert evidence["evidence_status"] == "FAILED"
    assert evidence["fundamentals"] == {}
    assert evidence["data_limitations"]


def test_collect_evidence_reads_matching_stock(tmp_path):
    scan = tmp_path / "scan.json"
    scan.write_text(json.dumps({"stocks": [{"symbol": "TCS", "close": 120, "rsi": 61}]}))
    evidence = collect_evidence({"symbol": "TCS", "position": {}}, scan)
    assert evidence["evidence_status"] == "TECHNICAL_ONLY"
    assert evidence["technical"]["close"] == 120


def test_prompt_forbids_unverified_fundamentals():
    evidence = {"symbol": "TCS", "evidence_status": "TECHNICAL_ONLY", "data_limitations": []}
    prompt = build_review_prompt(evidence, "2026-08")
    assert "fundamental_status to NOT_REVIEWED" in prompt
    assert "Return one JSON object only" in prompt


def test_validator_rejects_fundamental_claim_without_evidence():
    review = _valid_review()
    review["fundamental_status"] = "HEALTHY"
    errors = validate_review(review, "TCS")
    assert any("fundamental_status=NOT_REVIEWED" in error for error in errors)


def test_repository_preserves_monthly_history(tmp_path):
    review = _valid_review()
    dated, latest = save_review(review, tmp_path)
    assert dated.exists() and latest.exists()
    assert load_latest_review("TCS", tmp_path)["review_period"] == "2026-08"
    with pytest.raises(ReviewAlreadyExistsError):
        save_review(review, tmp_path)
