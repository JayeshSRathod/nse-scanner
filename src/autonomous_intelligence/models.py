from dataclasses import dataclass, field
from typing import List, Optional

ALLOWED_STATUSES = {"PENDING", "READY", "BLOCKED", "REQUIRES_APPROVAL", "COMPLETED"}
ALLOWED_ACTIONS = {"OBSERVE", "RESEARCH", "REVIEW", "ALERT", "NO_ACTION"}


@dataclass(frozen=True)
class AutonomousTask:
    task_id: str
    symbol: Optional[str]
    action: str
    evidence_refs: List[str] = field(default_factory=list)
    status: str = "PENDING"
    requires_human_approval: bool = True

    def __post_init__(self) -> None:
        if not self.task_id.strip():
            raise ValueError("task_id is required")
        if self.action not in ALLOWED_ACTIONS:
            raise ValueError("unsupported action")
        if self.status not in ALLOWED_STATUSES:
            raise ValueError("unsupported status")
        if self.action != "NO_ACTION" and not self.evidence_refs:
            raise ValueError("actionable tasks require evidence")
        if self.status == "COMPLETED" and self.requires_human_approval:
            raise ValueError("approved execution must be recorded before completion")


@dataclass(frozen=True)
class AutonomousCycle:
    cycle_id: str
    generated_at: str
    tasks: List[AutonomousTask]
    execution_enabled: bool = False

    def __post_init__(self) -> None:
        if not self.cycle_id.strip():
            raise ValueError("cycle_id is required")
        if self.execution_enabled:
            raise ValueError("automated trade execution is not permitted")
