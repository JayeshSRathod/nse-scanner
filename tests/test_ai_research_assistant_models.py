from __future__ import annotations

import pytest

from src.ai_research_assistant.models import ResearchAnswer, ResearchQuery


def test_query_normalizes_symbols() -> None:
    query = ResearchQuery(
        query_id="q-1",
        question="Compare TCS and Infosys",
        query_type="COMPARISON",
        requested_date="2026-07-31",
        symbols=(" tcs ", "infy"),
    )
    assert query.symbols == ("TCS", "INFY")


def test_ready_answer_requires_evidence() -> None:
    with pytest.raises(ValueError):
        ResearchAnswer(
            query_id="q-1",
            generated_date="2026-07-31",
            status="READY",
            confidence="HIGH",
            summary="Evidence-backed comparison",
        )


def test_insufficient_data_cannot_claim_high_confidence() -> None:
    with pytest.raises(ValueError):
        ResearchAnswer(
            query_id="q-2",
            generated_date="2026-07-31",
            status="INSUFFICIENT_DATA",
            confidence="HIGH",
            summary="Not enough verified evidence",
            limitations=("Financial evidence missing",),
        )


def test_ready_answer_with_evidence() -> None:
    answer = ResearchAnswer(
        query_id="q-3",
        generated_date="2026-07-31",
        status="READY",
        confidence="MEDIUM",
        summary="Technical and company evidence support the conclusion.",
        evidence_references=("company:TCS:latest", "market:2026-07-31"),
    )
    assert answer.status == "READY"
