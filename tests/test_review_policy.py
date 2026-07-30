from datetime import date
import json

from src.portfolio_review.recovery import write_recovery_manifest
from src.portfolio_review.review_policy import ReviewPolicy, review_age_days, should_review_symbol


def _review(review_date: str) -> dict:
    return {
        "symbol": "TCS",
        "review_date": review_date,
        "review_period": review_date[:7],
        "technical_status": "BULLISH",
        "fundamental_status": "NOT_REVIEWED",
        "management_status": "UNKNOWN",
        "risk_status": "LOW",
        "suggested_action": "HOLD",
        "material_change": False,
        "confidence_score": 75,
        "summary": "Technical evidence is constructive.",
        "key_positives": [],
        "key_concerns": [],
        "evidence_status": "TECHNICAL_ONLY",
        "data_limitations": ["Fundamentals unavailable"],
    }


def test_review_age_days():
    assert review_age_days(_review("2026-07-01"), as_of=date(2026, 7, 31)) == 30
    assert review_age_days(None, as_of=date(2026, 7, 31)) is None


def test_fresh_review_is_cached(tmp_path):
    symbol_dir = tmp_path / "TCS"
    symbol_dir.mkdir()
    (symbol_dir / "latest.json").write_text(json.dumps(_review("2026-07-20")), encoding="utf-8")
    policy = ReviewPolicy(max_age_days=45)
    required, reason = should_review_symbol(
        "TCS", reports_root=tmp_path, policy=policy, as_of=date(2026, 7, 31)
    )
    assert required is False
    assert "fresh" in reason


def test_stale_review_is_requeued(tmp_path):
    symbol_dir = tmp_path / "TCS"
    symbol_dir.mkdir()
    (symbol_dir / "latest.json").write_text(json.dumps(_review("2026-05-01")), encoding="utf-8")
    required, reason = should_review_symbol(
        "TCS",
        reports_root=tmp_path,
        policy=ReviewPolicy(max_age_days=45),
        as_of=date(2026, 7, 31),
    )
    assert required is True
    assert "days old" in reason


def test_force_refresh_bypasses_cache(tmp_path):
    required, reason = should_review_symbol(
        "TCS", reports_root=tmp_path, policy=ReviewPolicy(force_refresh=True)
    )
    assert required is True
    assert reason == "forced refresh"


def test_recovery_manifest_records_failures(tmp_path):
    destination = write_recovery_manifest(
        [
            {"symbol": "TCS", "status": "SUCCESS"},
            {"symbol": "INFY", "status": "FAILED", "error": "timeout"},
        ],
        review_period="2026-07",
        path=tmp_path / "recovery.json",
    )
    payload = json.loads(destination.read_text(encoding="utf-8"))
    assert payload["retry_required"] is True
    assert payload["failed_symbols"] == ["INFY"]
