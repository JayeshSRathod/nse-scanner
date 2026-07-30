from __future__ import annotations

import pytest

from src.market_intelligence.models import MarketEvidence, MarketSnapshot


def test_verified_market_evidence_requires_provenance() -> None:
    with pytest.raises(ValueError):
        MarketEvidence(
            metric="ADVANCE_DECLINE_RATIO",
            as_of_date="2026-07-31",
            status="VERIFIED",
            value=1.4,
        )


def test_valid_verified_market_evidence() -> None:
    evidence = MarketEvidence(
        metric="ADVANCE_DECLINE_RATIO",
        as_of_date="2026-07-31",
        status="VERIFIED",
        value=1.4,
        source_reference="NSE daily market statistics",
    )
    assert evidence.value == 1.4


def test_market_snapshot_count_contract() -> None:
    with pytest.raises(ValueError):
        MarketSnapshot(
            as_of_date="2026-07-31",
            regime="NEUTRAL",
            evidence_count=1,
            verified_evidence_count=2,
        )


def test_insufficient_data_regime_is_explicit() -> None:
    snapshot = MarketSnapshot(
        as_of_date="2026-07-31",
        regime="INSUFFICIENT_DATA",
        evidence_count=0,
        verified_evidence_count=0,
        limitations=("Breadth evidence not supplied",),
    )
    assert snapshot.regime == "INSUFFICIENT_DATA"
