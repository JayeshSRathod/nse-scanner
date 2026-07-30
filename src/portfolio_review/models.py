"""Domain models and controlled values for portfolio reviews."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

TECHNICAL_STATUSES = {"BULLISH", "NEUTRAL", "WEAK", "BROKEN"}
FUNDAMENTAL_STATUSES = {"HEALTHY", "STABLE", "WATCH", "CONCERN", "NOT_REVIEWED"}
MANAGEMENT_STATUSES = {"POSITIVE", "STABLE", "WATCH", "CONCERN", "UNKNOWN"}
RISK_STATUSES = {"LOW", "MEDIUM", "HIGH", "UNKNOWN"}
ACTIONS = {
    "HOLD",
    "WATCH",
    "REVIEW",
    "REDUCE",
    "TECHNICAL_EXIT",
    "INSUFFICIENT_DATA",
}
EVIDENCE_STATUSES = {"COMPLETE", "PARTIAL", "TECHNICAL_ONLY", "FAILED"}


@dataclass(frozen=True)
class ReviewQueueItem:
    symbol: str
    position: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PortfolioReview:
    symbol: str
    review_date: str
    review_period: str
    technical_status: str
    fundamental_status: str = "NOT_REVIEWED"
    management_status: str = "UNKNOWN"
    risk_status: str = "UNKNOWN"
    suggested_action: str = "INSUFFICIENT_DATA"
    material_change: bool = False
    confidence_score: float = 0.0
    summary: str = ""
    key_positives: list[str] = field(default_factory=list)
    key_concerns: list[str] = field(default_factory=list)
    evidence_status: str = "TECHNICAL_ONLY"
    data_limitations: list[str] = field(default_factory=list)
    prompt_version: str = "portfolio_review_v1"
    schema_version: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
