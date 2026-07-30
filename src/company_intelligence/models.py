"""Core deterministic contracts for Sprint 9 company intelligence."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

_ALLOWED_EVIDENCE_STATUS = {"VERIFIED", "MISSING", "STALE", "REJECTED"}
_ALLOWED_DOSSIER_STATUS = {"READY", "PARTIAL", "INSUFFICIENT_DATA"}


@dataclass(frozen=True)
class EvidenceItem:
    source_id: str
    category: str
    as_of_date: str
    status: str
    payload: dict[str, Any] = field(default_factory=dict)
    source_reference: str = ""

    def __post_init__(self) -> None:
        if not self.source_id.strip():
            raise ValueError("source_id is required")
        if not self.category.strip():
            raise ValueError("category is required")
        if self.status not in _ALLOWED_EVIDENCE_STATUS:
            raise ValueError(f"Unsupported evidence status: {self.status}")
        date.fromisoformat(self.as_of_date)


@dataclass(frozen=True)
class CompanyDossier:
    symbol: str
    generated_date: str
    status: str
    evidence_count: int
    verified_evidence_count: int
    sections: dict[str, Any] = field(default_factory=dict)
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol is required")
        date.fromisoformat(self.generated_date)
        if self.status not in _ALLOWED_DOSSIER_STATUS:
            raise ValueError(f"Unsupported dossier status: {self.status}")
        if self.evidence_count < 0 or self.verified_evidence_count < 0:
            raise ValueError("Evidence counts cannot be negative")
        if self.verified_evidence_count > self.evidence_count:
            raise ValueError("verified_evidence_count cannot exceed evidence_count")
