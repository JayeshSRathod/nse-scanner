"""Deterministic contracts for Sprint 10 market intelligence."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

_ALLOWED_REGIMES = {"BULLISH", "NEUTRAL", "BEARISH", "INSUFFICIENT_DATA"}
_ALLOWED_STATUS = {"VERIFIED", "PARTIAL", "STALE", "MISSING"}


@dataclass(frozen=True)
class MarketEvidence:
    metric: str
    as_of_date: str
    status: str
    value: Any = None
    source_reference: str = ""

    def __post_init__(self) -> None:
        if not self.metric.strip():
            raise ValueError("metric is required")
        date.fromisoformat(self.as_of_date)
        if self.status not in _ALLOWED_STATUS:
            raise ValueError(f"Unsupported market evidence status: {self.status}")
        if self.status == "VERIFIED" and not self.source_reference.strip():
            raise ValueError("Verified evidence requires source_reference")


@dataclass(frozen=True)
class MarketSnapshot:
    as_of_date: str
    regime: str
    evidence_count: int
    verified_evidence_count: int
    breadth: dict[str, Any] = field(default_factory=dict)
    sector_strength: dict[str, Any] = field(default_factory=dict)
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        date.fromisoformat(self.as_of_date)
        if self.regime not in _ALLOWED_REGIMES:
            raise ValueError(f"Unsupported market regime: {self.regime}")
        if self.evidence_count < 0 or self.verified_evidence_count < 0:
            raise ValueError("Evidence counts cannot be negative")
        if self.verified_evidence_count > self.evidence_count:
            raise ValueError("verified_evidence_count cannot exceed evidence_count")
