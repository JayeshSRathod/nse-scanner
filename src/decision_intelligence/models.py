"""Deterministic contracts for Sprint 14 Decision Intelligence."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

_ALLOWED_SCOPES = {"COMPANY", "OPPORTUNITY", "PORTFOLIO", "MARKET"}
_ALLOWED_ACTIONS = {"BUY", "ADD", "HOLD", "REDUCE", "EXIT", "WATCH", "NO_ACTION"}
_ALLOWED_STATUSES = {"READY", "PARTIAL", "INSUFFICIENT_DATA", "CONFLICTING_EVIDENCE"}
_ALLOWED_CONFIDENCE = {"LOW", "MEDIUM", "HIGH"}


@dataclass(frozen=True)
class DecisionInput:
    decision_id: str
    scope: str
    as_of_date: str
    subject: str
    evidence_references: tuple[str, ...] = ()
    source_modules: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.decision_id.strip():
            raise ValueError("decision_id is required")
        if self.scope not in _ALLOWED_SCOPES:
            raise ValueError(f"Unsupported decision scope: {self.scope}")
        date.fromisoformat(self.as_of_date)
        if not self.subject.strip():
            raise ValueError("subject is required")
        if len(set(self.evidence_references)) != len(self.evidence_references):
            raise ValueError("evidence_references must be unique")
        if len(set(self.source_modules)) != len(self.source_modules):
            raise ValueError("source_modules must be unique")


@dataclass(frozen=True)
class DecisionRecommendation:
    decision_id: str
    generated_date: str
    status: str
    action: str
    confidence: str
    score: float | None = None
    rationale: tuple[str, ...] = ()
    evidence_references: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    component_scores: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.decision_id.strip():
            raise ValueError("decision_id is required")
        date.fromisoformat(self.generated_date)
        if self.status not in _ALLOWED_STATUSES:
            raise ValueError(f"Unsupported decision status: {self.status}")
        if self.action not in _ALLOWED_ACTIONS:
            raise ValueError(f"Unsupported decision action: {self.action}")
        if self.confidence not in _ALLOWED_CONFIDENCE:
            raise ValueError(f"Unsupported confidence: {self.confidence}")
        if self.score is not None and not 0 <= self.score <= 100:
            raise ValueError("score must be between 0 and 100")
        for name, value in self.component_scores.items():
            if not name.strip():
                raise ValueError("component score names cannot be blank")
            if not 0 <= value <= 100:
                raise ValueError("component scores must be between 0 and 100")
        if len(set(self.evidence_references)) != len(self.evidence_references):
            raise ValueError("evidence_references must be unique")
        if self.status == "READY":
            if not self.evidence_references:
                raise ValueError("READY decisions require evidence references")
            if not self.rationale:
                raise ValueError("READY decisions require rationale")
            if self.score is None:
                raise ValueError("READY decisions require a deterministic score")
        if self.status in {"INSUFFICIENT_DATA", "CONFLICTING_EVIDENCE"}:
            if self.action not in {"WATCH", "NO_ACTION"}:
                raise ValueError("Unresolved decisions cannot recommend portfolio-changing actions")
            if not self.limitations:
                raise ValueError("Unresolved decisions require limitations")
        if self.action in {"BUY", "ADD", "REDUCE", "EXIT"} and self.status != "READY":
            raise ValueError("Portfolio-changing actions require READY status")
