"""Deterministic contracts for MIS Portfolio Intelligence 2.0."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

_ALLOWED_RISK_STATUS = {"LOW", "MODERATE", "HIGH", "INSUFFICIENT_DATA"}
_ALLOWED_ACTIONS = {"HOLD", "REDUCE", "INCREASE", "EXIT", "NO_ACTION"}


@dataclass(frozen=True)
class PortfolioRiskSnapshot:
    as_of_date: str
    position_count: int
    concentration_pct: float
    diversification_score: float
    risk_status: str
    evidence_ids: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        date.fromisoformat(self.as_of_date)
        if self.position_count < 0:
            raise ValueError("position_count cannot be negative")
        if not 0 <= self.concentration_pct <= 100:
            raise ValueError("concentration_pct must be between 0 and 100")
        if not 0 <= self.diversification_score <= 100:
            raise ValueError("diversification_score must be between 0 and 100")
        if self.risk_status not in _ALLOWED_RISK_STATUS:
            raise ValueError(f"Unsupported risk status: {self.risk_status}")
        if self.risk_status != "INSUFFICIENT_DATA" and not self.evidence_ids:
            raise ValueError("Evaluated risk requires evidence_ids")


@dataclass(frozen=True)
class RebalanceProposal:
    symbol: str
    action: str
    current_weight_pct: float
    proposed_weight_pct: float
    rationale_codes: tuple[str, ...] = field(default_factory=tuple)
    evidence_ids: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol is required")
        if self.action not in _ALLOWED_ACTIONS:
            raise ValueError(f"Unsupported action: {self.action}")
        if not 0 <= self.current_weight_pct <= 100:
            raise ValueError("current_weight_pct must be between 0 and 100")
        if not 0 <= self.proposed_weight_pct <= 100:
            raise ValueError("proposed_weight_pct must be between 0 and 100")
        if self.action != "NO_ACTION" and not self.evidence_ids:
            raise ValueError("Actionable proposals require evidence_ids")
        if self.action == "INCREASE" and self.proposed_weight_pct <= self.current_weight_pct:
            raise ValueError("INCREASE requires a higher proposed weight")
        if self.action in {"REDUCE", "EXIT"} and self.proposed_weight_pct >= self.current_weight_pct:
            raise ValueError(f"{self.action} requires a lower proposed weight")
        if self.action == "EXIT" and self.proposed_weight_pct != 0:
            raise ValueError("EXIT requires proposed_weight_pct of 0")
