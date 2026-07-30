from __future__ import annotations

import pytest

from src.company_intelligence.models import CompanyDossier, EvidenceItem


def test_verified_evidence_item() -> None:
    item = EvidenceItem(
        source_id="nse-announcement-1",
        category="CORPORATE_ANNOUNCEMENT",
        as_of_date="2026-08-01",
        status="VERIFIED",
        payload={"headline": "Quarterly result filed"},
        source_reference="NSE",
    )
    assert item.status == "VERIFIED"


def test_invalid_evidence_status_is_rejected() -> None:
    with pytest.raises(ValueError):
        EvidenceItem(
            source_id="bad",
            category="NEWS",
            as_of_date="2026-08-01",
            status="ASSUMED",
        )


def test_company_dossier_count_contract() -> None:
    with pytest.raises(ValueError):
        CompanyDossier(
            symbol="TCS",
            generated_date="2026-08-01",
            status="READY",
            evidence_count=1,
            verified_evidence_count=2,
        )


def test_partial_company_dossier() -> None:
    dossier = CompanyDossier(
        symbol="INFY",
        generated_date="2026-08-01",
        status="PARTIAL",
        evidence_count=3,
        verified_evidence_count=2,
        limitations=("Management evidence not supplied",),
    )
    assert dossier.symbol == "INFY"
