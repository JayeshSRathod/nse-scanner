import pytest

from src.autonomous_intelligence import AutonomousCycle, AutonomousTask


def test_actionable_task_requires_evidence():
    with pytest.raises(ValueError, match="require evidence"):
        AutonomousTask(task_id="t1", symbol="INFY", action="RESEARCH")


def test_automated_execution_is_rejected():
    task = AutonomousTask(
        task_id="t1",
        symbol="INFY",
        action="ALERT",
        evidence_refs=["evidence-1"],
    )
    with pytest.raises(ValueError, match="not permitted"):
        AutonomousCycle(
            cycle_id="c1",
            generated_at="2026-07-31T00:00:00Z",
            tasks=[task],
            execution_enabled=True,
        )


def test_valid_observation_cycle():
    task = AutonomousTask(
        task_id="t1",
        symbol="INFY",
        action="OBSERVE",
        evidence_refs=["evidence-1"],
        status="READY",
    )
    cycle = AutonomousCycle(
        cycle_id="c1",
        generated_at="2026-07-31T00:00:00Z",
        tasks=[task],
    )
    assert cycle.execution_enabled is False
