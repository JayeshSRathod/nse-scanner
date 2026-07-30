from __future__ import annotations

import pytest

from src.portfolio_intelligence_v2.models import PortfolioRiskSnapshot, RebalanceProposal


def test_evaluated_risk_requires_evidence() -> None:
    with pytest.raises(ValueError):
        PortfolioRiskSnapshot(
            as_of_date="2026-07-31",
            position_count=5,
            concentration_pct=32.0,
            diversification_score=68.0,
            risk_status="MODERATE",
        )


def test_insufficient_data_snapshot_is_explicit() -> None:
    snapshot = PortfolioRiskSnapshot(
        as_of_date="2026-07-31",
        position_count=0,
        concentration_pct=0,
        diversification_score=0,
        risk_status="INSUFFICIENT_DATA",
        limitations=("Portfolio positions not supplied",),
    )
    assert snapshot.risk_status == "INSUFFICIENT_DATA"


def test_increase_requires_higher_weight_and_evidence() -> None:
    proposal = RebalanceProposal(
        symbol="TCS",
        action="INCREASE",
        current_weight_pct=5,
        proposed_weight_pct=7,
        rationale_codes=("QUALITY",),
        evidence_ids=("company:TCS:latest",),
    )
    assert proposal.proposed_weight_pct == 7


def test_exit_requires_zero_weight() -> None:
    with pytest.raises(ValueError):
        RebalanceProposal(
            symbol="ABC",
            action="EXIT",
            current_weight_pct=4,
            proposed_weight_pct=1,
            evidence_ids=("risk:ABC:latest",),
        )
