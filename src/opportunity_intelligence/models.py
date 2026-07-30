"""Deterministic contracts for MIS opportunity intelligence."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

_ALLOWED_OPPORTUNITY_STATUS = {"QUALIFIED", "WATCHLIST", "REJECTED", "INSUFFICIENT_DATA"}
_ALLOWED_HORIZONS = {"SHORT", "SWING", "POSITIONAL", "LONG_TERM"}
_ALLOWED_CONFIDENCE = {"LOW", "MEDIUM", "HIGH"}


@dataclass(frozen=True)
class OpportunityEvidence:
    evidence_id: str
    category: str
    as_of_date: str
    source_reference: str
    payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.evidence_id.strip():
            raise ValueError("evidence_id is required")
        if not self.category.strip():
            raise ValueError("category is required")
        if not self.source_reference.strip():
            raise ValueError("source_reference is required")
        date.fromisoformat(self.as_of_date)


@dataclass(frozen=True)
class OpportunityCandidate:
    symbol: str
    generated_date: str
    status: str
    horizon: str
    confidence: str
    score: float
    evidence_ids: tuple[str, ...] = ()
    rationale: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol is required")
        date.fromisoformat(self.generated_date)
        if self.status not in _ALLOWED_OPPORTUNITY_STATUS:
            raise ValueError(f"Unsupported opportunity status: {self.status}")
        if self.horizon not in _ALLOWED_HORIZONS:
            raise ValueError(f"Unsupported horizon: {self.horizon}")
        if self.confidence not in _ALLOWED_CONFIDENCE:
            raise ValueError(f"Unsupported confidence: {self.confidence}")
        if not 0 <= self.score <= 100:
            raise ValueError("score must be between 0 and 100")
        if self.status == "QUALIFIED" and not self.evidence_ids:
            raise ValueError("Qualified opportunities require evidence")
        if self.status == "INSUFFICIENT_DATA" and self.confidence == "HIGH":
            raise ValueError("Insufficient-data opportunities cannot have HIGH confidence")
