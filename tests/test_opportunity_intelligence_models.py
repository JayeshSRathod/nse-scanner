from __future__ import annotations

import pytest

from src.opportunity_intelligence.models import OpportunityCandidate, OpportunityEvidence


def test_verified_opportunity_evidence_requires_provenance() -> None:
    evidence = OpportunityEvidence(
        evidence_id="technical-tcs-2026-07-31",
        category="TECHNICAL",
        as_of_date="2026-07-31",
        source_reference="scanner-output",
        payload={"trend": "UP"},
    )
    assert evidence.category == "TECHNICAL"


def test_missing_source_reference_is_rejected() -> None:
    with pytest.raises(ValueError):
        OpportunityEvidence(
            evidence_id="bad",
            category="NEWS",
            as_of_date="2026-07-31",
            source_reference="",
        )


def test_qualified_candidate_requires_evidence() -> None:
    with pytest.raises(ValueError):
        OpportunityCandidate(
            symbol="TCS",
            generated_date="2026-07-31",
            status="QUALIFIED",
            horizon="POSITIONAL",
            confidence="HIGH",
            score=82.5,
        )


def test_insufficient_data_cannot_be_high_confidence() -> None:
    with pytest.raises(ValueError):
        OpportunityCandidate(
            symbol="INFY",
            generated_date="2026-07-31",
            status="INSUFFICIENT_DATA",
            horizon="LONG_TERM",
            confidence="HIGH",
            score=40,
        )


def test_valid_watchlist_candidate() -> None:
    candidate = OpportunityCandidate(
        symbol="RELIANCE",
        generated_date="2026-07-31",
        status="WATCHLIST",
        horizon="SWING",
        confidence="MEDIUM",
        score=68,
        evidence_ids=("technical-reliance-1",),
        rationale=("Trend improving",),
        risks=("Breakout not confirmed",),
    )
    assert candidate.score == 68
