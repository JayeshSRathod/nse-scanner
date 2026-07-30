from __future__ import annotations

import pytest

from src.decision_intelligence.models import DecisionInput, DecisionRecommendation


def test_valid_ready_decision() -> None:
    item = DecisionRecommendation(
        decision_id="decision-tcs-2026-07-31",
        generated_date="2026-07-31",
        status="READY",
        action="HOLD",
        confidence="HIGH",
        score=78.5,
        rationale=("Company quality and technical evidence remain supportive",),
        evidence_references=("company:TCS:latest", "technical:TCS:daily"),
        component_scores={"company": 82.0, "technical": 75.0},
    )
    assert item.action == "HOLD"


def test_ready_decision_requires_evidence() -> None:
    with pytest.raises(ValueError):
        DecisionRecommendation(
            decision_id="missing-evidence",
            generated_date="2026-07-31",
            status="READY",
            action="HOLD",
            confidence="MEDIUM",
            score=60,
            rationale=("Unsupported",),
        )


def test_insufficient_data_cannot_recommend_buy() -> None:
    with pytest.raises(ValueError):
        DecisionRecommendation(
            decision_id="unsafe-buy",
            generated_date="2026-07-31",
            status="INSUFFICIENT_DATA",
            action="BUY",
            confidence="LOW",
            limitations=("Financial evidence missing",),
        )


def test_component_score_bounds_are_enforced() -> None:
    with pytest.raises(ValueError):
        DecisionRecommendation(
            decision_id="bad-score",
            generated_date="2026-07-31",
            status="PARTIAL",
            action="WATCH",
            confidence="LOW",
            component_scores={"market": 101},
        )


def test_decision_input_rejects_duplicate_evidence() -> None:
    with pytest.raises(ValueError):
        DecisionInput(
            decision_id="duplicate",
            scope="COMPANY",
            as_of_date="2026-07-31",
            subject="INFY",
            evidence_references=("company:INFY:latest", "company:INFY:latest"),
        )
